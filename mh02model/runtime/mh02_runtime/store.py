from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

from .models import AlertEvent, AggregateSample, FatigueState, GpsHealth, GpsSnapshot


class RuntimeStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.latest_path = self.database_path.parent.parent / "snapshots" / "latest-aggregate.json"
        self.latest_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS gps_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monotonic_ns INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gps_health_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    heartbeat_monotonic_ns INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fatigue_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monotonic_ns INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS aggregate_samples (
                    sequence INTEGER PRIMARY KEY,
                    monotonic_ns INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alert_events (
                    id TEXT PRIMARY KEY,
                    started_at_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS service_cursors (
                    service_name TEXT PRIMARY KEY,
                    sequence INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS test_reports (
                    report_id TEXT PRIMARY KEY,
                    created_at_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def save_gps(self, snapshot: GpsSnapshot) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO gps_snapshots (monotonic_ns, payload_json) VALUES (?, ?)",
                (snapshot.monotonic_ns, snapshot.model_dump_json()),
            )
            connection.execute(
                "DELETE FROM gps_snapshots WHERE id NOT IN "
                "(SELECT id FROM gps_snapshots ORDER BY id DESC LIMIT 600)",
            )

    def latest_gps(self, max_age_seconds: float = 5.0, as_of: Optional[datetime] = None) -> Optional[GpsSnapshot]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM gps_snapshots ORDER BY id DESC LIMIT 1",
            ).fetchone()
        if row is None:
            return None
        snapshot = GpsSnapshot.model_validate_json(row["payload_json"])
        return snapshot.as_of(as_of or utc_now(), max_age_seconds)

    def save_gps_health(self, health: GpsHealth) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO gps_health_snapshots (heartbeat_monotonic_ns, payload_json) VALUES (?, ?)",
                (health.heartbeat_monotonic_ns, health.model_dump_json()),
            )
            connection.execute(
                "DELETE FROM gps_health_snapshots WHERE id NOT IN "
                "(SELECT id FROM gps_health_snapshots ORDER BY id DESC LIMIT 1200)",
            )

    def latest_gps_health(
        self,
        heartbeat_max_age_seconds: float = 10.0,
        fix_max_age_seconds: float = 5.0,
        as_of: Optional[datetime] = None,
    ) -> Optional[GpsHealth]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM gps_health_snapshots ORDER BY id DESC LIMIT 1",
            ).fetchone()
        if row is None:
            return None
        health = GpsHealth.model_validate_json(row["payload_json"])
        return health.as_of(as_of or utc_now(), heartbeat_max_age_seconds, fix_max_age_seconds)

    def save_fatigue(self, state: FatigueState) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO fatigue_snapshots (monotonic_ns, payload_json) VALUES (?, ?)",
                (state.monotonic_ns, state.model_dump_json()),
            )
            connection.execute(
                "DELETE FROM fatigue_snapshots WHERE id NOT IN "
                "(SELECT id FROM fatigue_snapshots ORDER BY id DESC LIMIT 600)",
            )

    def latest_fatigue(self, max_age_seconds: float = 2.0, as_of: Optional[datetime] = None) -> Optional[FatigueState]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM fatigue_snapshots ORDER BY id DESC LIMIT 1",
            ).fetchone()
        if row is None:
            return None
        state = FatigueState.model_validate_json(row["payload_json"])
        return state if state.is_fresh(as_of or utc_now(), max_age_seconds) else None

    def next_sequence(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COALESCE(MAX(sequence), 0) + 1 AS next FROM aggregate_samples").fetchone()
        return int(row["next"])

    def save_aggregate(self, sample: AggregateSample) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO aggregate_samples (sequence, monotonic_ns, payload_json) VALUES (?, ?, ?)",
                (sample.sequence, sample.monotonic_ns, sample.model_dump_json()),
            )
            connection.execute(
                "DELETE FROM aggregate_samples WHERE sequence NOT IN "
                "(SELECT sequence FROM aggregate_samples ORDER BY sequence DESC LIMIT 86400)",
            )
        fd, temporary_path = tempfile.mkstemp(prefix="latest-aggregate-", suffix=".json", dir=self.latest_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(sample.model_dump_json(indent=2))
                handle.write("\n")
            os.replace(temporary_path, self.latest_path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def samples_after(self, sequence: int, limit: int = 120) -> List[AggregateSample]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM aggregate_samples WHERE sequence > ? "
                "ORDER BY sequence ASC LIMIT ?",
                (sequence, limit),
            ).fetchall()
        return [AggregateSample.model_validate_json(row["payload_json"]) for row in rows]

    def latest_aggregate(self) -> Optional[AggregateSample]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM aggregate_samples ORDER BY sequence DESC LIMIT 1",
            ).fetchone()
        return None if row is None else AggregateSample.model_validate_json(row["payload_json"])

    def save_alert(self, event: AlertEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO alert_events (id, started_at_utc, payload_json) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET started_at_utc=excluded.started_at_utc, payload_json=excluded.payload_json",
                (event.id, event.started_at_utc.isoformat(), event.model_dump_json()),
            )
            connection.execute(
                "DELETE FROM alert_events WHERE id NOT IN "
                "(SELECT id FROM alert_events ORDER BY started_at_utc DESC LIMIT 5000)",
            )

    def alerts(self, limit: int = 500) -> List[AlertEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM alert_events ORDER BY started_at_utc DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [AlertEvent.model_validate_json(row["payload_json"]) for row in rows]

    def open_alerts(self) -> List[AlertEvent]:
        return [event for event in reversed(self.alerts(5000)) if event.state != "complete"]

    def load_cursor(self, service_name: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT sequence FROM service_cursors WHERE service_name = ?",
                (service_name,),
            ).fetchone()
        return 0 if row is None else int(row["sequence"])

    def save_cursor(self, service_name: str, sequence: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO service_cursors (service_name, sequence) VALUES (?, ?) "
                "ON CONFLICT(service_name) DO UPDATE SET sequence=excluded.sequence",
                (service_name, sequence),
            )

    def save_test_report(self, report_id: str, created_at_utc: datetime, payload_json: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO test_reports (report_id, created_at_utc, payload_json) VALUES (?, ?, ?) "
                "ON CONFLICT(report_id) DO UPDATE SET created_at_utc=excluded.created_at_utc, payload_json=excluded.payload_json",
                (report_id, created_at_utc.isoformat(), payload_json),
            )
            connection.execute(
                "DELETE FROM test_reports WHERE report_id NOT IN "
                "(SELECT report_id FROM test_reports ORDER BY created_at_utc DESC LIMIT 200)",
            )

    def test_reports(self, limit: int = 50) -> List[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM test_reports ORDER BY created_at_utc DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [str(row["payload_json"]) for row in rows]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
