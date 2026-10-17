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
GpsStatus = Literal["FIX", "NO_FIX", "STALE", "INVALID"]
FatigueStatus = Literal["fresh", "stale", "unknown"]


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
    fix_observed_at_utc: Optional[datetime] = None
    valid_until_utc: Optional[datetime] = None
    status: GpsStatus = "FIX"
    boot_id: str = "legacy"

    def is_fresh(self, as_of: datetime, max_age_seconds: float) -> bool:
        observed_at = self.fix_observed_at_utc or self.timestamp_utc
        age_seconds = (as_of - observed_at).total_seconds()
        if age_seconds < 0 or age_seconds > max_age_seconds:
            return False
        if self.valid_until_utc is not None and as_of > self.valid_until_utc:
            return False
        return self.valid and self.fix_quality > 0 and self.status not in ("STALE", "INVALID", "NO_FIX")

    def as_of(self, observed_at: datetime, max_age_seconds: float) -> "GpsSnapshot":
        if self.is_fresh(observed_at, max_age_seconds):
            return self
        status = "STALE" if self.valid and self.fix_quality > 0 else "NO_FIX"
        return self.model_copy(update={"valid": False, "status": status})


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
    camera_id: str = "cabin"
    frame_id: Optional[str] = None
    media_pts_ns: Optional[int] = Field(default=None, ge=0)
    source_status: FatigueStatus = "fresh"
    boot_id: str = "legacy"

    def is_fresh(self, as_of: datetime, max_age_seconds: float) -> bool:
        age_seconds = (as_of - self.timestamp_utc).total_seconds()
        return (
            0 <= age_seconds <= max_age_seconds
            and self.source_status == "fresh"
            and self.camera_id == "cabin"
        )


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
    boot_id: str = "legacy"
    media_pts_ns: Optional[int] = Field(default=None, ge=0)
    utc_uncertainty_ms: Optional[float] = Field(default=None, ge=0)


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
    camera_id: str = "cabin"
    source_status: FatigueStatus = "fresh"
    boot_id: str = "legacy"
