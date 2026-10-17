from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parents[1] / "mh02model" / "runtime"))

from mh02_runtime.alert_service import Episode, process_sample
from mh02_runtime.evidence import render_vtt
from mh02_runtime.fatigue_service import parser as fatigue_parser
from mh02_runtime.gps_service import NmeaState, parse_nmea
from mh02_runtime.models import AggregateSample, FatigueState, GpsSnapshot
from mh02_runtime.store import RuntimeStore


class M1CorrectnessTests(unittest.TestCase):
    def test_stale_fatigue_cannot_trigger_new_alert(self) -> None:
        now = datetime(2026, 10, 17, tzinfo=timezone.utc)
        with TemporaryDirectory() as directory:
            store = RuntimeStore(Path(directory) / "mh02.sqlite3")
            stale = FatigueState(
                timestamp_utc=now - timedelta(minutes=10),
                monotonic_ns=1,
                closed_eyes=True,
            )
            sample = AggregateSample(
                sequence=1,
                timestamp_utc=now,
                monotonic_ns=2,
                device_id="device",
                unit_no="unit",
                fatigue=stale,
            )
            episodes = {
                "closed_eyes": Episode("closed_eyes"),
                "yawning": Episode("yawning"),
            }

            for sequence in range(1, 5):
                process_sample(
                    store,
                    episodes,
                    sample.model_copy(
                        update={
                            "sequence": sequence,
                            "timestamp_utc": now + timedelta(seconds=sequence),
                            "monotonic_ns": sequence + 1,
                        },
                    ),
                    trigger_seconds=2.0,
                    pre_seconds=7.5,
                    post_seconds=4.5,
                )

            self.assertEqual([], store.alerts())

    def test_stale_gps_is_not_exposed_as_valid(self) -> None:
        now = datetime.now(timezone.utc)
        with TemporaryDirectory() as directory:
            store = RuntimeStore(Path(directory) / "mh02.sqlite3")
            store.save_gps(
                GpsSnapshot(
                    timestamp_utc=now - timedelta(days=2),
                    monotonic_ns=1,
                    latitude=-6.1,
                    longitude=106.8,
                    fix_quality=1,
                    valid=True,
                ),
            )

            snapshot = store.latest_gps()

            self.assertIsNotNone(snapshot)
            self.assertFalse(snapshot.valid)

    def test_fatigue_defaults_to_cabin_source(self) -> None:
        args = fatigue_parser().parse_args([])

        self.assertEqual("cabin", args.camera_id)
        self.assertIn("/live/cabin.m3u8", args.source)
        self.assertNotIn("/live/front.m3u8", args.source)

    def test_nmea_without_checksum_is_rejected(self) -> None:
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W"

        self.assertIsNone(parse_nmea(sentence, NmeaState()))

    def test_nmea_checksum_and_coordinate_are_preserved(self) -> None:
        sentence = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"

        parsed = parse_nmea(sentence, NmeaState())

        self.assertIsNotNone(parsed)
        self.assertTrue(parsed.valid)
        self.assertAlmostEqual(48.1173, parsed.latitude, places=4)
        self.assertAlmostEqual(11.5167, parsed.longitude, places=4)

    def test_stale_gap_does_not_close_alert_immediately(self) -> None:
        start = datetime(2026, 10, 17, tzinfo=timezone.utc)
        with TemporaryDirectory() as directory:
            store = RuntimeStore(Path(directory) / "mh02.sqlite3")
            episodes = {
                "closed_eyes": Episode("closed_eyes"),
                "yawning": Episode("yawning"),
            }
            fatigue = FatigueState(timestamp_utc=start, monotonic_ns=1, closed_eyes=True)
            for sequence in range(3):
                sample = AggregateSample(
                    sequence=sequence + 1,
                    timestamp_utc=start + timedelta(seconds=sequence),
                    monotonic_ns=sequence + 1,
                    device_id="device",
                    unit_no="unit",
                    fatigue=fatigue,
                )
                process_sample(store, episodes, sample, 2.0, 7.5, 4.5)

            stale_sample = AggregateSample(
                sequence=4,
                timestamp_utc=start + timedelta(seconds=3),
                monotonic_ns=4,
                device_id="device",
                unit_no="unit",
                fatigue=fatigue,
            )
            process_sample(store, episodes, stale_sample, 2.0, 7.5, 4.5)
            self.assertEqual("active", store.alerts()[0].state)
            self.assertEqual("stale", store.alerts()[0].source_status)

            process_sample(
                store,
                episodes,
                stale_sample.model_copy(update={"sequence": 5, "timestamp_utc": start + timedelta(seconds=6), "monotonic_ns": 5}),
                2.0,
                7.5,
                4.5,
            )

            self.assertEqual("post", store.alerts()[0].state)

    def test_vtt_uses_media_pts_without_overlapping_same_position_cues(self) -> None:
        start = datetime(2026, 10, 17, tzinfo=timezone.utc)
        samples = [
            AggregateSample(
                sequence=1,
                timestamp_utc=start + timedelta(seconds=10),
                monotonic_ns=1,
                device_id="device",
                unit_no="unit",
                media_pts_ns=0,
            ),
            AggregateSample(
                sequence=2,
                timestamp_utc=start + timedelta(seconds=11),
                monotonic_ns=2,
                device_id="device",
                unit_no="unit",
                media_pts_ns=1_000_000_000,
            ),
        ]

        rendered = render_vtt(samples, start, segment_start_pts_ns=0, segment_duration_seconds=2.0)

        self.assertIn("00:00:00.000 --> 00:00:01.000 line:5%", rendered)
        self.assertIn("00:00:01.000 --> 00:00:02.000 line:5%", rendered)


if __name__ == "__main__":
    unittest.main()
