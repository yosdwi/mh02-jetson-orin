from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "mh02model" / "runtime"))

from mh02_runtime.evidence import (
    coverage_gaps,
    evidence_status,
    overlay_lines,
    render_vtt,
    samples_for_segment,
    vtt_clock_source,
)
from mh02_runtime.media_verifier import verify_media
from mh02_runtime.models import AggregateSample, GpsSnapshot


class M1FollowupCorrectnessTests(unittest.TestCase):
    def sample(
        self,
        sequence: int,
        timestamp: datetime,
        media_pts_ns: Optional[int] = None,
        gps: Optional[GpsSnapshot] = None,
    ) -> AggregateSample:
        return AggregateSample(
            sequence=sequence,
            timestamp_utc=timestamp,
            monotonic_ns=sequence,
            device_id="device",
            unit_no="unit",
            media_pts_ns=media_pts_ns,
            gps=gps,
        )

    def test_moov_atom_without_decodable_media_is_not_verified(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "fake.mp4"
            path.write_bytes(b"not-media-moov")

            result = verify_media(path, decoder=lambda _path: False)

            self.assertFalse(result.verified)
            self.assertEqual("decode_failed", result.reason)

    def test_utc_fallback_is_used_when_any_sample_lacks_media_pts(self) -> None:
        start = datetime(2026, 10, 17, tzinfo=timezone.utc)
        samples = [
            self.sample(1, start + timedelta(seconds=10), media_pts_ns=0),
            self.sample(2, start + timedelta(seconds=11)),
        ]

        self.assertEqual("utc_observed", vtt_clock_source(samples, 0))
        rendered = render_vtt(samples, start, segment_start_pts_ns=0, segment_duration_seconds=12.0)
        self.assertIn("00:00:10.000 --> 00:00:11.000", rendered)

    def test_restart_segment_excludes_historical_samples(self) -> None:
        start = datetime(2026, 10, 17, tzinfo=timezone.utc)
        historical = self.sample(1, start - timedelta(seconds=1))
        current = self.sample(2, start)

        selected = samples_for_segment([historical, current], start)

        self.assertEqual([2], [sample.sequence for sample in selected])

    def test_duplicate_timestamp_samples_produce_one_cue_set(self) -> None:
        start = datetime(2026, 10, 17, tzinfo=timezone.utc)
        rendered = render_vtt(
            [self.sample(1, start), self.sample(2, start)],
            start,
        )

        self.assertEqual(3, rendered.count(" --> "))

    def test_gps_validity_does_not_infer_acceleration(self) -> None:
        timestamp = datetime(2026, 10, 17, tzinfo=timezone.utc)
        gps = GpsSnapshot(
            timestamp_utc=timestamp,
            monotonic_ns=1,
            latitude=-6.1,
            longitude=106.8,
            fix_quality=1,
            valid=True,
        )

        self.assertIn("ACC:--", overlay_lines(self.sample(1, timestamp, gps=gps))[0])

    def test_missing_recording_interval_is_partial_evidence(self) -> None:
        start = datetime(2026, 10, 17, tzinfo=timezone.utc)
        end = start + timedelta(seconds=20)
        intervals = [(start, start + timedelta(seconds=5)), (start + timedelta(seconds=15), end)]

        gaps = coverage_gaps(intervals, start, end)

        self.assertEqual([(start + timedelta(seconds=5), start + timedelta(seconds=15))], gaps)
        self.assertEqual("partial", evidence_status(intervals, start, end))
        self.assertEqual("unavailable", evidence_status([], start, end))


if __name__ == "__main__":
    unittest.main()
