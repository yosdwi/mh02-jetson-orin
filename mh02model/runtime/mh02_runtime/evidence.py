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


def overlay_lines(sample: AggregateSample, camera_id: str = "FRONT", clock_source: str = "utc_observed") -> Tuple[str, str, str]:
    health = sample.gps_health
    gps_state = health.state if health is not None else ("FIX" if sample.gps and sample.gps.valid else "UNKNOWN")
    gps = sample.gps if gps_state == "FIX" and sample.gps and sample.gps.valid else None
    speed = "--" if gps is None or gps.speed_kph is None else str(round(gps.speed_kph)).zfill(3)
    payload = sample.redis_payload
    acceleration = next(
        (payload.get(key) for key in ("acceleration", "acc", "ACC", "acc_status") if payload.get(key) is not None),
        None,
    )
    if isinstance(acceleration, bool):
        acceleration_text = "ON" if acceleration else "OFF"
    elif acceleration is None:
        acceleration_text = "--"
    else:
        acceleration_text = str(acceleration).upper()
    channel = payload.get("channel") or payload.get("channel_no") or "CH1"
    channel_text = str(channel).upper()
    if not channel_text.startswith("CH"):
        channel_text = f"CH{channel_text}"
    local_timestamp = sample.timestamp_utc.astimezone().strftime("%d-%m-%Y %H:%M:%S")
    state_text = gps_state.replace("_", " ")
    fatigue = sample.fatigue if camera_id.lower() == "cabin" else None
    fatigue_text = ""
    if fatigue is not None:
        fatigue_text = f" FATIGUE:{'ALERT' if fatigue.closed_eyes or fatigue.yawning else 'NORMAL'} EAR:{fatigue.ear if fatigue.ear is not None else '--'} MAR:{fatigue.mar if fatigue.mar is not None else '--'}"
    return (
        f"GPS {state_text}: {nmea_coordinate(gps.latitude if gps else None, True)}, {nmea_coordinate(gps.longitude if gps else None, False)}, {speed}KM/H ACC:{acceleration_text}",
        f"ID: {sample.device_id or '--'} UNIT: {sample.unit_no or '--'} CAM:{camera_id.upper()}{fatigue_text}",
        f"{local_timestamp} {sample.unit_no or '--'} {channel_text} CLOCK:{clock_source.upper()}",
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
    use_media_pts: Optional[bool] = None,
) -> float:
    use_media_pts = (
        segment_start_pts_ns is not None and sample.media_pts_ns is not None
        if use_media_pts is None
        else use_media_pts
    )
    if use_media_pts and segment_start_pts_ns is not None and sample.media_pts_ns is not None:
        return max(0.0, (sample.media_pts_ns - segment_start_pts_ns) / 1_000_000_000)
    return max(0.0, (sample.timestamp_utc - segment_start_utc).total_seconds())


def vtt_clock_source(samples: Sequence[AggregateSample], segment_start_pts_ns: Optional[int]) -> str:
    if segment_start_pts_ns is not None and samples and all(sample.media_pts_ns is not None for sample in samples):
        return "media_pts"
    return "utc_observed"


def samples_for_segment(samples: Sequence[AggregateSample], segment_start_utc: datetime) -> List[AggregateSample]:
    return [sample for sample in samples if sample.timestamp_utc >= segment_start_utc]


def coverage_gaps(
    intervals: Sequence[Tuple[datetime, datetime]],
    expected_start: datetime,
    expected_end: datetime,
) -> List[Tuple[datetime, datetime]]:
    cursor = expected_start
    gaps: List[Tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if end <= expected_start or start >= expected_end:
            continue
        start = max(start, expected_start)
        end = min(end, expected_end)
        if start > cursor:
            gaps.append((cursor, start))
        if end > cursor:
            cursor = end
    if cursor < expected_end:
        gaps.append((cursor, expected_end))
    return gaps


def evidence_status(
    intervals: Sequence[Tuple[datetime, datetime]],
    expected_start: datetime,
    expected_end: datetime,
) -> str:
    gaps = coverage_gaps(intervals, expected_start, expected_end)
    if not intervals:
        return "unavailable"
    return "complete" if not gaps else "partial"


def render_vtt(
    samples: Sequence[AggregateSample],
    segment_start_utc: datetime,
    segment_start_pts_ns: Optional[int] = None,
    segment_duration_seconds: Optional[float] = None,
    camera_id: str = "FRONT",
) -> str:
    clock_source = vtt_clock_source(samples, segment_start_pts_ns)
    use_media_pts = clock_source == "media_pts"
    ordered = sorted(
        samples,
        key=lambda sample: (
            sample.media_pts_ns if use_media_pts else None,
            sample.timestamp_utc,
            sample.sequence,
        ),
    )
    offset_samples: List[Tuple[float, AggregateSample]] = []
    for sample in ordered:
        offset = sample_offset_seconds(sample, segment_start_utc, segment_start_pts_ns, use_media_pts)
        if offset_samples and offset_samples[-1][0] == offset:
            offset_samples[-1] = (offset, sample)
        else:
            offset_samples.append((offset, sample))
    positions = (5, 12, 88)
    lines: List[str] = ["WEBVTT", ""]
    for index, (begin, sample) in enumerate(offset_samples):
        next_begin = offset_samples[index + 1][0] if index + 1 < len(offset_samples) else None
        if next_begin is not None and next_begin > begin:
            end = next_begin
        elif segment_duration_seconds is not None and segment_duration_seconds > begin:
            end = segment_duration_seconds
        else:
            end = begin + 0.05
        end = max(begin + 0.05, end)
        for line_number, (line, position) in enumerate(zip(overlay_lines(sample, camera_id, clock_source), positions)):
            lines.append(f"{sample.sequence}-{line_number}")
            lines.append(
                f"{timestamp(begin)} --> {timestamp(end)} line:{position}% position:2% size:96% align:start",
            )
            lines.append(line)
            lines.append("")
    return "\n".join(lines)
