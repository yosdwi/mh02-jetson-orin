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
GpsOperationalState = Literal["FIX", "NO_SIGNAL", "DISCONNECTED", "UNKNOWN"]
GpsDiagnosticReason = Literal[
    "NO_FIX",
    "FIX_EXPIRED",
    "NMEA_TIMEOUT",
    "INVALID_NMEA",
    "SERIAL_PORT_MISSING",
    "SERIAL_READ_ERROR",
    "AT_FAILURE",
    "RECONNECTING",
    "HEALTH_HEARTBEAT_EXPIRED",
    "OK",
]
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
    operational_state: GpsOperationalState = "FIX"
    diagnostic_reason: GpsDiagnosticReason = "OK"
    boot_id: str = "legacy"

    def is_fresh(self, as_of: datetime, max_age_seconds: float) -> bool:
        observed_at = self.fix_observed_at_utc or self.timestamp_utc
        age_seconds = (as_of - observed_at).total_seconds()
        if age_seconds < 0 or age_seconds > max_age_seconds:
            return False
        if self.valid_until_utc is not None and as_of > self.valid_until_utc:
            return False
        return (
            self.valid
            and self.fix_quality > 0
            and self.status not in ("STALE", "INVALID", "NO_FIX")
            and self.operational_state == "FIX"
        )

    def as_of(self, observed_at: datetime, max_age_seconds: float) -> "GpsSnapshot":
        if self.is_fresh(observed_at, max_age_seconds):
            return self
        return self.model_copy(
            update={
                "valid": False,
                "status": "NO_FIX",
                "operational_state": "NO_SIGNAL",
                "diagnostic_reason": "FIX_EXPIRED" if self.valid and self.fix_quality > 0 else "NO_FIX",
            },
        )


class GpsHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(default=1, ge=1)
    state: GpsOperationalState = "UNKNOWN"
    diagnostic_reason: GpsDiagnosticReason = "RECONNECTING"
    source: str = "quectel-ec25-nmea"
    device_path: Optional[str] = None
    serial_accessible: bool = False
    nmea_last_received_utc: Optional[datetime] = None
    nmea_last_received_monotonic_ns: Optional[int] = Field(default=None, ge=0)
    last_valid_fix_utc: Optional[datetime] = None
    last_valid_fix_monotonic_ns: Optional[int] = Field(default=None, ge=0)
    fix_quality: int = Field(default=0, ge=0)
    satellites: int = Field(default=0, ge=0)
    fix_age_seconds: Optional[float] = Field(default=None, ge=0)
    last_valid_latitude: Optional[float] = None
    last_valid_longitude: Optional[float] = None
    last_valid_speed_kph: Optional[float] = None
    last_valid_altitude_m: Optional[float] = None
    last_error: Optional[str] = None
    reconnect_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    heartbeat_utc: datetime
    heartbeat_monotonic_ns: int = Field(gt=0)
    boot_id: str = "legacy"

    def heartbeat_fresh(self, as_of: datetime, max_age_seconds: float) -> bool:
        age_seconds = (as_of - self.heartbeat_utc).total_seconds()
        return 0 <= age_seconds <= max_age_seconds

    def as_of(self, observed_at: datetime, heartbeat_max_age_seconds: float, fix_max_age_seconds: float) -> "GpsHealth":
        if not self.heartbeat_fresh(observed_at, heartbeat_max_age_seconds):
            return self.model_copy(update={"state": "UNKNOWN", "diagnostic_reason": "HEALTH_HEARTBEAT_EXPIRED"})
        if self.state == "FIX" and self.last_valid_fix_utc is not None:
            fix_age = (observed_at - self.last_valid_fix_utc).total_seconds()
            if fix_age < 0 or fix_age > fix_max_age_seconds:
                return self.model_copy(
                    update={
                        "state": "NO_SIGNAL",
                        "diagnostic_reason": "FIX_EXPIRED",
                        "fix_age_seconds": max(0.0, fix_age),
                    },
                )
        return self

    @property
    def has_current_fix(self) -> bool:
        return self.state == "FIX" and self.last_valid_latitude is not None and self.last_valid_longitude is not None


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
    gps_health: Optional[GpsHealth] = None
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
    recording_camera_id: str = "front"
    evidence_status: Literal["pending", "complete", "partial", "unavailable"] = "pending"
    source_status: FatigueStatus = "fresh"
    boot_id: str = "legacy"
