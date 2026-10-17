from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from mh02_runtime.configuration import ConfigStore, RuntimeConfig, default_config
from mh02_runtime.store import RuntimeStore
from mh02_runtime.test_lab import TestRunRequest as LabRequest, run_test
from mh02_runtime.web_server import create_app


def test_default_configuration_keeps_front_and_cabin_routes_distinct() -> None:
    config = default_config()

    assert {camera.camera_id for camera in config.cameras} == {"front", "cabin"}
    assert {camera.hls_path for camera in config.cameras} == {"front", "cabin"}
    assert config.fatigue.source.endswith("/live/cabin.m3u8")


def test_configuration_rollback_creates_a_new_revision(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "config.json")
    initial = store.snapshot().config
    changed = initial.model_copy(update={"recording": initial.recording.model_copy(update={"retention_days": 14})})

    applied = store.apply(changed, "test", "change retention")
    rolled_back = store.rollback(initial.revision, "test")

    assert applied.config.revision == 2
    assert rolled_back.config.revision == 3
    assert rolled_back.config.recording.retention_days == initial.recording.retention_days
    assert rolled_back.restart_required == ("mh02-vlog.service", "mh02-cabin.service")


def test_configuration_restart_only_allows_declared_services(monkeypatch) -> None:
    calls = []

    def fake_run(command, check, timeout):
        calls.append((command, check, timeout))

    monkeypatch.setattr("mh02_runtime.configuration.subprocess.run", fake_run)
    store = ConfigStore(Path("/tmp/mh02-test-config.json"))

    assert store.restart(("mh02-web.service",)) == ("mh02-web.service",)
    assert calls == [(["systemctl", "restart", "mh02-web.service"], True, 30)]


def test_configuration_restart_rejects_arbitrary_commands(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "config.json")

    try:
        store.restart(("sh.service",))
    except ValueError as error:
        assert "not restartable" in str(error)
    else:
        raise AssertionError("unallowlisted service was accepted")


def test_simulation_report_is_pass_and_does_not_write_operational_alerts(tmp_path: Path) -> None:
    report = run_test(LabRequest(scenario="closed_eyes"))
    runtime_store = RuntimeStore(tmp_path / "state.sqlite3")

    assert report.status == "PASS"
    assert report.label == "SIMULATION"
    assert report.lifecycle[-1] == "evidence_ready"
    assert report.video_status == "not_recorded_simulation"
    assert runtime_store.alerts() == []


def test_live_test_profile_is_blocked_without_cabin_capture() -> None:
    report = run_test(LabRequest(scenario="yawning", source="live_cabin"))

    assert report.status == "BLOCKED"
    assert report.video_status == "unavailable"
    assert report.lifecycle == ["requested", "blocked"]


def test_web_test_lab_and_configuration_endpoints_are_integrated(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setenv("MH02_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("MH02_ADMIN_TOKEN", "test-token")
    app = create_app(
        tmp_path / "state.sqlite3",
        tmp_path / "recordings" / "front",
        tmp_path / "hls",
        tmp_path / "datalog",
        tmp_path / "clips",
    )

    with TestClient(app) as client:
        cameras = client.get("/api/cameras")
        report = client.post("/api/test-lab/run", json={"scenario": "yawning"})
        inference_health = client.get("/api/inference/health")
        inference_detections = client.get("/api/inference/detections")
        front_validation = client.post("/api/front-validation/run")
        denied = client.post("/api/config/validate", json=default_config().model_dump(mode="json"))
        effective = client.get("/api/config/effective")

    assert cameras.status_code == 200
    assert {item["camera_id"] for item in cameras.json()} == {"front", "cabin"}
    assert report.status_code == 200
    assert report.json()["status"] == "PASS"
    assert inference_health.status_code == 200
    assert inference_health.json()["status"] == "not_running"
    assert inference_detections.json() == []
    assert front_validation.json()["status"] == "BLOCKED"
    assert denied.status_code == 403
    assert effective.status_code == 200
    assert effective.json()["config"]["fatigue"]["camera_id"] == "cabin"


def test_web_configuration_apply_and_rollback_are_versioned(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MH02_CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setenv("MH02_ADMIN_TOKEN", "test-token")
    app = create_app(tmp_path / "state.sqlite3", tmp_path / "recordings", tmp_path / "hls", tmp_path / "datalog", tmp_path / "clips")
    changed = default_config().model_copy(update={"recording": default_config().recording.model_copy(update={"retention_days": 14})})

    with TestClient(app) as client:
        applied = client.post("/api/config/apply", headers={"x-mh02-admin-token": "test-token"}, json={"config": changed.model_dump(mode="json"), "reason": "test apply"})
        history = client.get("/api/config/history", headers={"x-mh02-admin-token": "test-token"})
        rolled_back = client.post("/api/config/rollback/1", headers={"x-mh02-admin-token": "test-token"})

    assert applied.status_code == 200
    assert applied.json()["config"]["revision"] == 2
    assert applied.json()["restart_required"] == ["mh02-vlog.service", "mh02-cabin.service"]
    assert history.status_code == 200
    assert {item["revision"] for item in history.json()} == {1, 2}
    assert rolled_back.status_code == 200
    assert rolled_back.json()["config"]["revision"] == 3


def test_web_test_report_can_be_retrieved_by_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MH02_CONFIG_PATH", str(tmp_path / "config.json"))
    app = create_app(tmp_path / "state.sqlite3", tmp_path / "recordings", tmp_path / "hls", tmp_path / "datalog", tmp_path / "clips")

    with TestClient(app) as client:
        created = client.post("/api/test-lab/run", json={"scenario": "closed_eyes"}).json()
        retrieved = client.get(f"/api/test-lab/reports/{created['report_id']}")

    assert retrieved.status_code == 200
    assert retrieved.json()["scenario_signature"] == created["scenario_signature"]
