from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field


JsonValue = Union[
    None,
    str,
    int,
    float,
    bool,
    List[Any],
    Dict[str, Any],
]


class GpsSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp_utc: datetime
    monotonic_ns: int = Field(gt=0)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed_kph: Optional[float] = None
    altitude_m: Optional[float] = None
    fix_quality: int = Field(default=0, ge=0)
    satellites: int = Field(default=0, ge=0)
    valid: bool = False
    source: str = "quectel-ec25-nmea"
    sentence: str = ""


class FatigueState(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp_utc: datetime
    monotonic_ns: int = Field(gt=0)
    face_present: bool = False
    closed_eyes: bool = False
    yawning: bool = False
    ear: Optional[float] = None
    mar: Optional[float] = None
    source: str = "mh02model-mediapipe-cpu-compat"


class AggregateSample(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence: int = Field(gt=0)
    timestamp_utc: datetime
    monotonic_ns: int = Field(gt=0)
    device_id: str
    unit_no: str
    gps: Optional[GpsSnapshot] = None
    redis_payload: Dict[str, JsonValue] = Field(default_factory=dict)
    fatigue: Optional[FatigueState] = None


class Recording(BaseModel):
    model_config = ConfigDict(frozen=True)

    camera_id: str
    filename: str
    subtitle_filename: Optional[str] = None
    size_bytes: int = Field(ge=0)
    modified_at_utc: datetime
    started_at_utc: Optional[datetime] = None
    ended_at_utc: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    complete: bool = True


class DatalogFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    filename: str
    hour_local: datetime
    size_bytes: int = Field(ge=0)
    rows: int = Field(ge=0)
    complete: bool = True


class AlertEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    alert_type: Literal["closed_eyes", "yawning"]
    state: Literal["active", "post", "complete"]
    started_at_utc: datetime
    triggered_at_utc: datetime
    ended_at_utc: Optional[datetime] = None
    evidence_start_utc: datetime
    evidence_end_utc: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    recording_filenames: Tuple[str, ...] = ()
    datalog_filenames: Tuple[str, ...] = ()
    clip_filename: Optional[str] = None
    clip_subtitle_filename: Optional[str] = None
