from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import tempfile
import time
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Dict, List, Tuple

import pyarrow as pa
import pyarrow.parquet as parquet

from .models import AggregateSample
from .diagnostics import configure_logging
from .store import RuntimeStore


LOGGER = logging.getLogger("mh02.datalogger")
SCHEMA = pa.schema(
    [
        ("timestamp_utc", pa.string()),
        ("monotonic_ns", pa.int64()),
        ("sequence", pa.int64()),
        ("device_id", pa.string()),
        ("unit_no", pa.string()),
        ("gps_valid", pa.bool_()),
        ("latitude", pa.float64()),
        ("longitude", pa.float64()),
        ("speed_kph", pa.float64()),
        ("altitude_m", pa.float64()),
        ("fix_quality", pa.int32()),
        ("satellites", pa.int32()),
        ("face_present", pa.bool_()),
        ("closed_eyes", pa.bool_()),
        ("yawning", pa.bool_()),
        ("ear", pa.float64()),
        ("mar", pa.float64()),
        ("redis_payload_json", pa.string()),
    ]
)


def hour_of(sample: AggregateSample) -> datetime:
    return sample.timestamp_utc.astimezone().replace(minute=0, second=0, microsecond=0)


def row_of(sample: AggregateSample) -> Dict[str, object]:
    gps = sample.gps
    fatigue = sample.fatigue
    return {
        "timestamp_utc": sample.timestamp_utc.isoformat(),
        "monotonic_ns": sample.monotonic_ns,
        "sequence": sample.sequence,
        "device_id": sample.device_id,
        "unit_no": sample.unit_no,
        "gps_valid": gps.valid if gps else False,
        "latitude": gps.latitude if gps else None,
        "longitude": gps.longitude if gps else None,
        "speed_kph": gps.speed_kph if gps else None,
        "altitude_m": gps.altitude_m if gps else None,
        "fix_quality": gps.fix_quality if gps else 0,
        "satellites": gps.satellites if gps else 0,
        "face_present": fatigue.face_present if fatigue else False,
        "closed_eyes": fatigue.closed_eyes if fatigue else False,
        "yawning": fatigue.yawning if fatigue else False,
        "ear": fatigue.ear if fatigue else None,
        "mar": fatigue.mar if fatigue else None,
        "redis_payload_json": json.dumps(sample.redis_payload, separators=(",", ":")),
    }


def hour_filename(hour: datetime) -> str:
    return f"datalog-{hour.strftime('%Y%m%d-%H')}.parquet"


def write_hour(directory: Path, hour: datetime, samples: List[AggregateSample]) -> None:
    if not samples:
        return
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / hour_filename(hour)
    if target.exists():
        return
    rows = [row_of(sample) for sample in sorted(samples, key=lambda item: item.sequence)]
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    fd, temporary = tempfile.mkstemp(prefix="datalog-", suffix=".parquet.tmp", dir=directory)
    os.close(fd)
    temporary_path = Path(temporary)
    metadata_path = target.with_suffix(target.suffix + ".json")
    try:
        parquet.write_table(table, temporary_path, compression="zstd")
        os.replace(temporary_path, target)
        metadata = {"hour_local": hour.isoformat(), "rows": len(rows), "complete": True}
        metadata_path.write_text(json.dumps(metadata, separators=(",", ":")), encoding="utf-8")
        LOGGER.info("Wrote %s rows to %s", len(rows), target)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def replay(store: RuntimeStore, buffers: Dict[datetime, Dict[int, AggregateSample]], cursor: int) -> int:
    while True:
        samples = store.samples_after(cursor, limit=1000)
        if not samples:
            return cursor
        for sample in samples:
            cursor = max(cursor, sample.sequence)
            key = hour_of(sample)
            buffers.setdefault(key, {})[sample.sequence] = sample


def flush_closed(directory: Path, buffers: Dict[datetime, Dict[int, AggregateSample]]) -> None:
    current = datetime.now().astimezone().replace(minute=0, second=0, microsecond=0)
    for hour in sorted(list(buffers)):
        if hour >= current:
            continue
        write_hour(directory, hour, list(buffers.pop(hour).values()))


def run(args: argparse.Namespace, stop: Event) -> None:
    store = RuntimeStore(Path(args.database))
    directory = Path(args.output_dir)
    buffers: Dict[datetime, Dict[int, AggregateSample]] = {}
    cursor = replay(store, buffers, 0)
    flush_closed(directory, buffers)
    while not stop.is_set():
        cursor = replay(store, buffers, cursor)
        flush_closed(directory, buffers)
        stop.wait(args.interval)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="MH02 hourly Parquet datalogger")
    result.add_argument("--database", default="/var/lib/mh02/state/mh02.sqlite3")
    result.add_argument("--output-dir", default="/var/lib/mh02/datalog")
    result.add_argument("--interval", type=float, default=1.0)
    return result


def main() -> int:
    configure_logging("mh02.datalogger")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    run(parser().parse_args(), stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
