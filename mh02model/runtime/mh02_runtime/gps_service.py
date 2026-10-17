from __future__ import annotations

import argparse
import logging
import re
import signal
import time
from uuid import uuid4
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Iterator, List, Optional

import serial

from .models import GpsDiagnosticReason, GpsHealth, GpsOperationalState, GpsSnapshot
from .diagnostics import configure_logging
from .store import RuntimeStore, utc_now


LOGGER = logging.getLogger("mh02.gps")
DEFAULT_NMEA_DEVICE = "/dev/serial/by-id/usb-Quectel_EC25-EUX_0123456789ABCDEF-if01-port0"
DEFAULT_AT_DEVICE = "/dev/serial/by-id/usb-Quectel_EC25-EUX_0123456789ABCDEF-if03-port0"


@dataclass(frozen=True)
class NmeaState:
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed_kph: Optional[float] = None
    altitude_m: Optional[float] = None
    fix_quality: int = 0
    satellites: int = 0
    valid: bool = False
    fix_observed_at_utc: Optional[datetime] = None


class GpsHealthTracker:
    def __init__(self, device_path: str, nmea_timeout_seconds: float, fix_max_age_seconds: float) -> None:
        self.device_path = device_path
        self.nmea_timeout_seconds = nmea_timeout_seconds
        self.fix_max_age_seconds = fix_max_age_seconds
        self.boot_id = uuid4().hex
        self.state = NmeaState()
        self.serial_accessible = False
        self.last_nmea_utc: Optional[datetime] = None
        self.last_nmea_monotonic_ns: Optional[int] = None
        self.last_valid_monotonic_ns: Optional[int] = None
        self.last_error: Optional[str] = None
        self.reason: GpsDiagnosticReason = "RECONNECTING"
        self.invalid_nmea_seen = False
        self.reconnect_count = 0
        self.retry_count = 0

    def mark_disconnected(self, reason: GpsDiagnosticReason, error: Optional[str] = None) -> None:
        self.serial_accessible = False
        self.reason = reason
        self.last_error = error
        self.retry_count += 1

    def mark_connected(self) -> None:
        self.serial_accessible = True
        self.reconnect_count += 1
        self.last_error = None

    def observe(self, sentence: str, received_at: datetime, monotonic_ns: int, parsed: Optional[NmeaState]) -> None:
        self.last_nmea_utc = received_at
        self.last_nmea_monotonic_ns = monotonic_ns
        if not has_valid_checksum(sentence):
            self.invalid_nmea_seen = True
            self.reason = "INVALID_NMEA"
            return
        if parsed is not None:
            self.state = parsed
            if parsed.valid:
                self.last_valid_monotonic_ns = monotonic_ns
                self.reason = "OK"
            else:
                self.reason = "NO_FIX"

    def health(self, now_utc: datetime, now_monotonic_ns: int) -> GpsHealth:
        nmea_age: Optional[float] = None
        if self.last_nmea_monotonic_ns is not None:
            nmea_age = max(0.0, (now_monotonic_ns - self.last_nmea_monotonic_ns) / 1_000_000_000)
        fix_age: Optional[float] = None
        if self.last_valid_monotonic_ns is not None:
            fix_age = max(0.0, (now_monotonic_ns - self.last_valid_monotonic_ns) / 1_000_000_000)

        if not self.serial_accessible:
            state: GpsOperationalState = "DISCONNECTED"
        elif nmea_age is None or nmea_age > self.nmea_timeout_seconds:
            state = "NO_SIGNAL"
            self.reason = "NMEA_TIMEOUT"
        elif not self.state.valid or self.state.fix_quality <= 0:
            state = "NO_SIGNAL"
            self.reason = "INVALID_NMEA" if self.invalid_nmea_seen else "NO_FIX"
        elif fix_age is None or fix_age > self.fix_max_age_seconds:
            state = "NO_SIGNAL"
            self.reason = "FIX_EXPIRED"
        else:
            state = "FIX"
            self.reason = "OK"

        return GpsHealth(
            state=state,
            diagnostic_reason=self.reason,
            device_path=self.device_path,
            serial_accessible=self.serial_accessible,
            nmea_last_received_utc=self.last_nmea_utc,
            nmea_last_received_monotonic_ns=self.last_nmea_monotonic_ns,
            last_valid_fix_utc=self.state.fix_observed_at_utc if self.state.valid else None,
            last_valid_fix_monotonic_ns=self.last_valid_monotonic_ns,
            fix_quality=self.state.fix_quality,
            satellites=self.state.satellites,
            fix_age_seconds=fix_age,
            last_valid_latitude=self.state.latitude if self.state.valid else None,
            last_valid_longitude=self.state.longitude if self.state.valid else None,
            last_valid_speed_kph=self.state.speed_kph if self.state.valid else None,
            last_valid_altitude_m=self.state.altitude_m if self.state.valid else None,
            last_error=self.last_error,
            reconnect_count=self.reconnect_count,
            retry_count=self.retry_count,
            heartbeat_utc=now_utc,
            heartbeat_monotonic_ns=now_monotonic_ns,
            boot_id=self.boot_id,
        )


def coordinate(raw: str, hemisphere: str) -> Optional[float]:
    if not raw or hemisphere not in ("N", "S", "E", "W"):
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    degrees = int(value // 100)
    minutes = value - (degrees * 100)
    maximum_degrees = 90 if hemisphere in ("N", "S") else 180
    if minutes >= 60 or degrees > maximum_degrees or (degrees == maximum_degrees and minutes > 0):
        return None
    result = degrees + (minutes / 60)
    return -result if hemisphere in ("S", "W") else result


def has_valid_checksum(sentence: str) -> bool:
    payload, separator, checksum = sentence.strip().partition("*")
    if not separator or len(checksum) < 2:
        return False
    try:
        expected = int(checksum[:2], 16)
    except ValueError:
        return False
    actual = 0
    checksum_payload = payload[1:] if payload.startswith("$") else payload
    for character in checksum_payload:
        actual ^= ord(character)
    return actual == expected


def nmea_fix_time(time_text: str, date_text: str, received_at: datetime) -> datetime:
    if not time_text or not date_text:
        return received_at
    try:
        parsed = datetime.strptime(f"{date_text}{time_text}", "%d%m%y%H%M%S.%f")
    except ValueError:
        try:
            parsed = datetime.strptime(f"{date_text}{time_text}", "%d%m%y%H%M%S")
        except ValueError:
            return received_at
    return parsed.replace(tzinfo=timezone.utc)


def parse_nmea(sentence: str, state: NmeaState, received_at: Optional[datetime] = None) -> Optional[NmeaState]:
    if not has_valid_checksum(sentence):
        return None
    payload = sentence.strip().partition("*")[0]
    fields = payload.split(",")
    if not fields or not fields[0].startswith("$"):
        return None
    message_type = fields[0][-3:]
    received_time = received_at or datetime.now(timezone.utc)
    if message_type == "RMC" and len(fields) >= 10:
        try:
            speed_kph = float(fields[7] or 0) * 1.852
        except ValueError:
            return None
        latitude = coordinate(fields[3], fields[4])
        longitude = coordinate(fields[5], fields[6])
        return replace(
            state,
            latitude=latitude,
            longitude=longitude,
            speed_kph=speed_kph,
            valid=fields[2] == "A" and latitude is not None and longitude is not None,
            fix_observed_at_utc=nmea_fix_time(fields[1], fields[9], received_time),
        )
    if message_type == "GGA" and len(fields) >= 10:
        try:
            fix_quality = int(fields[6] or 0)
            satellites = int(fields[7] or 0)
            altitude_m = float(fields[9] or 0)
        except ValueError:
            return None
        latitude = coordinate(fields[2], fields[3])
        longitude = coordinate(fields[4], fields[5])
        return replace(
            state,
            latitude=latitude,
            longitude=longitude,
            fix_quality=fix_quality,
            satellites=satellites,
            altitude_m=altitude_m,
            valid=fix_quality > 0 and latitude is not None and longitude is not None,
            fix_observed_at_utc=received_time,
        )
    return None


class QuectelGnss:

    def __init__(self, nmea_device: str, at_device: str, baudrate: int = 115200) -> None:
        self.nmea_device = nmea_device
        self.at_device = at_device
        self.baudrate = baudrate

    def _command(self, port: serial.Serial, command: str) -> str:
        port.reset_input_buffer()
        port.write((command + "\r").encode("ascii"))
        deadline = time.monotonic() + 3
        chunks: List[bytes] = []
        while time.monotonic() < deadline:
            chunk = port.read(port.in_waiting or 1)
            if chunk:
                chunks.append(chunk)
                if b"OK" in b"".join(chunks) or b"ERROR" in b"".join(chunks):
                    break
        return b"".join(chunks).decode("ascii", errors="ignore")

    def ensure_gnss_enabled(self) -> None:
        with serial.Serial(self.at_device, self.baudrate, timeout=0.2) as port:
            status = self._command(port, "AT+QGPS?")
            if re.search(r"\+QGPS:\s*1", status):
                LOGGER.info("GNSS already enabled on %s", self.at_device)
                return
            response = self._command(port, "AT+QGPS=1")
            if "OK" not in response:
                raise RuntimeError(f"Quectel GNSS enable failed: {response.strip()!r}")
            LOGGER.info("GNSS enabled once on %s", self.at_device)

    def read(self, stop: Event) -> Iterator[GpsSnapshot]:
        self.ensure_gnss_enabled()
        state = NmeaState()
        with serial.Serial(self.nmea_device, self.baudrate, timeout=1) as port:
            while not stop.is_set():
                raw_line = port.readline()
                if not raw_line:
                    continue
                sentence = raw_line.decode("ascii", errors="ignore").strip()
                received_at = utc_now()
                parsed = parse_nmea(sentence, state, received_at)
                if parsed is None:
                    continue
                state = parsed
                yield GpsSnapshot(
                    timestamp_utc=received_at,
                    monotonic_ns=time.monotonic_ns(),
                    latitude=state.latitude,
                    longitude=state.longitude,
                    speed_kph=state.speed_kph,
                    altitude_m=state.altitude_m,
                    fix_quality=state.fix_quality,
                    satellites=state.satellites,
                    valid=state.valid,
                    sentence=sentence,
                    fix_observed_at_utc=state.fix_observed_at_utc or received_at,
                    status="FIX" if state.valid else "NO_FIX",
                    operational_state="FIX" if state.valid else "NO_SIGNAL",
                    diagnostic_reason="OK" if state.valid else "NO_FIX",
                )


def publish_health(
    store: RuntimeStore,
    tracker: GpsHealthTracker,
    args: argparse.Namespace,
    last_health: Optional[GpsHealth],
    force: bool = False,
) -> GpsHealth:
    now_utc = utc_now()
    now_monotonic_ns = time.monotonic_ns()
    health = tracker.health(now_utc, now_monotonic_ns)
    transition = last_health is None or any(
        (
            health.state != last_health.state,
            health.diagnostic_reason != last_health.diagnostic_reason,
            health.last_error != last_health.last_error,
            health.reconnect_count != last_health.reconnect_count,
            health.retry_count != last_health.retry_count,
        ),
    )
    heartbeat_due = last_health is None or (
        now_monotonic_ns - last_health.heartbeat_monotonic_ns
    ) >= int(args.health_heartbeat_seconds * 1_000_000_000)
    if force or transition or heartbeat_due:
        store.save_gps_health(health)
        if transition:
            LOGGER.info(
                "GPS state transition",
                extra={
                    "gps_state": health.state,
                    "diagnostic_reason": health.diagnostic_reason,
                    "device_path": health.device_path or "",
                    "reconnect_count": health.reconnect_count,
                },
            )
        return health
    return last_health


def apply_runtime_config(args: argparse.Namespace) -> argparse.Namespace:
    if args.config_path is None or not Path(args.config_path).exists():
        return args
    from .configuration import ConfigStore

    gps = ConfigStore(Path(args.config_path)).snapshot().config.gps
    args.nmea_device = gps.device_path
    args.at_device = gps.at_device_path
    args.nmea_timeout_seconds = gps.nmea_timeout_seconds
    args.fix_max_age_seconds = gps.max_age_seconds
    args.health_heartbeat_seconds = gps.health_heartbeat_seconds
    args.retry_seconds = gps.reconnect_seconds
    return args


def run(args: argparse.Namespace, stop: Event) -> None:
    store = RuntimeStore(Path(args.database))
    reader = QuectelGnss(args.nmea_device, args.at_device, args.baudrate)
    tracker = GpsHealthTracker(args.nmea_device, args.nmea_timeout_seconds, args.fix_max_age_seconds)
    last_health: Optional[GpsHealth] = None
    while not stop.is_set():
        try:
            if not Path(args.nmea_device).exists() or not Path(args.at_device).exists():
                missing = args.nmea_device if not Path(args.nmea_device).exists() else args.at_device
                tracker.mark_disconnected("SERIAL_PORT_MISSING", f"serial device is missing: {missing}")
                last_health = publish_health(store, tracker, args, last_health, force=True)
                stop.wait(args.retry_seconds)
                continue
            reader.ensure_gnss_enabled()
            with serial.Serial(args.nmea_device, args.baudrate, timeout=1) as port:
                tracker.mark_connected()
                last_health = publish_health(store, tracker, args, last_health, force=True)
                nmea_state = NmeaState()
                while not stop.is_set():
                    raw_line = port.readline()
                    if not raw_line:
                        last_health = publish_health(store, tracker, args, last_health)
                        continue
                    received_at = utc_now()
                    monotonic_ns = time.monotonic_ns()
                    sentence = raw_line.decode("ascii", errors="ignore").strip()
                    parsed = parse_nmea(sentence, nmea_state, received_at)
                    tracker.observe(sentence, received_at, monotonic_ns, parsed)
                    if parsed is None:
                        last_health = publish_health(store, tracker, args, last_health)
                        continue
                    nmea_state = parsed
                    health = tracker.health(received_at, monotonic_ns)
                    store.save_gps(
                        GpsSnapshot(
                            timestamp_utc=received_at,
                            monotonic_ns=monotonic_ns,
                            latitude=parsed.latitude,
                            longitude=parsed.longitude,
                            speed_kph=parsed.speed_kph,
                            altitude_m=parsed.altitude_m,
                            fix_quality=parsed.fix_quality,
                            satellites=parsed.satellites,
                            valid=parsed.valid and health.state == "FIX",
                            sentence=sentence,
                            fix_observed_at_utc=parsed.fix_observed_at_utc or received_at,
                            status="FIX" if health.state == "FIX" else "NO_FIX",
                            operational_state=health.state,
                            diagnostic_reason=health.diagnostic_reason,
                            boot_id=tracker.boot_id,
                        ),
                    )
                    last_health = publish_health(store, tracker, args, last_health)
        except RuntimeError as exc:
            tracker.mark_disconnected("AT_FAILURE", str(exc))
            last_health = publish_health(store, tracker, args, last_health, force=True)
            stop.wait(args.retry_seconds)
        except (OSError, serial.SerialException, ValueError) as exc:
            reason = "SERIAL_PORT_MISSING" if not Path(args.nmea_device).exists() else "SERIAL_READ_ERROR"
            tracker.mark_disconnected(reason, str(exc))
            last_health = publish_health(store, tracker, args, last_health, force=True)
            stop.wait(args.retry_seconds)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="MH02 Quectel EC25 GNSS service")
    result.add_argument("--database", default="/var/lib/mh02/state/mh02.sqlite3")
    result.add_argument("--nmea-device", default=DEFAULT_NMEA_DEVICE)
    result.add_argument("--at-device", default=DEFAULT_AT_DEVICE)
    result.add_argument("--baudrate", type=int, default=115200)
    result.add_argument("--config-path", type=Path, default=Path("/etc/mh02/config.json"))
    result.add_argument("--nmea-timeout-seconds", type=float, default=5.0)
    result.add_argument("--fix-max-age-seconds", type=float, default=5.0)
    result.add_argument("--health-heartbeat-seconds", type=float, default=2.0)
    result.add_argument("--retry-seconds", type=float, default=5.0)
    return result


def main() -> int:
    configure_logging("mh02.gps")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    args = apply_runtime_config(parser().parse_args())
    run(args, stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
