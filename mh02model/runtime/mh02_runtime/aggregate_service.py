from __future__ import annotations

import argparse
import json
import logging
import signal
import time
from pathlib import Path
from threading import Event
from typing import Any, Dict, Tuple

import redis

from .models import AggregateSample, JsonValue
from .store import RuntimeStore, utc_now


LOGGER = logging.getLogger("mh02.aggregate")


def load_identity(path: Path) -> Tuple[str, str]:
    values = json.loads(path.read_text(encoding="utf-8"))
    return str(values.get("DEVICE_ID", "UNKNOWN")), str(values.get("UNIT_NO", "UNKNOWN"))


def json_value(value: Any) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    return str(value)


class RedisSnapshot:
    def __init__(self, url: str, key: str) -> None:
        self.client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=1, socket_connect_timeout=1)
        self.key = key

    def read(self) -> Dict[str, JsonValue]:
        raw = self.client.get(self.key)
        if raw is None:
            return {}
        value: Any = json.loads(raw)
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            return {}
        return {str(key): json_value(item) for key, item in value.items()}


def run(args: argparse.Namespace, stop: Event) -> None:
    store = RuntimeStore(Path(args.database))
    device_id, unit_no = load_identity(Path(args.identity))
    redis_snapshot = RedisSnapshot(args.redis_url, args.redis_key)
    sequence = store.next_sequence() - 1
    while not stop.is_set():
        payload: Dict[str, JsonValue] = {}
        try:
            payload = redis_snapshot.read()
        except (redis.exceptions.RedisError, json.JSONDecodeError, OSError) as exc:
            LOGGER.warning("Redis snapshot unavailable: %s", exc)
        sample_time = utc_now()
        monotonic_ns = time.monotonic_ns()
        sequence += 1
        sample = AggregateSample(
            sequence=sequence,
            timestamp_utc=sample_time,
            monotonic_ns=monotonic_ns,
            device_id=str(payload.get("deviceid", device_id)),
            unit_no=str(payload.get("unitno", unit_no)),
            gps=store.latest_gps(args.gps_max_age_seconds, sample_time),
            redis_payload=payload,
            fatigue=store.latest_fatigue(args.fatigue_max_age_seconds, sample_time),
        )
        store.save_aggregate(sample)
        stop.wait(args.interval)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="MH02 aggregate service")
    result.add_argument("--database", default="/var/lib/mh02/state/mh02.sqlite3")
    result.add_argument("--identity", default="/etc/mh02/smartd.json")
    result.add_argument("--redis-url", default="redis://127.0.0.1:6379/0")
    result.add_argument("--redis-key", default="ROW_DATA:data")
    result.add_argument("--interval", type=float, default=1.0)
    result.add_argument("--gps-max-age-seconds", type=float, default=5.0)
    result.add_argument("--fatigue-max-age-seconds", type=float, default=2.0)
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    run(parser().parse_args(), stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
