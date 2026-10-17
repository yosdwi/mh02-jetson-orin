from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


SourceKind = Literal["live_rtsp", "replay_mp4"]
InferenceStatus = Literal["starting", "running", "stopped", "blocked", "error", "not_running"]


class BoundingBox(BaseModel):
    model_config = ConfigDict(frozen=True)

    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class EvidenceReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    camera_id: Literal["front"] = "front"
    segment_id: Optional[str] = None
    status: Literal["pending", "complete", "unavailable"] = "pending"


class DetectionObservation(BaseModel):
    model_config = ConfigDict(frozen=True, protected_namespaces=())

    schema_version: int = Field(default=1, ge=1)
    observation_id: str
    observed_at_utc: datetime
    camera_id: Literal["front"] = "front"
    source_kind: SourceKind
    frame_id: str
    stream_generation: str = "legacy"
    media_pts_ns: Optional[int] = Field(default=None, ge=0)
    object_class: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    bounding_box: BoundingBox
    track_id: Optional[str] = None
    model_name: str
    model_version: str
    model_digest_sha256: str
    latency_ms: Optional[float] = Field(default=None, ge=0)


class WarningCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, protected_namespaces=())

    schema_version: int = Field(default=1, ge=1)
    warning_id: str
    created_at_utc: datetime
    camera_id: Literal["front"] = "front"
    source_kind: SourceKind
    frame_id: str
    media_pts_ns: Optional[int] = Field(default=None, ge=0)
    object_class: str
    confidence: float = Field(ge=0, le=1)
    track_id: Optional[str] = None
    evidence: EvidenceReference
    advisory_only: bool = True


class InferenceHealth(BaseModel):
    model_config = ConfigDict(frozen=True, protected_namespaces=())

    schema_version: int = Field(default=1, ge=1)
    status: InferenceStatus
    source_kind: Optional[SourceKind] = None
    source: Optional[str] = None
    camera_id: Literal["front", "cabin"] = "front"
    model_name: str = "disabled"
    model_version: str = "unconfigured"
    model_digest_sha256: Optional[str] = None
    deepstream_version: Optional[str] = None
    frames: int = Field(default=0, ge=0)
    detections: int = Field(default=0, ge=0)
    dropped_frames: int = Field(default=0, ge=0)
    fps: float = Field(default=0, ge=0)
    latency_p95_ms: Optional[float] = Field(default=None, ge=0)
    process_rss_mb: Optional[float] = Field(default=None, ge=0)
    gpu_utilization_percent: Optional[float] = Field(default=None, ge=0, le=100)
    last_media_pts_ns: Optional[int] = Field(default=None, ge=0)
    last_update_utc: datetime
    diagnostics: List[str] = Field(default_factory=list)
    annotated_stream_enabled: bool = False
    annotated_publisher: str = "disabled"


class InferenceCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    deepstream_available: bool
    nvinfer_available: bool
    nvtracker_available: bool
    pyds_available: bool
    nvdsosd_available: bool = False
    annotated_encoder_available: bool = False
    installed_deepstream_version: Optional[str] = None
    tensor_rt_version: Optional[str] = None
    diagnostics: Tuple[str, ...] = ()


class FrontValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    created_at_utc: datetime
    status: Literal["PASS", "FAIL", "BLOCKED"]
    source_kind: Optional[SourceKind] = None
    source: Optional[str] = None
    inference_status: InferenceStatus
    frames: int = Field(default=0, ge=0)
    detections: int = Field(default=0, ge=0)
    warnings: int = Field(default=0, ge=0)
    diagnostics: List[str] = Field(default_factory=list)


class FatigueObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(default=1, ge=1)
    observation_id: str
    observed_at_utc: datetime
    camera_id: Literal["cabin"] = "cabin"
    frame_id: str
    stream_generation: str = "legacy"
    media_pts_ns: Optional[int] = Field(default=None, ge=0)
    face_present: bool = False
    face_box: Optional[BoundingBox] = None
    closed_eyes: bool = False
    yawning: bool = False
    ear: Optional[float] = None
    mar: Optional[float] = None
    sync_status: Literal["matched", "delayed", "unavailable"] = "matched"
    latency_ms: Optional[float] = Field(default=None, ge=0)
