from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Optional

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gst

from .models import AggregateSample
from .store import RuntimeStore, utc_now


LOGGER = logging.getLogger("mh02.vlog")


def nmea_coordinate(value: Optional[float], latitude: bool) -> str:
    if value is None:
        return "--"
    absolute = abs(float(value))
    degrees = int(absolute)
    minutes = f"{(absolute - degrees) * 60:.4f}".zfill(7)
    degree_text = str(degrees).zfill(2 if latitude else 3)
    positive = "N" if latitude else "E"
    negative = "S" if latitude else "W"
    return f"{degree_text}{minutes} {negative if value < 0 else positive}"


def overlay_lines(sample: AggregateSample):
    gps = sample.gps if sample.gps and sample.gps.valid else None
    speed = "---" if gps is None or gps.speed_kph is None else str(round(gps.speed_kph)).zfill(3)
    payload = sample.redis_payload
    acceleration = next(
        (payload.get(key) for key in ("acceleration", "acc", "ACC", "acc_status") if payload.get(key) is not None),
        None,
    )
    if isinstance(acceleration, bool):
        acceleration_text = "ON" if acceleration else "OFF"
    elif acceleration is None:
        acceleration_text = "ON" if gps is not None else "--"
    else:
        acceleration_text = str(acceleration).upper()
    channel = payload.get("channel") or payload.get("channel_no") or "CH1"
    channel_text = str(channel).upper()
    if not channel_text.startswith("CH"):
        channel_text = f"CH{channel_text}"
    local_timestamp = sample.timestamp_utc.astimezone().strftime("%d-%m-%Y %H:%M:%S")
    return (
        f"{nmea_coordinate(gps.latitude if gps else None, True)}, {nmea_coordinate(gps.longitude if gps else None, False)}, {speed}KM/H ACC:{acceleration_text}",
        f"ID: {sample.device_id or '--'} Name: {sample.unit_no or '--'}",
        f"{local_timestamp} {sample.unit_no or '--'} {channel_text}",
    )


def timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{remaining:06.3f}"


class SubtitleWriter:
    def __init__(self, store: RuntimeStore, directory: Path, camera_id: str) -> None:
        self.store = store
        self.directory = directory
        self.camera_id = camera_id
        self.stop = Event()
        self.lock = threading.Lock()
        self.sequence = 0
        self.start_ns: Optional[int] = None
        self.end_ns: Optional[int] = None
        self.handle = None
        self.segment_path: Optional[Path] = None
        self.segment_start_utc: Optional[datetime] = None
        self.thread = threading.Thread(target=self._run, name="mh02-vtt", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def open(self, filename: str) -> None:
        with self.lock:
            self._close_locked()
            sidecar = Path(filename).with_suffix(".vtt")
            self.handle = sidecar.open("w", encoding="utf-8")
            self.handle.write("WEBVTT\n\n")
            self.handle.flush()
            self.start_ns = time.monotonic_ns()
            self.end_ns = None
            self.segment_path = Path(filename)
            self.segment_start_utc = utc_now()
            self._write_metadata(False, None)
            LOGGER.info("Opened telemetry track %s", sidecar)

    def close(self, complete: bool = True) -> None:
        with self.lock:
            if self.handle is None:
                return
            self.end_ns = time.monotonic_ns()
            self._write_metadata(complete, utc_now())
            self._close_locked()

    def _write_metadata(self, complete: bool, ended_at: Optional[datetime]) -> None:
        if self.segment_path is None or self.segment_start_utc is None:
            return
        payload = {
            "camera_id": self.camera_id,
            "filename": self.segment_path.name,
            "started_at_utc": self.segment_start_utc.isoformat(),
            "ended_at_utc": ended_at.isoformat() if ended_at else None,
            "duration_seconds": (self.end_ns - self.start_ns) / 1_000_000_000
            if ended_at and self.end_ns and self.start_ns
            else None,
            "complete": complete,
        }
        metadata_path = self.segment_path.with_suffix(".json")
        fd, temporary = tempfile.mkstemp(prefix="recording-", suffix=".json.tmp", dir=metadata_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"))
            os.replace(temporary, metadata_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _close_locked(self) -> None:
        if self.handle is not None:
            self.handle.flush()
            self.handle.close()
            self.handle = None
        self.start_ns = None
        self.end_ns = None
        self.segment_path = None
        self.segment_start_utc = None

    def _write(self, sample: AggregateSample) -> None:
        with self.lock:
            if self.handle is None or self.start_ns is None:
                return
            if sample.monotonic_ns < self.start_ns:
                return
            if self.end_ns is not None and sample.monotonic_ns > self.end_ns:
                return
            begin = (sample.monotonic_ns - self.start_ns) / 1_000_000_000
            end = begin + 1.2
            positions = (5, 12, 88)
            for index, (line, position) in enumerate(zip(overlay_lines(sample), positions)):
                self.handle.write(f"{sample.sequence}-{index}\n")
                self.handle.write(
                    f"{timestamp(begin)} --> {timestamp(end)} line:{position}% position:2% size:96% align:start\n"
                )
                self.handle.write(f"{line}\n\n")
            self.handle.flush()

    def _run(self) -> None:
        while not self.stop.wait(0.25):
            for sample in self.store.samples_after(self.sequence):
                self.sequence = sample.sequence
                self._write(sample)

    def shutdown(self) -> None:
        self.stop.set()
        self.thread.join(timeout=2)
        self.close(False)


def pipeline_description(args: argparse.Namespace) -> str:
    return (
        f"v4l2src device={args.device} io-mode=2 ! "
        f"image/jpeg,width={args.width},height={args.height},framerate={args.framerate}/1 ! "
        "jpegparse ! nvv4l2decoder mjpeg=1 ! nvvidconv ! "
        "video/x-raw(memory:NVMM),format=NV12 ! queue ! "
        f"nvv4l2h264enc bitrate={args.bitrate} iframeinterval={args.framerate} ! "
        "h264parse config-interval=1 ! tee name=encoded "
        f"encoded. ! queue ! h264parse ! splitmuxsink name=recorder muxer-factory=mp4mux "
        f"max-size-time={int(args.segment_seconds * 1_000_000_000)} async-finalize=true "
        'muxer-properties="properties,faststart=true" '
        f"location={args.record_dir / (args.camera_id + '-placeholder-%05d.mp4')} "
        f"encoded. ! queue ! h264parse ! hlssink2 target-duration=4 max-files=8 "
        f"playlist-length=5 location={args.hls_dir / (args.camera_id + '-%05d.ts')} "
        f"playlist-location={args.hls_dir / (args.camera_id + '.m3u8')} "
        f"encoded. ! queue ! h264parse config-interval=1 ! rtspclientsink location={args.rtsp_url} protocols=tcp"
    )


def location(message: Gst.Message) -> Optional[str]:
    structure = message.get_structure()
    if structure is None:
        return None
    value = structure.get_value("location")
    return str(value) if value else None


def run(args: argparse.Namespace, stop: Event) -> None:
    args.record_dir.mkdir(parents=True, exist_ok=True)
    args.hls_dir.mkdir(parents=True, exist_ok=True)
    Gst.init(None)
    store = RuntimeStore(Path(args.database))
    subtitles = SubtitleWriter(store, args.record_dir, args.camera_id)
    pipeline_text = pipeline_description(args)
    LOGGER.info("Starting GStreamer pipeline: %s", pipeline_text)
    pipeline = Gst.parse_launch(pipeline_text)
    recorder = pipeline.get_by_name("recorder")

    def format_location(_element: Gst.Element, fragment_id: int) -> str:
        stamp = utc_now().strftime("%Y%m%dT%H%M%S")
        return str(args.record_dir / f"{args.camera_id}-{stamp}-{int(fragment_id):05d}.mp4")

    recorder.connect("format-location", format_location)
    bus = pipeline.get_bus()
    bus.add_signal_watch()

    def on_message(_bus: Gst.Bus, message: Gst.Message) -> None:
        if message.type == Gst.MessageType.ERROR:
            error, detail = message.parse_error()
            LOGGER.error("GStreamer error: %s (%s)", error, detail)
            stop.set()
        elif message.type == Gst.MessageType.EOS:
            stop.set()
        elif message.type == Gst.MessageType.ELEMENT:
            if message.src.get_name() != "recorder":
                return
            name = message.get_structure().get_name() if message.get_structure() else ""
            path = location(message)
            if name == "splitmuxsink-fragment-opened" and path:
                subtitles.close()
                subtitles.open(path)

    bus.connect("message", on_message)
    subtitles.start()
    pipeline.set_state(Gst.State.PLAYING)
    loop = GLib.MainLoop()
    GLib.timeout_add(250, lambda: (loop.quit() or False) if stop.is_set() else True)
    try:
        loop.run()
    finally:
        pipeline.set_state(Gst.State.NULL)
        subtitles.shutdown()
        bus.remove_signal_watch()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="MH02 USB camera recorder and HLS service")
    result.add_argument("--database", default="/var/lib/mh02/state/mh02.sqlite3")
    result.add_argument("--device", default="/dev/video0")
    result.add_argument("--camera-id", default="front")
    result.add_argument("--record-dir", type=Path, default=Path("/var/lib/mh02/recordings/front"))
    result.add_argument("--hls-dir", type=Path, default=Path("/var/lib/mh02/hls"))
    result.add_argument("--width", type=int, default=1920)
    result.add_argument("--height", type=int, default=1080)
    result.add_argument("--framerate", type=int, default=30)
    result.add_argument("--bitrate", type=int, default=4_000_000)
    result.add_argument("--segment-seconds", type=float, default=600)
    result.add_argument("--rtsp-url", default="rtsp://127.0.0.1:8554/front")
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    run(parser().parse_args(), stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
