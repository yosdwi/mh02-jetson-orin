from __future__ import annotations

import sys
from threading import Event
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "mh02model" / "runtime"))

from mh02_runtime.configuration import default_config
from mh02_runtime.front_inference_service import run_pipeline, validation_report
from mh02_runtime.inference_contracts import BoundingBox, DetectionObservation, InferenceCapabilities, InferenceHealth
from mh02_runtime.warning_engine import AdvisoryPolicy, candidates_for


def observation(object_class: str = "car", confidence: float = 0.9) -> DetectionObservation:
    return DetectionObservation(
        observation_id="detection-test",
        observed_at_utc=datetime(2026, 10, 17, tzinfo=timezone.utc),
        source_kind="replay_mp4",
        frame_id="front-1",
        media_pts_ns=1_000_000_000,
        object_class=object_class,
        confidence=confidence,
        bounding_box=BoundingBox(left=0.1, top=0.2, width=0.3, height=0.4),
        track_id="42",
        model_name="dashcamnet",
        model_version="candidate-1",
        model_digest_sha256="a" * 64,
    )


def test_warning_engine_only_emits_advisory_candidate_for_allowed_confident_class() -> None:
    candidate = candidates_for((observation(),), AdvisoryPolicy(confidence_threshold=0.8))[0]

    assert candidate.advisory_only is True
    assert candidate.source_kind == "replay_mp4"
    assert candidate.evidence.status == "pending"
    assert candidate.evidence.camera_id == "front"


def test_warning_engine_does_not_emit_for_low_confidence_or_unknown_class() -> None:
    assert candidates_for((observation(confidence=0.79),), AdvisoryPolicy(confidence_threshold=0.8)) == []
    assert candidates_for((observation(object_class="traffic-light"),), AdvisoryPolicy()) == []


def test_validation_report_blocks_without_verified_health_artifact() -> None:
    report = validation_report(None, detections=10, warnings=4)

    assert report.status == "BLOCKED"
    assert report.inference_status == "not_running"
    assert report.frames == 0
    assert report.detections == 0
    assert report.warnings == 0


def test_validation_report_requires_frames_from_running_inference() -> None:
    health = InferenceHealth(
        status="running",
        source_kind="replay_mp4",
        source="/tmp/authorized.mp4",
        model_name="dashcamnet",
        model_version="candidate-1",
        frames=0,
        last_update_utc=datetime(2026, 10, 17, tzinfo=timezone.utc),
        diagnostics=["pipeline has not produced a frame"],
    )

    report = validation_report(health, detections=0, warnings=0)

    assert report.status == "BLOCKED"
    assert report.frames == 0


def test_missing_deepstream_assets_write_blocked_health(tmp_path: Path, monkeypatch) -> None:
    engine = tmp_path / "model.engine"
    engine.write_bytes(b"engine")
    config = default_config().inference.model_copy(
        update={
            "enabled": True,
            "engine_path": str(engine),
            "model_config_path": str(tmp_path / "missing-pgie.txt"),
            "tracker_lib_path": str(tmp_path / "missing-tracker.so"),
            "tracker_config_path": str(tmp_path / "missing-tracker.yml"),
        },
    )
    monkeypatch.setattr(
        "mh02_runtime.front_inference_service.capabilities",
        lambda: InferenceCapabilities(deepstream_available=True, nvinfer_available=True, nvtracker_available=True, pyds_available=True),
    )

    assert run_pipeline(config, tmp_path / "events.ndjson", tmp_path / "health.json", Event()) == 2
    health = InferenceHealth.model_validate_json((tmp_path / "health.json").read_text())
    assert health.status == "blocked"
    assert "configuration asset is missing" in health.diagnostics[0]
