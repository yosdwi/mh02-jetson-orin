from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass(frozen=True)
class MediaVerification:
    verified: bool
    reason: str


def _decode_with_gstreamer(path: Path) -> bool:
    executable = shutil.which("gst-launch-1.0")
    if executable is None:
        return False
    location = str(path.resolve()).replace("\\", "\\\\").replace(" ", "\\ ")
    try:
        completed = subprocess.run(
            [
                executable,
                "-q",
                f"filesrc location={location}",
                "!",
                "qtdemux",
                "name=demux",
                "demux.video_0",
                "!",
                "queue",
                "!",
                "decodebin",
                "!",
                "fakesink",
                "sync=false",
            ],
            capture_output=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def verify_media(
    path: Path,
    decoder: Optional[Callable[[Path], bool]] = None,
) -> MediaVerification:
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return MediaVerification(False, "missing_or_empty")
    except OSError:
        return MediaVerification(False, "unreadable")
    decode = decoder or _decode_with_gstreamer
    if not decode(path):
        return MediaVerification(False, "decode_failed")
    return MediaVerification(True, "decoded_to_eos")
