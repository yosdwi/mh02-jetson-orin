from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from .models import AggregateSample


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


def overlay_lines(sample: AggregateSample) -> Tuple[str, str, str]:
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


def sample_offset_seconds(
    sample: AggregateSample,
    segment_start_utc: datetime,
    segment_start_pts_ns: Optional[int],
) -> float:
    if segment_start_pts_ns is not None and sample.media_pts_ns is not None:
        return max(0.0, (sample.media_pts_ns - segment_start_pts_ns) / 1_000_000_000)
    return max(0.0, (sample.timestamp_utc - segment_start_utc).total_seconds())


def render_vtt(
    samples: Sequence[AggregateSample],
    segment_start_utc: datetime,
    segment_start_pts_ns: Optional[int] = None,
    segment_duration_seconds: Optional[float] = None,
) -> str:
    ordered = sorted(
        samples,
        key=lambda sample: (
            sample.media_pts_ns is None,
            sample.media_pts_ns if sample.media_pts_ns is not None else 0,
            sample.timestamp_utc,
            sample.sequence,
        ),
    )
    offsets = [sample_offset_seconds(sample, segment_start_utc, segment_start_pts_ns) for sample in ordered]
    positions = (5, 12, 88)
    lines: List[str] = ["WEBVTT", ""]
    for index, sample in enumerate(ordered):
        begin = offsets[index]
        next_begin = offsets[index + 1] if index + 1 < len(offsets) else None
        if next_begin is not None and next_begin > begin:
            end = next_begin
        elif segment_duration_seconds is not None and segment_duration_seconds > begin:
            end = segment_duration_seconds
        else:
            end = begin + 0.05
        end = max(begin + 0.05, end)
        for line_number, (line, position) in enumerate(zip(overlay_lines(sample), positions)):
            lines.append(f"{sample.sequence}-{line_number}")
            lines.append(
                f"{timestamp(begin)} --> {timestamp(end)} line:{position}% position:2% size:96% align:start",
            )
            lines.append(line)
            lines.append("")
    return "\n".join(lines)
