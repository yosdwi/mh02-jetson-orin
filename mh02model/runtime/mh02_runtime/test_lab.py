from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


__test__ = False


TestScenario = Literal["closed_eyes", "yawning"]
TestSource = Literal["simulation", "live_cabin"]
TestStatus = Literal["PASS", "FAIL", "BLOCKED"]


class TestRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario: TestScenario
    source: TestSource = "simulation"
    trigger_seconds: float = Field(default=2.0, gt=0, le=30)
    post_seconds: float = Field(default=4.5, gt=0, le=60)


class TestMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    offset_seconds: float
    ear: Optional[float]
    mar: Optional[float]
    closed_eyes: bool
    yawning: bool
    source_status: Literal["fresh", "stale", "unknown"]


class TestReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_id: str
    created_at_utc: datetime
    label: Literal["SIMULATION", "LIVE_TEST"]
    scenario: TestScenario
    source: TestSource
    status: TestStatus
    lifecycle: List[str]
    metrics: List[TestMetric]
    triggered_at_offset_seconds: Optional[float]
    evidence_ready_at_offset_seconds: Optional[float]
    video_status: Literal["not_recorded_simulation", "pending_live_capture", "unavailable"]
    diagnostics: List[str]
    scenario_signature: str


def run_test(request: TestRunRequest) -> TestReport:
    created = datetime.now(timezone.utc)
    signature = hashlib.sha256(json.dumps(request.model_dump(), sort_keys=True).encode("utf-8")).hexdigest()[:16]
    report_id = f"test-{uuid.uuid4().hex}"
    if request.source == "live_cabin":
        return TestReport(
            report_id=report_id,
            created_at_utc=created,
            label="LIVE_TEST",
            scenario=request.scenario,
            source=request.source,
            status="BLOCKED",
            lifecycle=["requested", "blocked"],
            metrics=[],
            triggered_at_offset_seconds=None,
            evidence_ready_at_offset_seconds=None,
            video_status="unavailable",
            diagnostics=["live cabin test requires an explicitly provisioned cabin publisher and test capture profile"],
            scenario_signature=signature,
        )
    metrics: List[TestMetric] = []
    for index in range(19):
        offset = index * 0.5
        active = 2.0 <= offset < 4.5
        metrics.append(
            TestMetric(
                offset_seconds=offset,
                ear=0.08 if request.scenario == "closed_eyes" and active else 0.31,
                mar=0.72 if request.scenario == "yawning" and active else 0.22,
                closed_eyes=request.scenario == "closed_eyes" and active,
                yawning=request.scenario == "yawning" and active,
                source_status="fresh",
            ),
        )
    triggered_at = request.trigger_seconds + 2.0
    evidence_ready = 4.5 + request.post_seconds
    lifecycle = ["requested", "running", "active", "post", "complete", "evidence_ready"]
    return TestReport(
        report_id=report_id,
        created_at_utc=created,
        label="SIMULATION",
        scenario=request.scenario,
        source=request.source,
        status="PASS",
        lifecycle=lifecycle,
        metrics=metrics,
        triggered_at_offset_seconds=triggered_at,
        evidence_ready_at_offset_seconds=evidence_ready,
        video_status="not_recorded_simulation",
        diagnostics=["simulation is isolated from operational alerts and raw recordings"],
        scenario_signature=signature,
    )
