from __future__ import annotations

import argparse
import logging
import re
import signal
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Iterator, List, Optional

import serial

from .models import GpsSnapshot
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
                )


def run(args: argparse.Namespace, stop: Event) -> None:
    store = RuntimeStore(Path(args.database))
    reader = QuectelGnss(args.nmea_device, args.at_device, args.baudrate)
    while not stop.is_set():
        try:
            for snapshot in reader.read(stop):
                store.save_gps(snapshot)
        except (OSError, serial.SerialException, RuntimeError, ValueError) as exc:
            LOGGER.warning("GPS input unavailable: %s; retrying in 5 seconds", exc)
            stop.wait(5)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="MH02 Quectel EC25 GNSS service")
    result.add_argument("--database", default="/var/lib/mh02/state/mh02.sqlite3")
    result.add_argument("--nmea-device", default=DEFAULT_NMEA_DEVICE)
    result.add_argument("--at-device", default=DEFAULT_AT_DEVICE)
    result.add_argument("--baudrate", type=int, default=115200)
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    args = parser().parse_args()
    run(args, stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
