"""Tests for splitting the HOS timeline into daily ELD log sheets."""
from datetime import datetime, timezone

from django.test import SimpleTestCase

from trips.services.hos import simulate_trip
from trips.services.logs import build_daily_logs


class DailyLogTests(SimpleTestCase):
    def build(self, leg1, leg2, cycle=0):
        sim = simulate_trip(leg1, leg2, cycle_used=cycle)
        start = datetime(2025, 6, 2, 8, 0, tzinfo=timezone.utc)
        return build_daily_logs(sim.events, start, sim.cycle_used)

    def test_every_day_covers_full_24_hours(self):
        for logs in (self.build(100, 150), self.build(600, 900)):
            for day in logs:
                total = sum(v for v in day["totals"].values())
                self.assertAlmostEqual(total, 24.0, places=2)

    def test_multi_day_trip_produces_multiple_sheets(self):
        logs = self.build(1000, 1100)
        self.assertGreater(len(logs), 1)
        self.assertEqual(logs[0]["date"], "2025-06-02")

    def test_segments_are_contiguous_within_each_day(self):
        logs = self.build(700, 800, cycle=30)
        for day in logs:
            cursor = 0.0
            for segment in day["segments"]:
                self.assertAlmostEqual(segment["start_hour"], cursor, places=3)
                cursor = segment["end_hour"]
            self.assertAlmostEqual(cursor, 24.0, places=3)

    def test_daily_miles_sum_to_trip_total(self):
        logs = self.build(520, 610)
        self.assertAlmostEqual(sum(d["miles"] for d in logs), 1130, delta=1.5)
