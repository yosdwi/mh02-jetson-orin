from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import os
import signal
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Dict, List, Optional, Type, Union

from pydantic import BaseModel, ValidationError

from .configuration import ConfigStore, InferenceConfig
from .diagnostics import configure_logging
from .inference_contracts import BoundingBox, DetectionObservation, FrontValidationReport, InferenceCapabilities, InferenceHealth
from .warning_engine import AdvisoryPolicy, WarningCandidate, candidates_for


LOGGER = logging.getLogger("mh02.front-inference")
MAX_LATENCIES = 256


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def plugin_available(name: str) -> bool:
    try:
        result = subprocess.run(
            ["gst-inspect-1.0", name],
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def installed_version(package: str) -> Optional[str]:
    if package == "deepstream-6.2" and os.environ.get("MH02_DEEPSTREAM_VERSION"):
        return os.environ["MH02_DEEPSTREAM_VERSION"]
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Version}", package],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def capabilities() -> InferenceCapabilities:
    diagnostics: List[str] = []
    deepstream = plugin_available("nvstreammux")
    nvinfer = plugin_available("nvinfer")
    nvtracker = plugin_available("nvtracker")
    pyds = importlib.util.find_spec("pyds") is not None
    if not deepstream:
        diagnostics.append("nvstreammux GStreamer plugin is unavailable")
    if not nvinfer:
        diagnostics.append("nvinfer GStreamer plugin is unavailable")
    if not nvtracker:
        diagnostics.append("nvtracker GStreamer plugin is unavailable")
    if not pyds:
        diagnostics.append("DeepStream Python bindings pyds are unavailable")
    return InferenceCapabilities(
        deepstream_available=deepstream,
        nvinfer_available=nvinfer,
        nvtracker_available=nvtracker,
        pyds_available=pyds,
        installed_deepstream_version=installed_version("deepstream-6.2"),
        tensor_rt_version=installed_version("tensorrt"),
        diagnostics=tuple(diagnostics),
    )


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def process_rss_mb() -> Optional[float]:
    try:
        pages = int(Path("/proc/self/statm").read_text(encoding="ascii").split()[1])
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (OSError, IndexError, ValueError):
        return None
    return pages * page_size / (1024 * 1024)


def gpu_load_percent() -> Optional[float]:
    for path in (Path("/sys/devices/gpu.0/load"), Path("/sys/devices/platform/gpu.0/load")):
        try:
            raw = int(path.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            continue
        return min(100.0, max(0.0, raw / 10.0))
    return None


def read_health(path: Path) -> Optional[InferenceHealth]:
    try:
        return InferenceHealth.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError):
        return None


def read_events(path: Path, model: Type[BaseModel], limit: int = 100) -> List[BaseModel]:
    if not path.exists():
        return []
    events: List[BaseModel] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-limit:]:
        try:
            events.append(model.model_validate_json(line))
        except (ValueError, ValidationError):
            continue
    return events


def validation_report(health: Optional[InferenceHealth], detections: int, warnings: int) -> FrontValidationReport:
    if health is None:
        return FrontValidationReport(
            created_at_utc=utc_now(),
            status="BLOCKED",
            inference_status="not_running",
            diagnostics=["front inference health artifact is not available"],
        )
    if health.status == "running" and health.frames > 0:
        status = "PASS"
    elif health.status in ("error", "stopped"):
        status = "FAIL"
    else:
        status = "BLOCKED"
    return FrontValidationReport(
        created_at_utc=utc_now(),
        status=status,
        source_kind=health.source_kind,
        source=health.source,
        inference_status=health.status,
        frames=health.frames,
        detections=detections,
        warnings=warnings,
        diagnostics=health.diagnostics,
    )


class OutputWriter:
    def __init__(self, output_path: Path, health_path: Path) -> None:
        self.output_path = output_path
        self.health_path = health_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.health_path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, payload: Union[DetectionObservation, WarningCandidate]) -> None:
        serialized = payload.model_dump_json()
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(serialized + "\n")

    def health(self, payload: InferenceHealth) -> None:
        fd, temporary = tempfile.mkstemp(prefix="mh02-inference-", suffix=".json", dir=self.health_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload.model_dump_json(indent=2))
                handle.write("\n")
            os.replace(temporary, self.health_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def pipeline_description(config: InferenceConfig) -> str:
    if config.source_kind == "live_rtsp":
        source = (
            f'rtspsrc location="{config.source}" latency=200 protocols=tcp ! '
            "rtph264depay ! h264parse ! nvv4l2decoder ! queue ! mux.sink_0"
        )
        live_source = "true"
    else:
        source = (
            f'filesrc location="{config.source}" ! qtdemux name=demux '
            "demux.video_0 ! queue ! h264parse ! nvv4l2decoder ! queue ! mux.sink_0"
        )
        live_source = "false"
    return (
        f"{source} nvstreammux name=mux batch-size=1 width=1920 height=1080 "
        f"live-source={live_source} batched-push-timeout=40000 ! "
        f'nvinfer name=front-pgie config-file-path="{config.model_config_path}" ! '
        f'nvtracker name=front-tracker ll-lib-file="{config.tracker_lib_path}" '
        f'll-config-file="{config.tracker_config_path}" ! fakesink name=front-sink sync=false'
    )


class InferenceRun:
    def __init__(self, config: InferenceConfig, writer: OutputWriter, stop: Event) -> None:
        self.config = config
        self.writer = writer
        self.stop = stop
        self.model_digest = file_digest(Path(config.engine_path))
        self.frames = 0
        self.detections = 0
        self.dropped_frames = 0
        self.started_monotonic = time.monotonic()
        self.received_pts: Dict[int, int] = {}
        self.latencies: List[float] = []
        self.last_media_pts_ns: Optional[int] = None
        self.last_health_write = 0.0

    def health(self, status: str, diagnostics: Optional[List[str]] = None) -> InferenceHealth:
        elapsed = max(0.001, time.monotonic() - self.started_monotonic)
        sorted_latencies = sorted(self.latencies)
        p95 = sorted_latencies[min(len(sorted_latencies) - 1, int(len(sorted_latencies) * 0.95))] if sorted_latencies else None
        return InferenceHealth(
            status=status,
            source_kind=self.config.source_kind,
            source=self.config.source,
            model_name=self.config.front_model,
            model_version=self.config.front_model_version,
            model_digest_sha256=self.model_digest,
            deepstream_version=installed_version("deepstream-6.2"),
            frames=self.frames,
            detections=self.detections,
            dropped_frames=self.dropped_frames,
            fps=self.frames / elapsed,
            latency_p95_ms=p95,
            process_rss_mb=process_rss_mb(),
            gpu_utilization_percent=gpu_load_percent(),
            last_media_pts_ns=self.last_media_pts_ns,
            last_update_utc=utc_now(),
            diagnostics=diagnostics or [],
        )

    def write_health(self, status: str, diagnostics: Optional[List[str]] = None, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self.last_health_write >= 1.0:
            self.writer.health(self.health(status, diagnostics))
            self.last_health_write = now

    def record_frame(self, pts_ns: int) -> None:
        self.frames += 1
        self.last_media_pts_ns = pts_ns
        self.received_pts[pts_ns] = time.monotonic_ns()
        self.write_health("running")

    def record_detection(self, observation: DetectionObservation) -> None:
        self.detections += 1
        if observation.media_pts_ns is not None:
            received = self.received_pts.get(observation.media_pts_ns)
            if received is not None:
                latency = max(0.0, (time.monotonic_ns() - received) / 1_000_000)
                self.latencies.append(latency)
                del self.received_pts[observation.media_pts_ns]
                deltas = self.latencies[-MAX_LATENCIES:]
                self.latencies = deltas
        self.writer.event(observation)
        policy = AdvisoryPolicy(confidence_threshold=self.config.confidence_threshold, classes=self.config.warning_classes)
        for candidate in candidates_for((observation,), policy):
            self.writer.event(candidate)
        self.write_health("running")


def run_pipeline(config: InferenceConfig, output_path: Path, health_path: Path, stop: Event) -> int:
    available = capabilities()
    writer = OutputWriter(output_path, health_path)
    model_path = Path(config.engine_path)
    if not config.enabled:
        writer.health(
            InferenceHealth(
                status="blocked",
                source_kind=config.source_kind,
                source=config.source,
                model_name=config.front_model,
                model_version=config.front_model_version,
                last_update_utc=utc_now(),
                diagnostics=["front inference is disabled by configuration"],
            ),
        )
        return 0
    if not model_path.exists():
        writer.health(
            InferenceHealth(
                status="blocked",
                source_kind=config.source_kind,
                source=config.source,
                model_name=config.front_model,
                model_version=config.front_model_version,
                last_update_utc=utc_now(),
                diagnostics=[f"TensorRT engine is missing: {model_path}"],
            ),
        )
        return 2
    if not all((available.deepstream_available, available.nvinfer_available, available.nvtracker_available, available.pyds_available)):
        writer.health(
            InferenceHealth(
                status="blocked",
                source_kind=config.source_kind,
                source=config.source,
                model_name=config.front_model,
                model_version=config.front_model_version,
                model_digest_sha256=file_digest(model_path),
                deepstream_version=available.installed_deepstream_version,
                last_update_utc=utc_now(),
                diagnostics=list(available.diagnostics),
            ),
        )
        return 3
    if not Path(config.model_config_path).exists():
        raise FileNotFoundError(config.model_config_path)
    if not Path(config.tracker_config_path).exists():
        raise FileNotFoundError(config.tracker_config_path)
    try:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        import pyds
    except ImportError as error:
        writer.health(
            InferenceHealth(
                status="blocked",
                source_kind=config.source_kind,
                source=config.source,
                model_name=config.front_model,
                model_version=config.front_model_version,
                model_digest_sha256=file_digest(model_path),
                last_update_utc=utc_now(),
                diagnostics=[f"DeepStream Python runtime unavailable: {error}"],
            ),
        )
        return 4
    Gst.init(None)
    run = InferenceRun(config, writer, stop)
    writer.health(run.health("starting", ["DeepStream pipeline is starting"]))
    pipeline = Gst.parse_launch(pipeline_description(config))
    mux = pipeline.get_by_name("mux")
    tracker = pipeline.get_by_name("front-tracker")
    if mux is None or tracker is None:
        raise RuntimeError("DeepStream pipeline did not create nvstreammux and nvtracker")

    def on_mux(_pad, info):
        buffer = info.get_buffer()
        if buffer is not None and buffer.pts != Gst.CLOCK_TIME_NONE:
            run.record_frame(int(buffer.pts))
        return Gst.PadProbeReturn.OK

    def on_tracker(_pad, info):
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
            frame_width = max(1.0, float(frame_meta.source_frame_width or 1920))
            frame_height = max(1.0, float(frame_meta.source_frame_height or 1080))
            pts_ns = int(frame_meta.buf_pts) if frame_meta.buf_pts != Gst.CLOCK_TIME_NONE else None
            object_list = frame_meta.obj_meta_list
            while object_list is not None:
                try:
                    object_meta = pyds.NvDsObjectMeta.cast(object_list.data)
                except StopIteration:
                    break
                rect = object_meta.rect_params
                left = min(1.0, max(0.0, float(rect.left) / frame_width))
                top = min(1.0, max(0.0, float(rect.top) / frame_height))
                width = min(1.0 - left, max(0.0001, float(rect.width) / frame_width))
                height = min(1.0 - top, max(0.0001, float(rect.height) / frame_height))
                raw_track = int(object_meta.object_id)
                track_id = None if raw_track >= 0xFFFFFFFFFFFFFF00 else str(raw_track)
                observation = DetectionObservation(
                    observation_id=f"detection-{uuid.uuid4().hex}",
                    observed_at_utc=utc_now(),
                    source_kind=config.source_kind,
                    frame_id=f"front-{int(frame_meta.frame_num)}",
                    media_pts_ns=pts_ns,
                    object_class=str(object_meta.obj_label),
                    confidence=float(object_meta.confidence),
                    bounding_box=BoundingBox(left=left, top=top, width=width, height=height),
                    track_id=track_id,
                    model_name=config.front_model,
                    model_version=config.front_model_version,
                    model_digest_sha256=run.model_digest,
                )
                run.record_detection(observation)
                object_list = object_list.next
            frame_list = frame_list.next
        return Gst.PadProbeReturn.OK

    mux.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, on_mux)
    tracker.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, on_tracker)
    bus = pipeline.get_bus()
    pipeline.set_state(Gst.State.PLAYING)
    try:
        while not stop.is_set():
            message = bus.timed_pop_filtered(250_000_000, Gst.MessageType.ERROR | Gst.MessageType.EOS)
            if message is None:
                continue
            if message.type == Gst.MessageType.EOS:
                break
            error, detail = message.parse_error()
            run.write_health("error", [f"GStreamer error: {error} ({detail})"], force=True)
            return 5
    finally:
        pipeline.set_state(Gst.State.NULL)
        run.write_health("stopped", ["inference pipeline stopped"], force=True)
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="MH02 DeepStream front inference service")
    result.add_argument("--config-path", type=Path, default=Path("/etc/mh02/config.json"))
    result.add_argument("--capabilities", action="store_true")
    result.add_argument("--source-kind", choices=("live_rtsp", "replay_mp4"))
    result.add_argument("--source")
    result.add_argument("--output-path", type=Path)
    result.add_argument("--health-path", type=Path)
    return result


def main() -> int:
    configure_logging("mh02.front-inference")
    args = parser().parse_args()
    if args.capabilities:
        print(capabilities().model_dump_json(indent=2))
        return 0
    config = ConfigStore(args.config_path).snapshot().config.inference
    if args.source_kind is not None:
        config = config.model_copy(update={"source_kind": args.source_kind})
    if args.source is not None:
        config = config.model_copy(update={"source": args.source})
    output_path = args.output_path or Path(config.output_path)
    health_path = args.health_path or Path(config.health_path)
    stop = Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    return run_pipeline(config, output_path, health_path, stop)


if __name__ == "__main__":
    raise SystemExit(main())
