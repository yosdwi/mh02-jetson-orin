from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .models import JsonValue


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, JsonValue] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", record.name),
        }
        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id is not None:
            payload["correlation_id"] = str(correlation_id)
        for key in ("gps_state", "diagnostic_reason", "device_path", "reconnect_count"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def configure_logging(service: str, level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
    logging.getLogger(service).addFilter(ServiceFilter(service))


class ServiceFilter(logging.Filter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self.service
        return True


def service_status(service: str) -> Dict[str, JsonValue]:
    try:
        result = subprocess.run(
            ["systemctl", "show", service, "--no-pager", "--property=ActiveState,SubState,Result,ExecMainStatus,ExecMainStartTimestamp,ExecMainPID"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"service": service, "status": "unavailable", "reason": "systemd unavailable"}
    if result.returncode != 0:
        return {"service": service, "status": "unavailable", "reason": result.stderr.strip() or "systemd query failed"}
    values: Dict[str, JsonValue] = {"service": service}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue
        values[key] = value
    values["status"] = "healthy" if values.get("ActiveState") == "active" else "degraded"
    return values


def journal_entries(
    service: Optional[str],
    query: Optional[str],
    limit: int = 200,
) -> List[Dict[str, JsonValue]]:
    command = ["journalctl", "--no-pager", "--output=json", "--since", "24 hours ago", "--lines", str(min(max(limit, 1), 1000))]
    if service:
        command.extend(["--unit", service])
    try:
        result = subprocess.run(command, capture_output=True, check=False, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    entries: List[Dict[str, JsonValue]] = []
    for line in result.stdout.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        if query and query.lower() not in json.dumps(entry, ensure_ascii=True).lower():
            continue
        entries.append({str(key): value for key, value in entry.items() if isinstance(value, (str, int, float, bool)) or value is None})
    return entries
