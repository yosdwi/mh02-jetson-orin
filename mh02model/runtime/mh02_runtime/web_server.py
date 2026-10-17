from __future__ import annotations

import argparse
import json
import os
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from .models import AlertEvent, DatalogFile, Recording
from .media_verifier import verify_media
from .store import RuntimeStore


WEB_ROOT = Path(__file__).resolve().parent / "web"


def read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def recording_from(video: Path) -> Optional[Recording]:
    metadata = read_json(video.with_suffix(".json"))
    if not metadata or not metadata.get("complete", False) or not verify_media(video).verified:
        return None
    started = metadata.get("started_at_utc")
    ended = metadata.get("ended_at_utc")
    return Recording(
        camera_id=str(metadata.get("camera_id", "front")),
        filename=video.name,
        subtitle_filename=video.with_suffix(".vtt").name if video.with_suffix(".vtt").exists() else None,
        size_bytes=video.stat().st_size,
        modified_at_utc=datetime.fromtimestamp(video.stat().st_mtime, timezone.utc),
        started_at_utc=datetime.fromisoformat(started) if started else None,
        ended_at_utc=datetime.fromisoformat(ended) if ended else None,
        duration_seconds=float(metadata["duration_seconds"]) if metadata.get("duration_seconds") else None,
        complete=bool(metadata.get("complete", True)),
    )


def list_recordings(record_dir: Path) -> List[Recording]:
    result: List[Recording] = []
    for video in sorted(record_dir.glob("*.mp4"), key=lambda path: path.stat().st_mtime, reverse=True):
        item = recording_from(video)
        if item is not None:
            result.append(item)
    return result


def list_datalogs(datalog_dir: Path) -> List[DatalogFile]:
    result: List[DatalogFile] = []
    for parquet_file in sorted(datalog_dir.glob("*.parquet"), key=lambda path: path.stat().st_mtime, reverse=True):
        metadata = read_json(parquet_file.with_suffix(parquet_file.suffix + ".json"))
        hour = metadata.get("hour_local")
        if not hour:
            continue
        result.append(
            DatalogFile(
                filename=parquet_file.name,
                hour_local=datetime.fromisoformat(hour),
                size_bytes=parquet_file.stat().st_size,
                rows=int(metadata.get("rows", 0)),
                complete=bool(metadata.get("complete", False)),
            )
        )
    return result


def overlaps(item: Recording, start: datetime, end: datetime) -> bool:
    item_start = item.started_at_utc or item.modified_at_utc
    item_end = item.ended_at_utc or item_start
    return item_start < end and item_end > start


def stream_bytes(path: Path, start: int, length: int) -> Iterator[bytes]:
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                return
            remaining -= len(chunk)
            yield chunk


def recording_response(path: Path, request: Request) -> Response:
    size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type="video/mp4", headers={"Accept-Ranges": "bytes"})
    if not range_header.startswith("bytes=") or "," in range_header or size == 0:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    value = range_header[6:]
    start_text, separator, end_text = value.partition("-")
    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if separator and end_text else size - 1
        else:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                raise ValueError
            start = max(0, size - suffix_length)
            end = size - 1
    except ValueError:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    if start < 0 or start >= size or end < start:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    end = min(end, size - 1)
    length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Range": f"bytes {start}-{end}/{size}",
    }
    return StreamingResponse(stream_bytes(path, start, length), status_code=206, media_type="video/mp4", headers=headers)


def bundle_response(directory: Path, filename: str) -> Response:
    video = directory / Path(filename).name
    if video.suffix.lower() != ".mp4" or not video.exists():
        return JSONResponse(status_code=404, content={"detail": "Video not found"})
    subtitle = video.with_suffix(".vtt")
    metadata = video.with_suffix(".json")
    fd, temporary_path = tempfile.mkstemp(prefix="mh02-bundle-", suffix=".zip", dir=directory)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(video, video.name, compress_type=zipfile.ZIP_STORED)
            if subtitle.exists():
                archive.write(subtitle, subtitle.name, compress_type=zipfile.ZIP_DEFLATED)
            if metadata.exists():
                archive.write(metadata, metadata.name, compress_type=zipfile.ZIP_DEFLATED)
    except Exception:
        os.unlink(temporary_path)
        raise
    bundle_name = f"{video.stem}.zip"
    return FileResponse(
        temporary_path,
        media_type="application/zip",
        filename=bundle_name,
        background=BackgroundTask(os.unlink, temporary_path),
    )


def enrich_alert(event: AlertEvent, recordings: List[Recording], datalogs: List[DatalogFile]) -> AlertEvent:
    evidence_end = event.evidence_end_utc or datetime.now(timezone.utc)
    matching_recordings = tuple(
        item.filename
        for item in recordings
        if overlaps(item, event.evidence_start_utc, evidence_end)
    )
    matching_datalogs = []
    for item in datalogs:
        hour_start = item.hour_local.astimezone(timezone.utc)
        hour_end = hour_start + timedelta(hours=1)
        if hour_start < evidence_end and hour_end > event.evidence_start_utc:
            matching_datalogs.append(item.filename)
    return event.model_copy(
        update={
            "recording_filenames": matching_recordings,
            "datalog_filenames": tuple(matching_datalogs),
        },
    )


def create_app(database: Path, record_dir: Path, hls_dir: Path, datalog_dir: Path, clip_dir: Path) -> FastAPI:
    app = FastAPI(title="Vehicle Operations")
    store = RuntimeStore(database)

    @app.get("/api/aggregate")
    def latest_aggregate() -> object:
        sample = store.latest_aggregate()
        return sample if sample is not None else JSONResponse(status_code=204, content=None)

    @app.get("/api/recordings", response_model=List[Recording])
    def recordings(date: Optional[str] = None, hour: Optional[int] = None) -> List[Recording]:
        items = list_recordings(record_dir)
        if date is None:
            return items
        selected = datetime.strptime(date, "%Y-%m-%d").date()
        result = []
        for item in items:
            started = (item.started_at_utc or item.modified_at_utc).astimezone().replace(tzinfo=None)
            if started.date() != selected:
                continue
            if hour is not None and started.hour != hour:
                continue
            result.append(item)
        return result

    @app.get("/api/datalogs", response_model=List[DatalogFile])
    def datalogs() -> List[DatalogFile]:
        return list_datalogs(datalog_dir)

    @app.get("/api/alerts", response_model=List[AlertEvent])
    def alerts(date: Optional[str] = None, alert_type: Optional[str] = None) -> List[AlertEvent]:
        selected = datetime.strptime(date, "%Y-%m-%d").date() if date else None
        recordings_all = list_recordings(record_dir)
        datalogs_all = list_datalogs(datalog_dir)
        result = []
        for event in store.alerts():
            if selected is not None and event.started_at_utc.astimezone().date() != selected:
                continue
            if alert_type is not None and event.alert_type != alert_type:
                continue
            result.append(enrich_alert(event, recordings_all, datalogs_all))
        return result

    @app.get("/api/health")
    def health(date: Optional[str] = None) -> Dict[str, Any]:
        local_now = datetime.now().astimezone()
        selected_date = datetime.strptime(date, "%Y-%m-%d").date() if date else local_now.date()
        recordings_all = list_recordings(record_dir)
        datalogs_all = list_datalogs(datalog_dir)
        hours: List[Dict[str, Any]] = []
        for number in range(24):
            start = datetime.combine(selected_date, datetime.min.time(), local_now.tzinfo) + timedelta(hours=number)
            end = start + timedelta(hours=1)
            expected_seconds = max(0.0, min(3600.0, (local_now - start).total_seconds()))
            matches = [item for item in recordings_all if overlaps(item, start.astimezone(timezone.utc), end.astimezone(timezone.utc))]
            recording_seconds = sum(item.duration_seconds or 0 for item in matches)
            datalog_match = next((item for item in datalogs_all if item.hour_local.astimezone().replace(tzinfo=None) == start.replace(tzinfo=None)), None)
            datalog_ok = datalog_match is not None and datalog_match.complete and datalog_match.rows >= max(1, int(expected_seconds * 0.8))
            recording_ok = recording_seconds >= max(30.0, expected_seconds * 0.8) if expected_seconds else False
            recording_present = recording_seconds > 0
            datalog_present = datalog_match is not None and datalog_match.rows > 0
            future = start > local_now
            if future:
                status = "future"
            elif recording_ok and datalog_ok:
                status = "green"
            elif recording_present or datalog_present:
                status = "orange"
            else:
                status = "red"
            hours.append({"hour": number, "status": status, "recording": recording_ok, "datalog": datalog_ok, "recording_seconds": round(recording_seconds), "datalog_rows": datalog_match.rows if datalog_match else 0})
        return {"date": selected_date.isoformat(), "hours": hours}

    @app.get("/recordings/{filename}")
    def recording(filename: str, request: Request) -> Response:
        path = record_dir / Path(filename).name
        if not path.exists():
            return JSONResponse(status_code=404, content={"detail": "Recording not found"})
        if path.suffix.lower() != ".mp4":
            return FileResponse(path, media_type="text/vtt" if path.suffix.lower() == ".vtt" else None)
        return recording_response(path, request)

    @app.get("/recordings/{filename}/bundle")
    def recording_bundle(filename: str) -> Response:
        return bundle_response(record_dir, filename)

    @app.get("/datalog/{filename}")
    def datalog(filename: str) -> FileResponse:
        path = datalog_dir / Path(filename).name
        return FileResponse(path, media_type="application/octet-stream", filename=path.name)

    @app.get("/alert-clips/{filename}")
    def alert_clip(filename: str, request: Request) -> Response:
        path = clip_dir / Path(filename).name
        if not path.exists():
            return JSONResponse(status_code=404, content={"detail": "Alert clip not found"})
        if path.suffix.lower() != ".mp4":
            return FileResponse(path, media_type="text/vtt" if path.suffix.lower() == ".vtt" else None)
        return recording_response(path, request)

    @app.get("/alert-clips/{filename}/bundle")
    def alert_clip_bundle(filename: str) -> Response:
        return bundle_response(clip_dir, filename)

    app.mount("/live", StaticFiles(directory=str(hls_dir), check_dir=False), name="live")
    app.mount("/assets", StaticFiles(directory=str(WEB_ROOT)), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB_ROOT / "index.html")

    return app


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Vehicle operations web server")
    result.add_argument("--database", default="/var/lib/mh02/state/mh02.sqlite3")
    result.add_argument("--record-dir", type=Path, default=Path("/var/lib/mh02/recordings/front"))
    result.add_argument("--hls-dir", type=Path, default=Path("/var/lib/mh02/hls"))
    result.add_argument("--datalog-dir", type=Path, default=Path("/var/lib/mh02/datalog"))
    result.add_argument("--clip-dir", type=Path, default=Path("/var/lib/mh02/recordings/alerts"))
    result.add_argument("--host", default="0.0.0.0")
    result.add_argument("--port", type=int, default=8080)
    return result


def main() -> int:
    args = parser().parse_args()
    app = create_app(Path(args.database), args.record_dir, args.hls_dir, args.datalog_dir, args.clip_dir)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
