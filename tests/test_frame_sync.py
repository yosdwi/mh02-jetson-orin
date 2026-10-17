from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "mh02model" / "runtime"))

from mh02_runtime.frame_sync import FrameIdentityManager, FrameRef, FrameResultJoiner, TelemetryCache
from mh02_runtime.models import AggregateSample


def ref(camera: str, epoch: str, sequence: int, pts: int, when: datetime) -> FrameRef:
    return FrameRef(
        camera_id=camera,
        boot_id="boot-a",
        stream_epoch=epoch,
        frame_seq=sequence,
        media_pts_ns=pts,
        capture_utc=when,
        timestamp_source="ingest_estimate",
        utc_uncertainty_ms=100,
    )


def test_joiner_only_releases_the_exact_frame_key_when_results_finish_out_of_order() -> None:
    now = 10_000
    first = ref("cabin", "epoch-a", 1, 1_000, datetime.now(timezone.utc))
    second = ref("cabin", "epoch-a", 2, 2_000, datetime.now(timezone.utc))
    joiner = FrameResultJoiner()
    joiner.register_video(first, now + 100)
    joiner.register_video(second, now + 100)

    assert joiner.register_inference(second, "F2")
    assert joiner.register_inference(first, "F1")
    assert joiner.release(first) == "F1"
    assert joiner.release(second) == "F2"
    assert joiner.metrics.exact_matches == 2


def test_joiner_rejects_camera_and_epoch_cross_contamination() -> None:
    cabin = ref("cabin", "epoch-a", 1, 1_000, datetime.now(timezone.utc))
    front = ref("front", "epoch-a", 1, 1_000, datetime.now(timezone.utc))
    new_epoch = ref("cabin", "epoch-b", 1, 1_000, datetime.now(timezone.utc))
    joiner = FrameResultJoiner()
    joiner.register_video(cabin, 100)
    assert not joiner.register_inference(front, "wrong-camera")
    assert joiner.release(cabin) is None

    joiner.register_video(cabin, 100)
    joiner.register_video(new_epoch, 100)
    assert joiner.invalidate_epoch("epoch-b") == 1
    assert joiner.register_inference(cabin, "old-epoch") is False
    assert joiner.metrics.unmatched_results >= 2


def test_joiner_accounts_for_deadlines_and_late_results() -> None:
    frame = ref("cabin", "epoch-a", 1, 1_000, datetime.now(timezone.utc))
    joiner = FrameResultJoiner()
    joiner.register_video(frame, 10)
    assert joiner.expire(11) == 1
    assert not joiner.register_inference(frame, "late")
    assert joiner.metrics.expired_frames == 1
    assert joiner.metrics.unmatched_results == 1


def test_identity_manager_diagnoses_duplicate_missing_and_discontinuous_pts() -> None:
    manager = FrameIdentityManager("front", "boot-a")
    first = manager.register(100)
    duplicate = manager.register(100)
    missing = manager.register(None)
    reset = manager.register(50)

    assert first.stream_epoch == duplicate.stream_epoch
    assert reset.stream_epoch != first.stream_epoch
    assert duplicate.frame_seq == first.frame_seq + 1
    assert missing.pts_domain == "unknown"
    assert manager.duplicate_pts == 1
    assert manager.missing_pts == 1
    assert manager.discontinuities == 1


def test_telemetry_cache_rejects_future_and_stale_samples() -> None:
    base = datetime(2026, 10, 18, tzinfo=timezone.utc)
    sample = AggregateSample(
        sequence=1,
        timestamp_utc=base + timedelta(seconds=2),
        monotonic_ns=1,
        device_id="device",
        unit_no="unit",
        boot_id="boot-a",
    )
    cache = TelemetryCache()
    cache.publish(sample, source="redis")
    before = ref("front", "epoch-a", 1, 1, base + timedelta(seconds=1))
    after = ref("front", "epoch-a", 2, 2, base + timedelta(seconds=3))
    assert cache.select(before, 5) is None
    assert cache.select(after, 5) == sample
    stale = ref("front", "epoch-a", 3, 3, base + timedelta(seconds=20))
    assert cache.select(stale, 5) is None
