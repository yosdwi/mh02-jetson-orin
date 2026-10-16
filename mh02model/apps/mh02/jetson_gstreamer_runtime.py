#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import logging
import re
import signal
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit


LOGGER = logging.getLogger("jetson_gstreamer_runtime")
CONFIG_DIR = Path(__file__).resolve().parents[2] / "files" / "configs"
REQUIRED_ELEMENTS = (
    "h264parse",
    "nvvidconv",
    "nvv4l2h264enc",
    "rtph264pay",
)
RTSP_ELEMENTS = ("rtspsrc", "rtph264depay", "nvv4l2decoder")
USB_ELEMENTS = ("v4l2src", "jpegparse", "nvv4l2decoder")


@dataclass(frozen=True)
class RuntimeConfig:
    camera_id: str
    source: str
    input_url: str | None
    device: str
    width: int
    height: int
    framerate: int
    mount: str
    bind_address: str
    port: int
    latency_ms: int
    bitrate: int
    iframe_interval: int
    record_dir: Path | None
    segment_seconds: int


def parse_key_value_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    return values


def parse_config_file(path: Path) -> dict[str, str]:
    if path.suffix.lower() == ".json":
        values = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(values, dict):
            raise ValueError(f"Expected an object in config file: {path}")
        return {str(key): str(value) for key, value in values.items()}
    return parse_key_value_file(path)


def redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<invalid-url>"
    if parsed.password is None:
        return value
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    user = parsed.username or ""
    netloc = f"{user}:<redacted>@{host}"
    redacted = SplitResult(parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
    return urlunsplit(redacted)


def validate_mount(mount: str) -> str:
    normalized = mount if mount.startswith("/") else f"/{mount}"
    if not re.fullmatch(r"/[A-Za-z0-9._/-]+", normalized):
        raise ValueError(f"Invalid RTSP mount path: {mount!r}")
    return normalized


def escape_launch_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def resolve_input_url(camera_id: str, explicit_url: str | None, config: dict[str, str]) -> str:
    if explicit_url:
        return explicit_url
    candidates = {
        "front": ("CAM_URL", "front_cam_stream", "front_cam"),
        "cabin": ("CAM_URL", "cabin_cam_stream", "cabin_cam"),
    }.get(camera_id)
    if candidates is None:
        raise ValueError("camera-id must be 'front' or 'cabin'")
    for key in candidates:
        value = config.get(key)
        if value:
            return value
    raise ValueError(f"No RTSP URL found for {camera_id!r} in the MH02 config")


def build_pipeline(config: RuntimeConfig) -> str:
    if config.source == "usb":
        source = (
            f'v4l2src device="{escape_launch_value(config.device)}" io-mode=2 '
            f"! image/jpeg,width={config.width},height={config.height},framerate={config.framerate}/1"
        )
        decode = (
            "jpegparse ! nvv4l2decoder mjpeg=1 ! nvvidconv ! "
            "video/x-raw(memory:NVMM),format=NV12"
        )
    else:
        if config.input_url is None:
            raise ValueError("RTSP mode requires --input-url or a camera config")
        source = (
            f'rtspsrc location="{escape_launch_value(config.input_url)}" '
            f"protocols=tcp latency={config.latency_ms}"
        )
        decode = (
            "rtph264depay ! h264parse ! nvv4l2decoder ! nvvidconv ! "
            "video/x-raw(memory:NVMM),format=NV12"
        )
    encode = (
        f"nvv4l2h264enc bitrate={config.bitrate} "
        f"iframeinterval={config.iframe_interval} ! h264parse config-interval=1"
    )
    rtsp_payloader = "rtph264pay name=pay0 pt=96 config-interval=1"

    if config.record_dir is None:
        return (
            f"( {source} ! {decode} ! queue max-size-buffers=4 leaky=downstream ! "
            f"{encode} ! {rtsp_payloader} )"
        )

    location = config.record_dir / f"{config.camera_id}-%05d.mp4"
    rtsp_branch = (
        "encoded. ! queue max-size-buffers=4 leaky=downstream ! "
        f"{rtsp_payloader}"
    )
    record_branch = (
        "encoded. ! queue max-size-buffers=8 leaky=downstream ! "
        f"splitmuxsink muxer-factory=mp4mux max-size-time={config.segment_seconds * 1_000_000_000} "
        f'location="{escape_launch_value(str(location))}" async-finalize=true'
    )
    return (
        f"( {source} ! {decode} ! queue max-size-buffers=4 leaky=downstream ! "
        f"{encode} ! tee name=encoded {rtsp_branch} {record_branch} )"
    )


def build_safe_pipeline(config: RuntimeConfig) -> str:
    if config.input_url is None:
        return build_pipeline(config)
    return build_pipeline(replace(config, input_url=redact_url(config.input_url)))


def build_runtime_config(args: argparse.Namespace) -> RuntimeConfig:
    if args.source == "usb":
        config_values = {}
    elif args.input_url:
        config_values = {}
    else:
        config_path = args.config or {
            "front": CONFIG_DIR / "mh02_front.json",
            "cabin": CONFIG_DIR / "mh02_cabin_old.json",
        }[args.camera_id]
        config_values = parse_config_file(config_path)
    input_url = None if args.source == "usb" else resolve_input_url(args.camera_id, args.input_url, config_values)
    record_dir = Path(args.record_dir).expanduser() if args.record_dir else None
    if record_dir is not None:
        record_dir.mkdir(parents=True, exist_ok=True)
    return RuntimeConfig(
        camera_id=args.camera_id,
        source=args.source,
        input_url=input_url,
        device=args.device,
        width=args.width,
        height=args.height,
        framerate=args.framerate,
        mount=validate_mount(args.mount or f"/{args.camera_id}"),
        bind_address=args.bind_address,
        port=args.port,
        latency_ms=args.latency_ms,
        bitrate=args.bitrate,
        iframe_interval=args.iframe_interval,
        record_dir=record_dir,
        segment_seconds=args.segment_seconds,
    )


def load_gst() -> tuple[Any, Any, Any]:
    try:
        import gi

        gi.require_version("Gst", "1.0")
        gi.require_version("GstRtspServer", "1.0")
        gi.require_version("GLib", "2.0")
        from gi.repository import GLib, Gst, GstRtspServer
    except (ImportError, ValueError) as exc:
        raise RuntimeError(
            "GObject introspection bindings for Gst/GstRtspServer are required on the Jetson"
        ) from exc
    Gst.init(None)
    return GLib, Gst, GstRtspServer


def check_required_elements(gst: Any, source: str, include_recording: bool) -> list[str]:
    required = list(REQUIRED_ELEMENTS)
    required.extend(USB_ELEMENTS if source == "usb" else RTSP_ELEMENTS)
    if include_recording:
        required.append("splitmuxsink")
    return [name for name in required if gst.ElementFactory.find(name) is None]


def run_server(config: RuntimeConfig) -> int:
    glib, gst, rtsp_server_module = load_gst()
    missing = check_required_elements(gst, config.source, config.record_dir is not None)
    if missing:
        raise RuntimeError("Missing GStreamer elements on target: " + ", ".join(missing))

    pipeline = build_pipeline(config)
    server = rtsp_server_module.RTSPServer()
    server.set_address(config.bind_address)
    server.set_service(str(config.port))
    mounts = server.get_mount_points()
    factory = rtsp_server_module.RTSPMediaFactory()
    factory.set_launch(pipeline)
    factory.set_shared(True)
    mounts.add_factory(config.mount, factory)
    if server.attach(None) == 0:
        raise RuntimeError("Could not attach the RTSP server")

    loop = glib.MainLoop()

    def stop_loop(_signum: int, _frame: Any) -> None:
        glib.idle_add(loop.quit)

    signal.signal(signal.SIGINT, stop_loop)
    signal.signal(signal.SIGTERM, stop_loop)
    LOGGER.info("RTSP output: rtsp://<jetson-ip>:%s%s", config.port, config.mount)
    if config.source == "usb":
        LOGGER.info("USB input: %s", config.device)
    else:
        LOGGER.info("RTSP input: %s", redact_url(config.input_url or ""))
    LOGGER.info("Pipeline: %s", build_safe_pipeline(config))
    loop.run()
    return 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jetson hardware RTSP relay for one MH02 camera")
    parser.add_argument("--camera-id", choices=("front", "cabin"), required=True)
    parser.add_argument("--source", choices=("usb", "rtsp"), default="usb")
    parser.add_argument("--input-url", help="Override the URL from mh02.conf")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--device", default="/dev/video0")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--framerate", type=int, default=30)
    parser.add_argument("--mount", help="RTSP mount path; defaults to /<camera-id>")
    parser.add_argument("--bind-address", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8554)
    parser.add_argument("--latency-ms", type=int, default=200)
    parser.add_argument("--bitrate", type=int, default=2_000_000)
    parser.add_argument("--iframe-interval", type=int, default=30)
    parser.add_argument("--record-dir", help="Enable segmented MP4 recording")
    parser.add_argument("--segment-seconds", type=int, default=60)
    parser.add_argument("--print-pipeline", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-elements", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = create_parser().parse_args(argv)
    try:
        config = build_runtime_config(args)
        pipeline = build_safe_pipeline(config)
        if args.print_pipeline or args.dry_run:
            print(pipeline)
        if args.dry_run:
            return 0
        if args.check_elements:
            _, gst, _ = load_gst()
            missing = check_required_elements(gst, config.source, config.record_dir is not None)
            if missing:
                print("missing: " + ", ".join(missing))
                return 2
            print("all required elements available")
            return 0
        return run_server(config)
    except (OSError, RuntimeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
