from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import signal
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from queue import Full, Queue
from threading import Event
from typing import Deque, Dict, Optional, Tuple

from .configuration import CabinAnnotationConfig, ConfigStore
from .diagnostics import configure_logging
from .frame_sync import FrameIdentityManager, FrameRef, FrameResultJoiner, TelemetryCache
from .inference_contracts import BoundingBox, FatigueObservation, InferenceHealth
from .overlay_composer import OverlayComposer, identity_values
from .store import RuntimeStore


LOGGER = logging.getLogger("mh02.cabin-annotation")


class ArtifactWriter:
    def __init__(self, output_path: Path, health_path: Path) -> None:
        self.output_path = output_path
        self.health_path = health_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        health_path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, event: FatigueObservation) -> None:
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")

    def health(self, health: InferenceHealth) -> None:
        temporary = self.health_path.with_suffix(".tmp")
        temporary.write_text(health.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.health_path)


class ObservationBuffer:
    def __init__(self, limit: int = 64) -> None:
        self.values: Dict[Tuple[str, str, int], FatigueObservation] = {}
        self.legacy_values: Dict[int, FatigueObservation] = {}
        self.lock = threading.Lock()
        self.limit = limit

    def put(self, observation: FatigueObservation) -> None:
        with self.lock:
            if observation.frame_ref is not None:
                self.values[observation.frame_ref.key] = observation
            elif observation.media_pts_ns is not None:
                self.legacy_values[observation.media_pts_ns] = observation
            while len(self.values) + len(self.legacy_values) > self.limit:
                if self.values:
                    self.values.pop(next(iter(self.values)))
                elif self.legacy_values:
                    self.legacy_values.pop(next(iter(self.legacy_values)))

    def match(self, pts_ns: Optional[int], max_age_ns: int) -> Optional[FatigueObservation]:
        if pts_ns is None:
            return None
        with self.lock:
            return self.legacy_values.get(pts_ns)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def health(
    config: CabinAnnotationConfig,
    status: str,
    frames: int,
    observations: int,
    diagnostics: list[str],
    joiner: Optional[FrameResultJoiner] = None,
    identity: Optional[FrameIdentityManager] = None,
) -> InferenceHealth:
    metrics = joiner.metrics if joiner is not None else None
    return InferenceHealth(
        status=status,
        camera_id="cabin",
        source_kind="live_rtsp",
        source=config.source,
        model_name="mediapipe-facemesh",
        model_version="legacy-compatible",
        frames=frames,
        detections=observations,
        last_update_utc=utc_now(),
        diagnostics=diagnostics,
        annotated_stream_enabled=config.enabled,
        annotated_publisher=config.annotated_rtsp_url if config.enabled else "disabled",
        exact_frame_matches=metrics.exact_matches if metrics else 0,
        expired_frame_results=metrics.expired_frames if metrics else 0,
        unmatched_observations=metrics.unmatched_results if metrics else 0,
        late_observations=metrics.late_results if metrics else 0,
        duplicate_pts=identity.duplicate_pts if identity else 0,
        pts_discontinuities=identity.discontinuities if identity else 0,
        missing_pts=identity.missing_pts if identity else 0,
    )


def pipeline_description(config: CabinAnnotationConfig) -> str:
    return (
        f'rtspsrc location="{config.source}" latency=200 protocols=tcp ! '
        "rtph264depay ! h264parse ! nvv4l2decoder ! queue ! mux.sink_0 "
        "nvstreammux name=mux batch-size=1 width=1920 height=1080 live-source=true batched-push-timeout=40000 ! "
        "tee name=frames "
        "frames. ! queue max-size-buffers=2 leaky=downstream ! nvstreamdemux name=demux "
        "demux.src_0 ! nvvideoconvert ! video/x-raw,format=BGR ! "
        "appsink name=face-sink emit-signals=true max-buffers=2 drop=true sync=false "
        f"frames. ! queue max-size-buffers=2 leaky=downstream ! nvdsosd name=cabin-osd process-mode=1 display-bbox=0 display-text=1 ! "
        "nvvideoconvert ! video/x-raw(memory:NVMM),format=NV12 ! "
        f"nvv4l2h264enc bitrate={config.bitrate} iframeinterval=30 ! h264parse config-interval=1 ! "
        f'rtspclientsink location="{config.annotated_rtsp_url}" protocols=tcp'
    )


def run(config: CabinAnnotationConfig, identity_path: Path, stop: Event) -> int:
    writer = ArtifactWriter(Path(config.output_path), Path(config.health_path))
    if not config.enabled:
        writer.health(health(config, "blocked", 0, 0, ["cabin annotated stream is disabled by configuration"]))
        return 0
    if importlib.util.find_spec("pyds") is None:
        writer.health(health(config, "blocked", 0, 0, ["DeepStream Python bindings pyds are unavailable"]))
        return 3
    try:
        import cv2
        import gi
        import mediapipe as mp
        import numpy as np

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        import pyds
    except ImportError as error:
        writer.health(health(config, "blocked", 0, 0, [f"cabin annotation runtime unavailable: {error}"]))
        return 3
    sys.path.insert(0, config.app_root)
    from detectors.FaceLandmarkDetector import FaceLandmarkDetector

    Gst.init(None)
    pipeline = Gst.parse_launch(pipeline_description(config))
    sink = pipeline.get_by_name("face-sink")
    osd = pipeline.get_by_name("cabin-osd")
    mux = pipeline.get_by_name("mux")
    if sink is None or osd is None or mux is None:
        writer.health(health(config, "error", 0, 0, ["cabin annotation pipeline is missing required elements"]))
        return 4
    device_id, unit_no = identity_values(identity_path)
    store = RuntimeStore(Path(config.database_path))
    composer = OverlayComposer(
        store,
        "cabin",
        device_id,
        unit_no,
        config.osd_font_size,
        config.osd_safe_margin,
        config.diagnostics,
        config.telemetry_max_age_seconds,
        cache=TelemetryCache(),
    )
    composer.start(store.latest_aggregate)
    detector = FaceLandmarkDetector(mp, config.face_config)
    frames = 0
    observations = 0
    sample_queue: "Queue[Tuple[FrameRef, object]]" = Queue(maxsize=2)
    joiner = FrameResultJoiner(limit=64)
    identity = FrameIdentityManager("cabin")
    sample_frame_refs: Dict[int, Deque[FrameRef]] = {}
    osd_frame_refs: Dict[int, Deque[FrameRef]] = {}
    stream_generation = uuid.uuid4().hex

    def on_sample(appsink):
        sample = appsink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.ERROR
        buffer = sample.get_buffer()
        caps = sample.get_caps().get_structure(0)
        width = int(caps.get_value("width"))
        height = int(caps.get_value("height"))
        ok, mapped = buffer.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.OK
        try:
            frame = np.frombuffer(mapped.data, dtype=np.uint8).reshape((height, width, 3)).copy()
            pts_ns = None if buffer.pts == Gst.CLOCK_TIME_NONE else int(buffer.pts)
            frame_ref = None
            if pts_ns is not None and sample_frame_refs.get(pts_ns):
                frame_ref = sample_frame_refs[pts_ns].popleft()
                if not sample_frame_refs[pts_ns]:
                    del sample_frame_refs[pts_ns]
            if frame_ref is not None:
                try:
                    sample_queue.put_nowait((frame_ref, frame))
                except Full:
                    pass
        finally:
            buffer.unmap(mapped)
        return Gst.FlowReturn.OK

    def process_samples() -> None:
        nonlocal observations
        next_sample_at = 0.0
        while not stop.is_set():
            try:
                frame_ref, frame = sample_queue.get(timeout=0.2)
            except Exception:
                continue
            now = time.monotonic()
            if now < next_sample_at:
                continue
            next_sample_at = now + config.sample_interval_seconds
            started = time.monotonic_ns()
            height, width = frame.shape[:2]
            result = detector.detect(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), (height, width), config.roi)
            ear = None if result.ear[0] < 0 or result.ear[1] < 0 else (result.ear[0] + result.ear[1]) / 2
            face_box = None
            if result.faceroi is not None:
                (left, top), (right, bottom) = result.faceroi
                face_box = BoundingBox(
                    left=max(0.0, min(1.0, left / width)),
                    top=max(0.0, min(1.0, top / height)),
                    width=max(0.001, min(1.0, (right - left) / width)),
                    height=max(0.001, min(1.0, (bottom - top) / height)),
                )
            observation = FatigueObservation(
                observation_id=f"cabin-{uuid.uuid4().hex}",
                observed_at_utc=utc_now(),
                frame_id=f"cabin-{frame_ref.frame_seq}",
                stream_generation=stream_generation,
                frame_ref=frame_ref,
                media_pts_ns=frame_ref.media_pts_ns,
                face_present=result.face is not None,
                face_box=face_box,
                closed_eyes=result.isclosedeye,
                yawning=result.isyawning,
                ear=ear,
                mar=result.mar if result.mar >= 0 else None,
                latency_ms=max(0.0, (time.monotonic_ns() - started) / 1_000_000),
                observation_type="EXACT_INFERRED",
            )
            joiner.register_inference(frame_ref, observation)
            writer.event(observation)
            observations += 1

    sink.connect("new-sample", on_sample)
    worker = threading.Thread(target=process_samples, name="mh02-cabin-mediapipe", daemon=True)
    worker.start()

    def on_mux(_pad, info):
        buffer = info.get_buffer()
        if buffer is None:
            return Gst.PadProbeReturn.OK
        pts_ns = None if buffer.pts == Gst.CLOCK_TIME_NONE else int(buffer.pts)
        previous_epoch = identity.stream_epoch
        frame_ref = identity.register(
            pts_ns,
            capture_utc=utc_now(),
            capture_monotonic_ns=time.monotonic_ns(),
            timestamp_source="ingest_estimate",
            utc_uncertainty_ms=100.0,
        )
        if frame_ref.stream_epoch != previous_epoch:
            joiner.invalidate_epoch(frame_ref.stream_epoch)
            sample_frame_refs.clear()
            osd_frame_refs.clear()
        if pts_ns is not None:
            sample_frame_refs.setdefault(pts_ns, deque()).append(frame_ref)
            osd_frame_refs.setdefault(pts_ns, deque()).append(frame_ref)
        joiner.register_video(frame_ref, time.monotonic_ns() + config.max_sync_age_ms * 1_000_000)
        return Gst.PadProbeReturn.OK

    def on_osd(_pad, info):
        nonlocal frames
        buffer = info.get_buffer()
        if buffer is None:
            return Gst.PadProbeReturn.OK
        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(buffer))
        if batch_meta is None:
            return Gst.PadProbeReturn.OK
        frame_list = batch_meta.frame_meta_list
        while frame_list is not None:
            try:
                frame_meta = pyds.NvDsFrameMeta.cast(frame_list.data)
            except StopIteration:
                break
            frames += 1
            pts_ns = int(frame_meta.buf_pts) if frame_meta.buf_pts != Gst.CLOCK_TIME_NONE else None
            frame_ref = None
            if pts_ns is not None and osd_frame_refs.get(pts_ns):
                frame_ref = osd_frame_refs[pts_ns].popleft()
                if not osd_frame_refs[pts_ns]:
                    del osd_frame_refs[pts_ns]
            joiner.expire()
            observation = joiner.release(frame_ref) if frame_ref is not None else None
            composer.add_display_meta(pyds, batch_meta, frame_meta, frame_ref)
            display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
            display_meta.num_labels = 1
            display_meta.num_rects = 0
            text = display_meta.text_params[0]
            text.x_offset = config.osd_safe_margin
            text.y_offset = config.osd_safe_margin + 4 * (config.osd_font_size + 8)
            text.font_params.font_name = "Sans"
            text.font_params.font_size = config.osd_font_size
            text.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)
            text.set_bg_clr = 1
            text.text_bg_clr.set(0.0, 0.0, 0.0, 0.65)
            if observation is None:
                text.display_text = "FATIGUE AI UNAVAILABLE/DELAYED"
            else:
                text.display_text = f"FATIGUE {'ALERT' if observation.closed_eyes or observation.yawning else 'NORMAL'} EAR:{observation.ear if observation.ear is not None else '--'} MAR:{observation.mar if observation.mar is not None else '--'}"
                if observation.face_box is not None:
                    display_meta.num_rects = 1
                    rect = display_meta.rect_params[0]
                    rect.left = observation.face_box.left * 1920
                    rect.top = observation.face_box.top * 1080
                    rect.width = observation.face_box.width * 1920
                    rect.height = observation.face_box.height * 1080
                    rect.border_width = 3
                    rect.border_color.set(1.0, 0.7 if observation.closed_eyes else 1.0, 0.2, 1.0)
            pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)
            frame_list = frame_list.next
        return Gst.PadProbeReturn.OK

    mux.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, on_mux)
    osd.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, on_osd)
    pipeline.set_state(Gst.State.PLAYING)
    writer.health(health(config, "running", 0, 0, ["DeepStream cabin annotated pipeline is running"]))
    bus = pipeline.get_bus()
    try:
        while not stop.is_set():
            message = bus.timed_pop_filtered(250_000_000, Gst.MessageType.ERROR | Gst.MessageType.EOS)
            if message is None:
                continue
            if message.type == Gst.MessageType.EOS:
                break
            error, detail = message.parse_error()
            writer.health(health(config, "error", frames, observations, [f"GStreamer error: {error} ({detail})"]))
            return 5
    finally:
        stop.set()
        pipeline.set_state(Gst.State.NULL)
        worker.join(timeout=2)
        composer.stop()
        writer.health(health(config, "stopped", frames, observations, ["cabin annotation pipeline stopped"], joiner, identity))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="MH02 DeepStream cabin annotation service")
    result.add_argument("--config-path", type=Path, default=Path("/etc/mh02/config.json"))
    return result


def main() -> int:
    configure_logging("mh02.cabin-annotation")
    args = parser().parse_args()
    config = ConfigStore(args.config_path).snapshot().config
    stop = Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    return run(config.cabin_annotation, Path(config.inference.identity_path), stop)


if __name__ == "__main__":
    raise SystemExit(main())
