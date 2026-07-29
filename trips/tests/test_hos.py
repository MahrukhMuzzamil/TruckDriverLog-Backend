"""Unit tests for the HOS simulation engine (pure logic, no network/DB)."""
from django.test import SimpleTestCase

from trips.services.hos import (
    AVG_SPEED_MPH,
    CYCLE_LIMIT,
    DRIVING,
    MAX_DRIVING_PER_SHIFT,
    simulate_trip,
)


class HosEngineTests(SimpleTestCase):
    def totals(self, sim):
        result = {}
        for event in sim.events:
            result[event.kind] = result.get(event.kind, 0) + 1
        return result

    def test_short_trip_has_no_rest_or_fuel(self):
        # 100 mi + 150 mi = ~4.5h driving: fits in one shift.
        sim = simulate_trip(100, 150, cycle_used=0)
        kinds = self.totals(sim)
        self.assertNotIn("rest10", kinds)
        self.assertNotIn("fuel", kinds)
        self.assertNotIn("restart34", kinds)
        self.assertEqual(kinds["pickup"], 1)
        self.assertEqual(kinds["dropoff"], 1)

    def test_thirty_minute_break_after_eight_hours_driving(self):
        # A single 500 mi leg (~9.1h uninterrupted driving) must include a
        # 30-min break. (A 1-hr pickup would itself satisfy the break rule,
        # so the long leg must come *after* the pickup.)
        sim = simulate_trip(30, 500, cycle_used=0)
        kinds = self.totals(sim)
        self.assertGreaterEqual(kinds.get("break30", 0), 1)
        # No stretch of driving may exceed 8h without a 30+ min interruption.
        since_break = 0.0
        for event in sim.events:
            if event.status == DRIVING:
                since_break += event.duration
                self.assertLessEqual(since_break, 8.0 + 1e-6)
            elif event.duration >= 0.5 - 1e-9:
                since_break = 0.0

    def test_daily_driving_limit_forces_rest(self):
        # 1,200 miles (~21.8h driving) needs at least one 10-hr rest.
        sim = simulate_trip(600, 600, cycle_used=0)
        kinds = self.totals(sim)
        self.assertGreaterEqual(kinds.get("rest10", 0), 1)

        # Driving per shift never exceeds 11h.
        driving_in_shift = 0.0
        for event in sim.events:
            if event.status == DRIVING:
                driving_in_shift += event.duration
                self.assertLessEqual(driving_in_shift, MAX_DRIVING_PER_SHIFT + 1e-6)
            elif event.kind in ("rest10", "restart34"):
                driving_in_shift = 0.0

    def test_fuel_stop_every_thousand_miles(self):
        sim = simulate_trip(1200, 1300, cycle_used=0)
        kinds = self.totals(sim)
        self.assertEqual(kinds.get("fuel", 0), 2)  # at miles 1000 and 2000

    def test_cycle_exhaustion_triggers_34h_restart(self):
        # Starting with 69h used: almost immediately needs a restart.
        sim = simulate_trip(300, 300, cycle_used=69)
        kinds = self.totals(sim)
        self.assertGreaterEqual(kinds.get("restart34", 0), 1)
        self.assertLessEqual(sim.cycle_used, CYCLE_LIMIT)

    def test_total_miles_conserved(self):
        sim = simulate_trip(750, 480, cycle_used=10)
        driven = sum(e.miles for e in sim.events if e.status == DRIVING)
        self.assertAlmostEqual(driven, 1230, places=3)
        self.assertAlmostEqual(sim.odometer, 1230, places=3)

    def test_events_are_contiguous_and_ordered(self):
        sim = simulate_trip(900, 400, cycle_used=25)
        for previous, current in zip(sim.events, sim.events[1:]):
            self.assertAlmostEqual(previous.end, current.start, places=9)
            self.assertGreater(current.end, current.start)

    def test_driving_time_matches_average_speed(self):
        sim = simulate_trip(550, 0.0001, cycle_used=0)
        driving_hours = sum(e.duration for e in sim.events if e.status == DRIVING)
        self.assertAlmostEqual(driving_hours, 550 / AVG_SPEED_MPH, places=2)
