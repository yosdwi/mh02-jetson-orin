from __future__ import annotations

import argparse
import json
import logging
import os
import re
import re
import signal
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Iterable, List, Optional, Sequence, Tuple

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst

from .models import AlertEvent
from .store import RuntimeStore


LOGGER = logging.getLogger("mh02.alert-clips")
TIMESTAMP_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})\.(\d{3})$")
SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class RecordingInfo:
    path: Path
    subtitle_path: Optional[Path]
    started_at_utc: datetime
    ended_at_utc: datetime


def parse_timestamp(value: str) -> float:
    match = TIMESTAMP_RE.match(value.strip())
    if match is None:
        raise ValueError(f"Invalid VTT timestamp: {value}")
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def format_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{remaining:06.3f}"


def cue_position(payload: str) -> int:
    if payload.startswith("ID:"):
        return 12
    if re.match(r"^\d{2}-\d{2}-\d{4} ", payload):
        return 88
    return 5


def has_mp4_index(path: Path) -> bool:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if b"moov" in handle.read(min(size, 1024 * 1024)):
                return True
            if size > 1024 * 1024:
                handle.seek(-1024 * 1024, 2)
                return b"moov" in handle.read(1024 * 1024)
    except OSError:
        return False
    return False


def read_recordings(directory: Path, start: datetime, end: datetime) -> List[RecordingInfo]:
    result: List[RecordingInfo] = []
    for path in directory.glob("*.mp4"):
        metadata_path = path.with_suffix(".json")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            started = datetime.fromisoformat(metadata["started_at_utc"])
            ended = datetime.fromisoformat(metadata["ended_at_utc"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if not metadata.get("complete") or not has_mp4_index(path):
            continue
        if started < end and ended > start:
            subtitle = path.with_suffix(".vtt")
            result.append(RecordingInfo(path, subtitle if subtitle.exists() else None, started, ended))
    return sorted(result, key=lambda item: item.started_at_utc)


def gst_location(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(" ", "\\ ")


def trim_recording(source: RecordingInfo, start: datetime, end: datetime, output: Path) -> None:
    source_start = max(0.0, (start - source.started_at_utc).total_seconds())
    source_end = max(source_start + 0.05, (end - source.started_at_utc).total_seconds())
    pipeline_description = (
        f"filesrc location={gst_location(source.path)} ! qtdemux ! h264parse ! "
        f"mp4mux faststart=true ! filesink location={gst_location(output)}"
    )
    pipeline = Gst.parse_launch(pipeline_description)
    try:
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError(f"Unable to start GStreamer for {source.path.name}")
        state, _, _ = pipeline.get_state(10 * Gst.SECOND)
        if state == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError(f"GStreamer failed to preroll {source.path.name}")
        flags = Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE | Gst.SeekFlags.KEY_UNIT
        if not pipeline.seek(
            1.0,
            Gst.Format.TIME,
            flags,
            Gst.SeekType.SET,
            int(source_start * Gst.SECOND),
            Gst.SeekType.SET,
            int(source_end * Gst.SECOND),
        ):
            raise RuntimeError(f"GStreamer seek failed for {source.path.name}")
        message = pipeline.get_bus().timed_pop_filtered(
            90 * Gst.SECOND,
            Gst.MessageType.ERROR | Gst.MessageType.EOS,
        )
        if message is None:
            raise RuntimeError(f"GStreamer timed out while exporting {source.path.name}")
        if message.type == Gst.MessageType.ERROR:
            error, detail = message.parse_error()
            raise RuntimeError(f"GStreamer error for {source.path.name}: {error} ({detail})")
    finally:
        pipeline.set_state(Gst.State.NULL)
    if not output.exists() or not has_mp4_index(output):
        raise RuntimeError(f"GStreamer produced an invalid clip for {source.path.name}")


def combine_recordings(parts: Sequence[Path], output: Path) -> None:
    if len(parts) == 1:
        os.replace(parts[0], output)
        return

    def run_to_eos(description: str, label: str) -> None:
        pipeline = Gst.parse_launch(description)
        try:
            if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError(f"Unable to start GStreamer for {label}")
            message = pipeline.get_bus().timed_pop_filtered(
                90 * Gst.SECOND,
                Gst.MessageType.ERROR | Gst.MessageType.EOS,
            )
            if message is None:
                raise RuntimeError(f"GStreamer timed out for {label}")
            if message.type == Gst.MessageType.ERROR:
                error, detail = message.parse_error()
                raise RuntimeError(f"GStreamer error for {label}: {error} ({detail})")
        finally:
            pipeline.set_state(Gst.State.NULL)

    with tempfile.TemporaryDirectory(prefix="alert-ts-", dir=output.parent) as temporary_dir:
        transport_parts: List[Path] = []
        for index, part in enumerate(parts):
            transport = Path(temporary_dir) / f"part-{index:02d}.ts"
            run_to_eos(
                f"filesrc location={gst_location(part)} ! qtdemux ! h264parse ! "
                f"mpegtsmux ! filesink location={gst_location(transport)}",
                part.name,
            )
            transport_parts.append(transport)
        joined = Path(temporary_dir) / "joined.ts"
        with joined.open("wb") as handle:
            for transport in transport_parts:
                handle.write(transport.read_bytes())
        run_to_eos(
            f"filesrc location={gst_location(joined)} ! tsdemux ! h264parse ! "
            f"mp4mux faststart=true ! filesink location={gst_location(output)}",
            output.name,
        )
    if not output.exists() or not has_mp4_index(output):
        raise RuntimeError("GStreamer produced an invalid concatenated alert clip")


def read_cues(path: Path) -> Iterable[Tuple[float, float, str]]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    cues: List[Tuple[float, float, str]] = []
    for block in content.split("\n\n"):
        lines = [line.strip("\r") for line in block.splitlines()]
        timing_index = next((index for index, line in enumerate(lines) if " --> " in line), None)
        if timing_index is None:
            continue
        begin_text, end_text = lines[timing_index].split(" --> ", 1)
        try:
            begin = parse_timestamp(begin_text)
            end = parse_timestamp(end_text.split(" ", 1)[0])
        except ValueError:
            continue
        payload = "\n".join(lines[timing_index + 1 :]).strip()
        if payload and end > begin:
            cues.append((begin, end, payload))
    return cues


def write_clip_vtt(
    output: Path,
    recordings: Sequence[RecordingInfo],
    clip_start: datetime,
    clip_end: datetime,
) -> None:
    with output.open("w", encoding="utf-8") as handle:
        handle.write("WEBVTT\n\n")
        for recording in recordings:
            local_start = max(clip_start, recording.started_at_utc)
            local_end = min(clip_end, recording.ended_at_utc)
            if local_end <= local_start or recording.subtitle_path is None:
                continue
            source_offset = (local_start - recording.started_at_utc).total_seconds()
            source_end = (local_end - recording.started_at_utc).total_seconds()
            clip_offset = (local_start - clip_start).total_seconds()
            for begin, end, payload in read_cues(recording.subtitle_path):
                if end <= source_offset or begin >= source_end:
                    continue
                begin = max(begin, source_offset) - source_offset + clip_offset
                end = min(end, source_end) - source_offset + clip_offset
                if end <= begin:
                    continue
                position = cue_position(payload)
                handle.write(
                    f"{format_timestamp(begin)} --> {format_timestamp(end)} line:{position}% position:2% size:96% align:start\n"
                    f"{payload}\n\n"
                )


def write_json(path: Path, payload: object) -> None:
    fd, temporary = tempfile.mkstemp(prefix="alert-clip-", suffix=".json.tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def clip_id(event: AlertEvent) -> str:
    return SAFE_ID_RE.sub("-", event.id).strip("-")


def export_event(event: AlertEvent, store: RuntimeStore, record_dir: Path, clip_dir: Path) -> bool:
    if event.state != "complete" or event.evidence_end_utc is None:
        return False
    name = f"alert-{clip_id(event)}"
    output = clip_dir / f"{name}.mp4"
    subtitle = clip_dir / f"{name}.vtt"
    metadata = clip_dir / f"{name}.json"
    if output.exists() and subtitle.exists() and has_mp4_index(output):
        if event.clip_filename != output.name:
            store.save_alert(event.model_copy(update={"clip_filename": output.name, "clip_subtitle_filename": subtitle.name}))
        return False

    recordings = read_recordings(record_dir, event.evidence_start_utc, event.evidence_end_utc)
    if not recordings:
        return False
    clip_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{name}-", dir=clip_dir) as temporary_dir:
        parts: List[Path] = []
        for index, recording in enumerate(recordings):
            start = max(event.evidence_start_utc, recording.started_at_utc)
            end = min(event.evidence_end_utc, recording.ended_at_utc)
            if end <= start:
                continue
            part = Path(temporary_dir) / f"part-{index:02d}.mp4"
            trim_recording(recording, start, end, part)
            parts.append(part)
        if not parts:
            return False
        temporary_output = Path(temporary_dir) / output.name
        combine_recordings(parts, temporary_output)
        os.replace(temporary_output, output)
        temporary_vtt = Path(temporary_dir) / subtitle.name
        write_clip_vtt(temporary_vtt, recordings, event.evidence_start_utc, event.evidence_end_utc)
        os.replace(temporary_vtt, subtitle)

    write_json(
        metadata,
        {
            "alert_id": event.id,
            "filename": output.name,
            "subtitle_filename": subtitle.name,
            "started_at_utc": event.evidence_start_utc.isoformat(),
            "ended_at_utc": event.evidence_end_utc.isoformat(),
            "duration_seconds": (event.evidence_end_utc - event.evidence_start_utc).total_seconds(),
            "complete": True,
        },
    )
    store.save_alert(event.model_copy(update={"clip_filename": output.name, "clip_subtitle_filename": subtitle.name}))
    LOGGER.info("Exported alert clip %s from %s recording(s)", output.name, len(recordings))
    return True


def run(args: argparse.Namespace, stop: Event) -> None:
    Gst.init(None)
    args.clip_dir.mkdir(parents=True, exist_ok=True)
    store = RuntimeStore(Path(args.database))
    while not stop.wait(0):
        for event in store.alerts():
            try:
                export_event(event, store, args.record_dir, args.clip_dir)
            except Exception:
                LOGGER.exception("Failed to export alert clip %s", event.id)
        if stop.wait(args.poll_seconds):
            break


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Export alert evidence clips from finalized Vlog MP4 segments")
    result.add_argument("--database", default="/var/lib/mh02/state/mh02.sqlite3")
    result.add_argument("--record-dir", type=Path, default=Path("/var/lib/mh02/recordings/front"))
    result.add_argument("--clip-dir", type=Path, default=Path("/var/lib/mh02/recordings/alerts"))
    result.add_argument("--poll-seconds", type=float, default=5.0)
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
