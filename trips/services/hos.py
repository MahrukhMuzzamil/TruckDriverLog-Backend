"""FMCSA Hours-of-Service simulation for a property-carrying driver.

Implements the rules from 49 CFR Part 395 that apply under the assessment's
assumptions (70hr/8day carrier, no adverse driving conditions):

* 11-hour driving limit per shift            (§ 395.3(a)(3))
* 14-hour driving window per shift           (§ 395.3(a)(2))
* 30-minute break after 8h cumulative driving (§ 395.3(a)(3)(ii))
* 10 consecutive hours off duty resets the shift
* 70-hour/8-day on-duty cycle                (§ 395.3(b))
* 34-hour restart resets the cycle           (§ 395.3(c))
* Fuel stop at least every 1,000 miles       (assessment assumption)
* 1 hour on-duty for pickup and for drop-off (assessment assumption)

The simulator walks the trip minute-by-minute in continuous time (hours as
floats from trip start) and emits an ordered list of duty events. A separate
module slices those events into per-calendar-day ELD log sheets.

Simplification (documented deliberately): instead of tracking the rolling
8-day recap, the planner takes a 34-hour restart when the 70-hour cycle is
exhausted mid-trip. That is always a legal, conservative choice.
"""
from dataclasses import dataclass, field
from typing import List

# --- Rule constants (hours / miles) ----------------------------------------
AVG_SPEED_MPH = 55.0          # realistic average highway speed for a loaded CMV
MAX_DRIVING_PER_SHIFT = 11.0
MAX_DUTY_WINDOW = 14.0
DRIVING_BEFORE_BREAK = 8.0
BREAK_DURATION = 0.5
DAILY_REST_DURATION = 10.0
CYCLE_LIMIT = 70.0
RESTART_DURATION = 34.0
FUEL_INTERVAL_MILES = 1000.0
FUEL_STOP_DURATION = 0.5
PICKUP_DURATION = 1.0
DROPOFF_DURATION = 1.0

EPS = 1e-6

# Duty statuses as they appear on an ELD log grid.
OFF_DUTY = "off_duty"
SLEEPER = "sleeper"
DRIVING = "driving"
ON_DUTY = "on_duty"


@dataclass
class DutyEvent:
    """One contiguous block on the ELD timeline."""

    status: str        # off_duty | sleeper | driving | on_duty
    kind: str          # drive | break30 | rest10 | restart34 | fuel | pickup | dropoff
    start: float       # hours since trip start
    end: float
    label: str
    miles: float = 0.0
    odometer_start: float = 0.0
    odometer_end: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class HosSimulator:
    """Stateful walk through the trip under HOS constraints."""

    cycle_used: float
    time: float = 0.0
    odometer: float = 0.0
    shift_start: float | None = None
    driving_in_shift: float = 0.0
    driving_since_break: float = 0.0
    next_fuel_at: float = FUEL_INTERVAL_MILES
    events: List[DutyEvent] = field(default_factory=list)

    # --- internal helpers ----------------------------------------------------
    def _emit(self, status: str, kind: str, duration: float, label: str, miles: float = 0.0):
        event = DutyEvent(
            status=status,
            kind=kind,
            start=self.time,
            end=self.time + duration,
            label=label,
            miles=miles,
            odometer_start=self.odometer,
            odometer_end=self.odometer + miles,
        )
        self.events.append(event)
        self.time = event.end
        self.odometer = event.odometer_end

    def _window_left(self) -> float:
        if self.shift_start is None:
            return MAX_DUTY_WINDOW
        return MAX_DUTY_WINDOW - (self.time - self.shift_start)

    def _ensure_shift(self):
        if self.shift_start is None:
            self.shift_start = self.time

    def _rest(self):
        """10 consecutive hours off duty (sleeper berth): resets shift clocks."""
        self._emit(SLEEPER, "rest10", DAILY_REST_DURATION, "10-hr rest (sleeper berth)")
        self.shift_start = None
        self.driving_in_shift = 0.0
        self.driving_since_break = 0.0

    def _restart(self):
        """34-hour restart: resets the 70-hour/8-day cycle."""
        self._emit(OFF_DUTY, "restart34", RESTART_DURATION, "34-hr restart (cycle reset)")
        self.cycle_used = 0.0
        self.shift_start = None
        self.driving_in_shift = 0.0
        self.driving_since_break = 0.0

    def _break30(self):
        self._emit(OFF_DUTY, "break30", BREAK_DURATION, "30-min rest break")
        self.driving_since_break = 0.0

    # --- public operations -----------------------------------------------------
    def on_duty_task(self, kind: str, duration: float, label: str):
        """Non-driving on-duty work (pickup, drop-off, fueling)."""
        if self.cycle_used + duration > CYCLE_LIMIT + EPS:
            self._restart()
        self._ensure_shift()
        self._emit(ON_DUTY, kind, duration, label)
        self.cycle_used += duration
        # Any 30+ minute non-driving period satisfies the § 395.3(a)(3)(ii)
        # break requirement, even when spent on duty (e.g. fueling, loading).
        if duration >= BREAK_DURATION:
            self.driving_since_break = 0.0

    def drive(self, miles: float, label: str):
        """Drive a leg, inserting breaks / rests / restarts / fuel stops as needed."""
        remaining = miles
        while remaining > EPS:
            drive_left = MAX_DRIVING_PER_SHIFT - self.driving_in_shift
            window_left = self._window_left()
            break_left = DRIVING_BEFORE_BREAK - self.driving_since_break
            cycle_left = CYCLE_LIMIT - self.cycle_used

            if cycle_left <= EPS:
                self._restart()
                continue
            if drive_left <= EPS or window_left <= EPS:
                self._rest()
                continue
            if break_left <= EPS:
                self._break30()
                continue

            miles_to_fuel = self.next_fuel_at - self.odometer
            if miles_to_fuel <= EPS:
                self.on_duty_task("fuel", FUEL_STOP_DURATION, "Fuel stop")
                self.next_fuel_at += FUEL_INTERVAL_MILES
                continue

            hours_possible = min(drive_left, window_left, break_left, cycle_left)
            hours_needed = remaining / AVG_SPEED_MPH
            hours_to_fuel = miles_to_fuel / AVG_SPEED_MPH
            chunk_hours = min(hours_possible, hours_needed, hours_to_fuel)
            chunk_miles = chunk_hours * AVG_SPEED_MPH

            self._ensure_shift()
            self._emit(DRIVING, "drive", chunk_hours, label, miles=chunk_miles)
            self.driving_in_shift += chunk_hours
            self.driving_since_break += chunk_hours
            self.cycle_used += chunk_hours
            remaining -= chunk_miles


def simulate_trip(leg1_miles: float, leg2_miles: float, cycle_used: float) -> HosSimulator:
    """Run the full trip: drive to pickup, load, drive to drop-off, unload."""
    sim = HosSimulator(cycle_used=cycle_used)
    if leg1_miles > EPS:
        sim.drive(leg1_miles, "Driving to pickup")
    sim.on_duty_task("pickup", PICKUP_DURATION, "Pickup (loading)")
    sim.drive(leg2_miles, "Driving to drop-off")
    sim.on_duty_task("dropoff", DROPOFF_DURATION, "Drop-off (unloading)")
    return sim
