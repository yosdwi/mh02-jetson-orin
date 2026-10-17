from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "mh02model" / "runtime"))

from mh02_runtime.cabin_annotation_service import ObservationBuffer
from mh02_runtime.configuration import default_config
from mh02_runtime.front_inference_service import pipeline_description
from mh02_runtime.gps_service import GpsHealthTracker, NmeaState, parse_nmea
from mh02_runtime.inference_contracts import FatigueObservation
from mh02_runtime.models import AggregateSample, GpsHealth, GpsSnapshot
from mh02_runtime.overlay_composer import OverlayComposer
from mh02_runtime.store import RuntimeStore


def sentence(payload: str) -> str:
    checksum = 0
    for character in payload[1:]:
        checksum ^= ord(character)
    return f"{payload}*{checksum:02X}"


def test_gps_health_transitions_are_source_driven() -> None:
    base = datetime(2026, 10, 17, tzinfo=timezone.utc)
    tracker = GpsHealthTracker("/dev/ttyGPS", nmea_timeout_seconds=20, fix_max_age_seconds=5)
    tracker.mark_connected()
    no_fix = sentence("$GPGGA,123519,,,,,,0,00,99.99,,,,,,")
    parsed = parse_nmea(no_fix, NmeaState(), base)
    tracker.observe(no_fix, base, 1_000_000_000, parsed)
    assert tracker.health(base + timedelta(seconds=1), 2_000_000_000).state == "NO_SIGNAL"
    assert tracker.health(base + timedelta(seconds=1), 2_000_000_000).diagnostic_reason == "NO_FIX"

    valid = sentence("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,")
    parsed = parse_nmea(valid, NmeaState(), base + timedelta(seconds=2))
    tracker.observe(valid, base + timedelta(seconds=2), 3_000_000_000, parsed)
    assert tracker.health(base + timedelta(seconds=3), 4_000_000_000).state == "FIX"
    expired = tracker.health(base + timedelta(seconds=9), 10_000_000_000)
    assert expired.state == "NO_SIGNAL"
    assert expired.diagnostic_reason == "FIX_EXPIRED"

    tracker.mark_disconnected("SERIAL_PORT_MISSING")
    assert tracker.health(base + timedelta(seconds=10), 11_000_000_000).state == "DISCONNECTED"


def test_gps_health_heartbeat_expiry_is_unknown() -> None:
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    health = GpsHealth(
        state="DISCONNECTED",
        diagnostic_reason="SERIAL_PORT_MISSING",
        heartbeat_utc=now,
        heartbeat_monotonic_ns=1,
    )
    expired = health.as_of(now + timedelta(seconds=11), 10, 5)
    assert expired.state == "UNKNOWN"
    assert expired.diagnostic_reason == "HEALTH_HEARTBEAT_EXPIRED"


def test_invalid_checksum_cannot_become_a_fix() -> None:
    tracker = GpsHealthTracker("/dev/ttyGPS", 5, 5)
    tracker.mark_connected()
    bad = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*00"
    tracker.observe(bad, datetime.now(timezone.utc), 1_000_000_000, None)
    result = tracker.health(datetime.now(timezone.utc), 2_000_000_000)
    assert result.state == "NO_SIGNAL"
    assert result.diagnostic_reason == "INVALID_NMEA"


def test_front_annotated_pipeline_has_nvdsosd_and_no_terminal_fakesink() -> None:
    config = default_config().inference.model_copy(update={"annotated_stream_enabled": True})
    pipeline = pipeline_description(config)
    assert "nvdsosd name=front-osd" in pipeline
    assert "rtspclientsink" in pipeline
    assert "fakesink name=front-sink" not in pipeline


def test_front_disabled_annotation_keeps_diagnostic_sink() -> None:
    pipeline = pipeline_description(default_config().inference)
    assert "fakesink name=front-sink" in pipeline


def test_cabin_observation_matching_rejects_unrelated_frames() -> None:
    buffer = ObservationBuffer()
    observation = FatigueObservation(
        observation_id="one",
        observed_at_utc=datetime.now(timezone.utc),
        frame_id="cabin-100",
        media_pts_ns=100,
    )
    buffer.put(observation)
    assert buffer.match(100, 10) == observation
    assert buffer.match(1_000, 10) is None


def test_overlay_composer_does_not_reuse_stale_telemetry(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path / "state.sqlite3")
    now = datetime.now(timezone.utc)
    store.save_aggregate(
        AggregateSample(
            sequence=1,
            timestamp_utc=now - timedelta(seconds=10),
            monotonic_ns=1,
            device_id="device",
            unit_no="unit",
            gps=GpsSnapshot(timestamp_utc=now, monotonic_ns=1, latitude=-6.1, longitude=106.8, fix_quality=1, valid=True),
        ),
    )
    lines = OverlayComposer(store, "front", "device", "unit", max_age_seconds=2).lines()
    assert lines[0].startswith("GPS UNKNOWN")
    assert "--, --" in lines[0]
