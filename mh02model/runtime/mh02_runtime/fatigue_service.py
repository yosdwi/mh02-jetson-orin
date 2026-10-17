from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Tuple

from .models import FatigueState
from .configuration import ConfigStore
from .diagnostics import configure_logging
from .store import RuntimeStore


LOGGER = logging.getLogger("mh02.fatigue")


def parse_roi(value: str) -> Tuple[int, int, int, int]:
    values = [int(item.strip()) for item in value.split(",")]
    if len(values) != 4:
        raise ValueError(f"Expected four ROI values, got {value!r}")
    return values[0], values[1], values[2], values[3]


def run(args: argparse.Namespace, stop: Event) -> None:
    if args.camera_id != "cabin" or "/front" in args.source:
        raise ValueError("Fatigue inference requires the explicit cabin camera source")
    import mediapipe as mp
    import cv2

    store = RuntimeStore(Path(args.database))
    sys.path.insert(0, str(Path(args.app_root)))
    from detectors.FaceLandmarkDetector import FaceLandmarkDetector

    detector = FaceLandmarkDetector(mp, args.face_config)
    capture = cv2.VideoCapture(args.source)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 2)
    next_sample = time.monotonic()
    frame_sequence = 0
    roi = parse_roi(args.roi)
    while not stop.is_set():
        ok, frame = capture.read()
        if not ok:
            LOGGER.warning("Fatigue stream read failed; reopening")
            capture.release()
            stop.wait(2)
            capture = cv2.VideoCapture(args.source)
            continue
        now = time.monotonic()
        if now < next_sample:
            continue
        next_sample = now + args.interval
        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = detector.detect(rgb_frame, (height, width), roi)
        frame_sequence += 1
        ear = None
        if result.ear[0] >= 0 and result.ear[1] >= 0:
            ear = (result.ear[0] + result.ear[1]) / 2
        state = FatigueState(
            timestamp_utc=datetime.now(timezone.utc),
            monotonic_ns=time.monotonic_ns(),
            face_present=result.face is not None,
            closed_eyes=result.isclosedeye,
            yawning=result.isyawning,
            ear=ear,
            mar=result.mar if result.mar >= 0 else None,
            camera_id=args.camera_id,
            frame_id=str(frame_sequence),
        )
        store.save_fatigue(state)
    capture.release()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="MH02 closed-eyes and yawning service")
    result.add_argument("--database", default="/var/lib/mh02/state/mh02.sqlite3")
    result.add_argument("--camera-id", default="cabin")
    result.add_argument("--source", default="http://127.0.0.1:8080/live/cabin.m3u8")
    result.add_argument("--app-root", default=str(Path(__file__).resolve().parents[3] / "apps" / "mh02"))
    result.add_argument("--interval", type=float, default=0.25)
    result.add_argument("--roi", default="300,100,1200,700")
    result.add_argument("--face-config", default="0.15,0.60,-70,70,-50,70")
    result.add_argument("--config-path", type=Path)
    return result


def apply_runtime_config(args: argparse.Namespace) -> argparse.Namespace:
    if args.config_path is None:
        return args
    config = ConfigStore(args.config_path).snapshot().config
    args.camera_id = config.fatigue.camera_id
    args.source = config.fatigue.source
    return args


def main() -> int:
    configure_logging("mh02.fatigue")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    run(apply_runtime_config(parser().parse_args()), stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
