from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator


CameraId = Literal["front", "cabin"]
SourceKind = Literal["device", "rtsp", "test"]


class CameraConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    camera_id: CameraId
    role: Literal["road", "driver"]
    device: str
    source_kind: SourceKind = "device"
    source: str = ""
    rtsp_path: str
    hls_path: str
    record_dir: str
    record_enabled: bool = True
    inference_enabled: bool = False
    width: int = Field(default=1920, gt=0, le=4096)
    height: int = Field(default=1080, gt=0, le=4096)
    framerate: int = Field(default=30, gt=0, le=120)


class GpsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_age_seconds: float = Field(default=5.0, gt=0, le=300)
    device_path: str = "/dev/serial/by-id/mh02-gps"


class FatigueConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    camera_id: Literal["cabin"] = "cabin"
    max_age_seconds: float = Field(default=2.0, gt=0, le=30)
    trigger_seconds: float = Field(default=2.0, gt=0, le=120)
    pre_seconds: float = Field(default=7.5, ge=0, le=120)
    post_seconds: float = Field(default=4.5, ge=0, le=120)
    source: str = "http://127.0.0.1:8080/live/cabin.m3u8"


class InferenceConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    front_model: str = "disabled"
    front_model_version: str = "unconfigured"
    front_sample_fps: float = Field(default=10.0, gt=0, le=30)
    enabled: bool = False


class RecordingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    segment_seconds: float = Field(default=600.0, gt=1, le=3600)
    retention_days: int = Field(default=7, gt=0, le=365)
    minimum_free_bytes: int = Field(default=5_000_000_000, ge=0)


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    cameras: Tuple[CameraConfig, CameraConfig]
    gps: GpsConfig = GpsConfig()
    fatigue: FatigueConfig = FatigueConfig()
    inference: InferenceConfig = InferenceConfig()
    recording: RecordingConfig = RecordingConfig()

    @model_validator(mode="after")
    def validate_camera_contract(self) -> "RuntimeConfig":
        ids = {camera.camera_id for camera in self.cameras}
        if ids != {"front", "cabin"}:
            raise ValueError("configuration requires exactly one front and one cabin camera")
        routes = {camera.rtsp_path for camera in self.cameras}
        hls_paths = {camera.hls_path for camera in self.cameras}
        if len(routes) != 2 or len(hls_paths) != 2:
            raise ValueError("front and cabin routes must be distinct")
        if self.fatigue.camera_id != "cabin":
            raise ValueError("fatigue camera must remain cabin")
        cabin = next(camera for camera in self.cameras if camera.camera_id == "cabin")
        if self.fatigue.source != f"http://127.0.0.1:8080/live/{cabin.hls_path}.m3u8":
            raise ValueError("fatigue source must match the configured cabin HLS route")
        return self


class ConfigRevision(BaseModel):
    model_config = ConfigDict(frozen=True)

    revision: int
    created_at_utc: datetime
    actor: str
    reason: str
    config: RuntimeConfig


class ConfigSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    config: RuntimeConfig
    source: Literal["active", "default"]
    restart_required: Tuple[str, ...] = ()


class ConfigMutation(BaseModel):
    model_config = ConfigDict(frozen=True)

    config: RuntimeConfig
    reason: str = Field(default="web configuration update", min_length=1, max_length=200)


class ConfigRestartRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    services: Tuple[str, ...] = Field(min_length=1)


RESTART_ALLOWLIST: Tuple[str, ...] = (
    "mh02-vlog.service",
    "mh02-cabin.service",
    "mh02-fatigue.service",
    "mh02-aggregate.service",
    "mh02-alerts.service",
    "mh02-web.service",
)


def default_config() -> RuntimeConfig:
    return RuntimeConfig(
        cameras=(
            CameraConfig(
                camera_id="front",
                role="road",
                device="/dev/v4l/by-id/mh02-front",
                rtsp_path="front",
                hls_path="front",
                record_dir="/var/lib/mh02/recordings/front",
            ),
            CameraConfig(
                camera_id="cabin",
                role="driver",
                device="/dev/v4l/by-id/mh02-cabin",
                rtsp_path="cabin",
                hls_path="cabin",
                record_dir="/var/lib/mh02/recordings/cabin",
                inference_enabled=True,
            ),
        ),
    )


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.history_path = path.with_suffix(path.suffix + ".history.jsonl")

    def snapshot(self) -> ConfigSnapshot:
        if not self.path.exists():
            return ConfigSnapshot(config=default_config(), source="default")
        return ConfigSnapshot(config=RuntimeConfig.model_validate_json(self.path.read_text(encoding="utf-8")), source="active")

    def history(self, limit: int = 20) -> List[ConfigRevision]:
        if not self.history_path.exists():
            return []
        lines = self.history_path.read_text(encoding="utf-8").splitlines()
        revisions: List[ConfigRevision] = []
        for line in lines[-limit:]:
            if line.strip():
                revisions.append(ConfigRevision.model_validate_json(line))
        return list(reversed(revisions))

    def validate(self, payload: RuntimeConfig) -> RuntimeConfig:
        return RuntimeConfig.model_validate(payload.model_dump())

    def apply(self, payload: RuntimeConfig, actor: str, reason: str) -> ConfigSnapshot:
        snapshot = self.snapshot()
        current = snapshot.config
        if snapshot.source == "default" and not self.history_path.exists():
            self._append_history(
                ConfigRevision(
                    revision=current.revision,
                    created_at_utc=datetime.now(timezone.utc),
                    actor="system",
                    reason="implicit default baseline",
                    config=current,
                ),
            )
        config = self.validate(payload).model_copy(update={"revision": current.revision + 1})
        restart_required = self.restart_required(current, config)
        revision = ConfigRevision(
            revision=config.revision,
            created_at_utc=datetime.now(timezone.utc),
            actor=actor,
            reason=reason,
            config=config,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.path, config.model_dump_json(indent=2) + "\n")
        self._append_history(revision)
        return ConfigSnapshot(config=config, source="active", restart_required=restart_required)

    def rollback(self, revision: int, actor: str) -> ConfigSnapshot:
        selected = next((item for item in self.history(limit=1000) if item.revision == revision), None)
        if selected is None:
            raise ValueError(f"configuration revision {revision} was not found")
        return self.apply(selected.config, actor, f"rollback to revision {revision}")

    def restart(self, services: Tuple[str, ...]) -> Tuple[str, ...]:
        invalid = tuple(service for service in services if service not in RESTART_ALLOWLIST)
        if invalid:
            raise ValueError(f"service is not restartable: {invalid[0]}")
        for service in services:
            subprocess.run(["systemctl", "restart", service], check=True, timeout=30)
        return services

    @staticmethod
    def restart_required(previous: RuntimeConfig, current: RuntimeConfig) -> Tuple[str, ...]:
        if previous.cameras != current.cameras:
            return ("mh02-vlog.service", "mh02-cabin.service", "mh02-fatigue.service")
        if previous.fatigue != current.fatigue:
            return ("mh02-fatigue.service", "mh02-alerts.service")
        if previous.recording != current.recording:
            return ("mh02-vlog.service", "mh02-cabin.service")
        if previous.inference != current.inference:
            return ("mh02-fatigue.service",)
        return ()

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        fd, temporary = tempfile.mkstemp(prefix="mh02-config-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _append_history(self, revision: ConfigRevision) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(revision.model_dump_json() + "\n")
