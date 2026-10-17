from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


class FrameRef(BaseModel):
    model_config = ConfigDict(frozen=True, protected_namespaces=())

    schema_version: int = Field(default=1, ge=1)
    camera_id: str = Field(min_length=1)
    boot_id: str = Field(min_length=1)
    stream_epoch: str = Field(min_length=1)
    frame_seq: int = Field(ge=0)
    media_pts_ns: Optional[int] = Field(default=None, ge=0)
    pts_domain: str = "decoder-running-time"
    capture_monotonic_ns: Optional[int] = Field(default=None, ge=0)
    capture_utc: Optional[datetime] = None
    utc_uncertainty_ms: Optional[float] = Field(default=None, ge=0)
    timestamp_source: str = "unknown"

    @property
    def key(self) -> Tuple[str, str, int]:
        return self.camera_id, self.stream_epoch, self.frame_seq


class FrameIdentityManager:
    def __init__(self, camera_id: str, boot_id: Optional[str] = None) -> None:
        self.camera_id = camera_id
        self.boot_id = boot_id or self._system_boot_id()
        self.stream_epoch = uuid.uuid4().hex
        self.frame_seq = -1
        self.last_pts_ns: Optional[int] = None
        self.duplicate_pts = 0
        self.discontinuities = 0
        self.missing_pts = 0

    @staticmethod
    def _system_boot_id() -> str:
        try:
            value = open("/proc/sys/kernel/random/boot_id", encoding="ascii").read().strip()
        except OSError:
            value = ""
        return value or f"boot-{uuid.uuid4().hex}"

    def reset_epoch(self) -> None:
        self.stream_epoch = uuid.uuid4().hex
        self.frame_seq = -1
        self.last_pts_ns = None

    def register(
        self,
        media_pts_ns: Optional[int],
        *,
        capture_utc: Optional[datetime] = None,
        capture_monotonic_ns: Optional[int] = None,
        pts_domain: str = "decoder-running-time",
        timestamp_source: str = "unknown",
        utc_uncertainty_ms: Optional[float] = None,
    ) -> FrameRef:
        if media_pts_ns is None:
            self.missing_pts += 1
        elif self.last_pts_ns is not None and media_pts_ns == self.last_pts_ns:
            self.duplicate_pts += 1
        elif self.last_pts_ns is not None and media_pts_ns < self.last_pts_ns:
            self.discontinuities += 1
            self.reset_epoch()
        self.frame_seq += 1
        if media_pts_ns is not None:
            self.last_pts_ns = media_pts_ns
        return FrameRef(
            camera_id=self.camera_id,
            boot_id=self.boot_id,
            stream_epoch=self.stream_epoch,
            frame_seq=self.frame_seq,
            media_pts_ns=media_pts_ns,
            pts_domain=pts_domain if media_pts_ns is not None else "unknown",
            capture_monotonic_ns=capture_monotonic_ns,
            capture_utc=capture_utc,
            utc_uncertainty_ms=utc_uncertainty_ms,
            timestamp_source=timestamp_source,
        )


@dataclass(frozen=True)
class JoinerMetrics:
    exact_matches: int = 0
    dropped_frames: int = 0
    expired_frames: int = 0
    unmatched_results: int = 0
    late_results: int = 0
    epoch_invalidations: int = 0


@dataclass
class _PendingFrame:
    ref: FrameRef
    deadline_ns: int
    result: Any = None


class FrameResultJoiner:
    def __init__(self, limit: int = 64) -> None:
        self.limit = max(1, limit)
        self._pending: "OrderedDict[Tuple[str, str, int], _PendingFrame]" = OrderedDict()
        self._lock = threading.Lock()
        self._metrics = JoinerMetrics()

    @property
    def metrics(self) -> JoinerMetrics:
        with self._lock:
            return self._metrics

    def register_video(self, ref: FrameRef, deadline_ns: Optional[int] = None) -> None:
        with self._lock:
            if len(self._pending) >= self.limit:
                self._pending.popitem(last=False)
                self._metrics = self._replace(self._metrics, dropped_frames=self._metrics.dropped_frames + 1)
            self._pending[ref.key] = _PendingFrame(
                ref=ref,
                deadline_ns=deadline_ns if deadline_ns is not None else time.monotonic_ns(),
            )

    def register_inference(self, ref: FrameRef, result: Any) -> bool:
        with self._lock:
            pending = self._pending.get(ref.key)
            if pending is None or pending.ref != ref:
                self._metrics = self._replace(
                    self._metrics,
                    unmatched_results=self._metrics.unmatched_results + 1,
                )
                return False
            pending.result = result
            return True

    def release(self, ref: FrameRef) -> Any:
        with self._lock:
            pending = self._pending.pop(ref.key, None)
            if pending is None or pending.ref != ref:
                self._metrics = self._replace(
                    self._metrics,
                    unmatched_results=self._metrics.unmatched_results + 1,
                )
                return None
            if pending.result is None:
                self._metrics = self._replace(
                    self._metrics,
                    late_results=self._metrics.late_results + 1,
                )
                return None
            self._metrics = self._replace(self._metrics, exact_matches=self._metrics.exact_matches + 1)
            return pending.result

    def expire(self, now_ns: Optional[int] = None) -> int:
        current = now_ns if now_ns is not None else time.monotonic_ns()
        with self._lock:
            expired = [key for key, pending in self._pending.items() if pending.deadline_ns <= current]
            for key in expired:
                self._pending.pop(key, None)
            if expired:
                self._metrics = self._replace(
                    self._metrics,
                    expired_frames=self._metrics.expired_frames + len(expired),
                )
            return len(expired)

    def invalidate_epoch(self, stream_epoch: str) -> int:
        with self._lock:
            removed = [key for key in self._pending if key[1] != stream_epoch]
            for key in removed:
                self._pending.pop(key, None)
            if removed:
                self._metrics = self._replace(
                    self._metrics,
                    epoch_invalidations=self._metrics.epoch_invalidations + len(removed),
                )
            return len(removed)

    @staticmethod
    def _replace(metrics: JoinerMetrics, **updates: int) -> JoinerMetrics:
        values = metrics.__dict__.copy()
        values.update(updates)
        return JoinerMetrics(**values)


@dataclass(frozen=True)
class TelemetryObservation:
    sample: Any
    observed_at_utc: datetime
    boot_id: str
    source: str = "unknown"
    expires_at_utc: Optional[datetime] = None


class TelemetryCache:
    def __init__(self, limit: int = 128) -> None:
        self.limit = max(1, limit)
        self._values: Deque[TelemetryObservation] = deque(maxlen=self.limit)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def publish(self, sample: Any, *, source: str = "aggregate", expires_at_utc: Optional[datetime] = None) -> None:
        observed = getattr(sample, "timestamp_utc", None) or datetime.now(timezone.utc)
        boot_id = str(getattr(sample, "boot_id", "legacy"))
        value = TelemetryObservation(sample, observed, boot_id, source, expires_at_utc)
        with self._lock:
            self._values.append(value)

    def latest(self) -> Optional[Any]:
        with self._lock:
            return self._values[-1].sample if self._values else None

    def select(self, ref: Optional[FrameRef], max_age_seconds: float) -> Optional[Any]:
        with self._lock:
            values = list(self._values)
        if not values or ref is None or ref.capture_utc is None:
            return None
        candidates = [item for item in values if item.observed_at_utc <= ref.capture_utc]
        if not candidates:
            return None
        selected = candidates[-1]
        age = (ref.capture_utc - selected.observed_at_utc).total_seconds()
        if age < 0 or age > max_age_seconds:
            return None
        if selected.expires_at_utc is not None and ref.capture_utc > selected.expires_at_utc:
            return None
        if selected.boot_id not in ("legacy", ref.boot_id):
            return None
        return selected.sample

    def start(self, reader: Callable[[], Optional[Any]], interval_seconds: float = 0.25) -> None:
        if self._thread is not None:
            return

        def refresh() -> None:
            while not self._stop.wait(interval_seconds):
                try:
                    sample = reader()
                except Exception:
                    continue
                if sample is not None:
                    self.publish(sample, source="redis-aggregate-cache")

        self._thread = threading.Thread(target=refresh, name="mh02-telemetry-cache", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
