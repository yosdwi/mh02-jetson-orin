#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "opencv-python",
#     "mediapipe",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run poc_jetson_mediapipe_openvino.py --input evidence.mp4
# 3. Or make executable and run:
#      chmod +x poc_jetson_mediapipe_openvino.py && ./poc_jetson_mediapipe_openvino.py
# ──────────────────

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, NamedTuple, TextIO

import cv2


DEFAULT_INPUT: Final = Path("/mnt/d/Job/JetsonMH02/evidence.mp4")
DEFAULT_OUTPUT: Final = Path("/mnt/d/Job/JetsonMH02/evidence_poc.mp4")
DEFAULT_METRICS: Final = Path("/mnt/d/Job/JetsonMH02/evidence_poc.metrics.json")


class MetricsSnapshot(NamedTuple):
    """One Jetson telemetry snapshot plus Linux CPU counters."""

    label: str
    captured_at_utc: str
    tegrastats: str
    cpu_counters: tuple[int, ...] | None


class VideoResult(NamedTuple):
    """Observable result of the MediaPipe video pass."""

    frames_processed: int
    faces_detected: int
    fps: float
    width: int
    height: int


class PocRuntimeError(OSError):
    """A typed error at the video pipeline boundary."""


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the Jetson PoC."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="Maximum video duration in seconds; use 0 for the full input.",
    )
    return parser.parse_args()


def read_cpu_counters() -> tuple[int, ...] | None:
    """Read aggregate CPU counters from Linux /proc."""
    try:
        first_line = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
    except (FileNotFoundError, IndexError, PermissionError):
        return None
    parts = first_line.split()
    if not parts or parts[0] != "cpu":
        return None
    return tuple(int(value) for value in parts[1:])


def cpu_usage_percent(
    before: tuple[int, ...] | None,
    after: tuple[int, ...] | None,
) -> float | None:
    """Calculate aggregate CPU utilization between two /proc snapshots."""
    if before is None or after is None or len(before) < 4 or len(after) < 4:
        return None
    before_total = sum(before)
    after_total = sum(after)
    total_delta = after_total - before_total
    idle_delta = after[3] - before[3]
    if total_delta <= 0:
        return None
    return round((1.0 - idle_delta / total_delta) * 100.0, 2)


def run_tegrastats_once() -> str:
    """Capture one Jetson tegrastats line, if the utility is installed."""
    executable = shutil.which("tegrastats")
    if executable is None:
        return "tegrastats not found"
    try:
        completed = subprocess.run(
            [executable, "--interval", "1000"],
            capture_output=True,
            check=False,
            text=True,
            timeout=3,
        )
        output = (completed.stdout or completed.stderr).strip()
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or exc.stderr or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        output = output.strip()
    except OSError as exc:
        return f"tegrastats failed: {type(exc).__name__}: {exc}"
    if output:
        return output.splitlines()[0]
    return f"tegrastats failed: exit code {completed.returncode}"


def capture_snapshot(label: str) -> MetricsSnapshot:
    """Capture CPU counters and the Jetson telemetry line."""
    return MetricsSnapshot(
        label=label,
        captured_at_utc=datetime.now(timezone.utc).isoformat(),
        tegrastats=run_tegrastats_once(),
        cpu_counters=read_cpu_counters(),
    )


def start_tegrastats(log_path: Path) -> tuple[subprocess.Popen[str] | None, TextIO | None]:
    """Start continuous tegrastats logging for the video pass."""
    executable = shutil.which("tegrastats")
    if executable is None:
        log_path.write_text("tegrastats not found\n", encoding="utf-8")
        return None, None
    log_file = log_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            [executable, "--interval", "1000"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except OSError:
        log_file.close()
        raise
    return process, log_file


def stop_tegrastats(
    process: subprocess.Popen[str] | None,
    log_file: TextIO | None,
) -> None:
    """Stop continuous tegrastats logging and close its output file."""
    if process is not None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if log_file is not None:
        log_file.close()


def run_mediapipe_video(
    input_path: Path,
    output_path: Path,
    duration_seconds: float,
) -> VideoResult:
    """Run MediaPipe Face Mesh and save an annotated MP4."""
    import mediapipe as mp

    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        raise PocRuntimeError(f"Unable to open input video: {input_path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise PocRuntimeError(f"Unable to open output video: {output_path}")

    frame_limit = int(fps * duration_seconds) if duration_seconds > 0 else None
    frames_processed = 0
    faces_detected = 0
    try:
        with mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=2,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) as face_mesh:
            while frame_limit is None or frames_processed < frame_limit:
                success, frame = capture.read()
                if not success:
                    break
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = face_mesh.process(rgb_frame)
                detections = result.multi_face_landmarks or []
                faces_detected += len(detections)
                cv2.putText(
                    frame,
                    f"MediaPipe FaceMesh faces={len(detections)}",
                    (12, 32),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )
                for landmarks in detections:
                    x_points = [int(point.x * width) for point in landmarks.landmark]
                    y_points = [int(point.y * height) for point in landmarks.landmark]
                    cv2.rectangle(
                        frame,
                        (max(0, min(x_points)), max(0, min(y_points))),
                        (min(width - 1, max(x_points)), min(height - 1, max(y_points))),
                        (0, 255, 0),
                        2,
                    )
                    mp.solutions.drawing_utils.draw_landmarks(
                        image=frame,
                        landmark_list=landmarks,
                        connections=mp.solutions.face_mesh.FACEMESH_TESSELATION,
                        landmark_drawing_spec=None,
                        connection_drawing_spec=mp.solutions.drawing_styles.get_default_face_mesh_tesselation_style(),
                    )
                    mp.solutions.drawing_utils.draw_landmarks(
                        image=frame,
                        landmark_list=landmarks,
                        connections=mp.solutions.face_mesh.FACEMESH_CONTOURS,
                        landmark_drawing_spec=None,
                        connection_drawing_spec=mp.solutions.drawing_styles.get_default_face_mesh_contours_style(),
                    )
                writer.write(frame)
                frames_processed += 1
    finally:
        capture.release()
        writer.release()

    return VideoResult(frames_processed, faces_detected, fps, width, height)


def main() -> int:
    """Run MediaPipe Face Mesh with Jetson telemetry capture."""
    args = parse_args()
    if not args.input.is_file():
        raise FileNotFoundError(f"Input video does not exist: {args.input}")

    metrics_path = args.metrics
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    tegrastats_log = metrics_path.with_suffix(".tegrastats.log")
    before = capture_snapshot("before")
    tegrastats_process, tegrastats_file = start_tegrastats(tegrastats_log)
    started_at = time.perf_counter()
    try:
        video_result = run_mediapipe_video(args.input, args.output, args.duration)
    finally:
        stop_tegrastats(tegrastats_process, tegrastats_file)
    elapsed_seconds = round(time.perf_counter() - started_at, 3)
    after = capture_snapshot("after")

    report = {
        "input": str(args.input),
        "output": str(args.output),
        "metrics_log": str(tegrastats_log),
        "mediapipe": video_result._asdict(),
        "elapsed_seconds": elapsed_seconds,
        "cpu_usage_percent_between_snapshots": cpu_usage_percent(
            before.cpu_counters,
            after.cpu_counters,
        ),
        "snapshots": [before._asdict(), after._asdict()],
    }
    metrics_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
