"""Unit tests for the HOS scheduler. Pure Python, no Django required.

Run with:  venv/Scripts/python.exe -m unittest discover -s hos/tests -v
"""

import unittest
from datetime import datetime

from hos import DutyStatus, Leg, plan_trip
from hos import rules


def _hours(plan, status):
    return sum(s.hours for s in plan.segments if s.status == status)


def _drive_blocks(plan):
    return [s for s in plan.segments if s.status == DutyStatus.DRIVING]


class ShortTripTests(unittest.TestCase):
    """A trip well under one shift needs no resets or breaks."""

    def setUp(self):
        legs = [
            Leg(120, 2.0, "Origin", "Pickup", purpose="to_pickup"),
            Leg(150, 2.5, "Pickup", "Dropoff", purpose="to_dropoff"),
        ]
        self.plan = plan_trip(legs, cycle_hours_used=10.0,
                              start_time=datetime(2025, 1, 6, 8, 0))

    def test_total_driving_preserved(self):
        self.assertAlmostEqual(_hours(self.plan, DutyStatus.DRIVING), 4.5, places=3)

    def test_pickup_and_dropoff_on_duty(self):
        on_duty = _hours(self.plan, DutyStatus.ON_DUTY)
        # 1h pickup + 1h dropoff, no fueling (under 1000 mi).
        self.assertAlmostEqual(on_duty, 2.0, places=3)

    def test_no_reset_no_break(self):
        offs = [s for s in self.plan.segments if s.status == DutyStatus.OFF]
        self.assertEqual(offs, [])
        self.assertEqual(len(self.plan.days), 1)

    def test_cycle_accumulates(self):
        # started at 10h, added 4.5 driving + 2 on-duty = 16.5
        self.assertAlmostEqual(self.plan.cycle_hours_end, 16.5, places=3)

    def test_segments_are_contiguous(self):
        segs = self.plan.segments
        for a, b in zip(segs, segs[1:]):
            self.assertEqual(a.end, b.start)


class ThirtyMinuteBreakTests(unittest.TestCase):
    """More than 8 hours of driving must trigger a 30-minute break."""

    def setUp(self):
        # 10 hours of driving straight, no intervening on-duty stops.
        legs = [Leg(600, 10.0, "A", "B", purpose="to_dropoff")]
        self.plan = plan_trip(legs, cycle_hours_used=0.0,
                              start_time=datetime(2025, 1, 6, 6, 0))

    def test_break_inserted(self):
        breaks = [s for s in self.plan.segments
                  if s.status == DutyStatus.OFF and "30-min" in s.note]
        self.assertEqual(len(breaks), 1)
        self.assertAlmostEqual(breaks[0].hours, rules.BREAK_DURATION, places=3)

    def test_no_driving_block_exceeds_eight_since_break(self):
        run = 0.0
        for s in self.plan.segments:
            if s.status == DutyStatus.DRIVING:
                run += s.hours
                self.assertLessEqual(round(run, 6), rules.DRIVE_HOURS_BEFORE_BREAK)
            elif s.hours >= rules.BREAK_QUALIFYING_MIN:
                run = 0.0


class ElevenHourLimitTests(unittest.TestCase):
    """A trip needing >11 driving hours must span multiple shifts."""

    def setUp(self):
        # ~1400 mi @ 55mph ~= 25.5 driving hours -> needs 3 shifts.
        legs = [
            Leg(50, 1.0, "Origin", "Pickup", purpose="to_pickup"),
            Leg(1350, 24.5, "Pickup", "Dropoff", purpose="to_dropoff"),
        ]
        self.plan = plan_trip(legs, cycle_hours_used=0.0,
                              start_time=datetime(2025, 1, 6, 6, 0))

    def test_driving_never_exceeds_11_per_shift(self):
        drive_today = 0.0
        for s in self.plan.segments:
            if s.status == DutyStatus.DRIVING:
                drive_today += s.hours
                self.assertLessEqual(round(drive_today, 6),
                                     rules.MAX_DRIVE_PER_SHIFT)
            elif s.status == DutyStatus.OFF and s.hours >= rules.DAILY_RESET - 1e-6:
                drive_today = 0.0

    def test_ten_hour_resets_present(self):
        resets = [s for s in self.plan.segments
                  if s.status == DutyStatus.OFF and s.hours >= rules.DAILY_RESET - 1e-6]
        self.assertGreaterEqual(len(resets), 2)

    def test_14h_window_respected(self):
        # Between two 10h resets, the span from first on-duty to last drive
        # must never exceed 14h of driving eligibility.
        window_start = None
        for s in self.plan.segments:
            if s.status == DutyStatus.OFF and s.hours >= rules.DAILY_RESET - 1e-6:
                window_start = None
                continue
            if s.status in (DutyStatus.DRIVING, DutyStatus.ON_DUTY):
                if window_start is None:
                    window_start = s.start
                elapsed = (s.end - window_start).total_seconds() / 3600.0
                if s.status == DutyStatus.DRIVING:
                    self.assertLessEqual(round(elapsed, 6), rules.MAX_DUTY_WINDOW)

    def test_multiple_days(self):
        self.assertGreater(len(self.plan.days), 1)


class FuelStopTests(unittest.TestCase):
    """Fueling at least once per 1,000 miles."""

    def setUp(self):
        legs = [Leg(2100, 38.0, "A", "B", purpose="to_dropoff")]
        self.plan = plan_trip(legs, cycle_hours_used=0.0,
                              start_time=datetime(2025, 1, 6, 6, 0))

    def test_fuel_stops_count(self):
        fuels = [s for s in self.plan.segments if s.note == "Fueling"]
        # 2100 mi -> fuel after 1000 and after 2000 -> at least 2 stops.
        self.assertGreaterEqual(len(fuels), 2)


class DaySlicingTests(unittest.TestCase):
    def test_each_day_totals_exactly_24h(self):
        legs = [
            Leg(60, 1.0, "Origin", "Pickup", purpose="to_pickup"),
            Leg(900, 16.0, "Pickup", "Dropoff", purpose="to_dropoff"),
        ]
        plan = plan_trip(legs, cycle_hours_used=0.0,
                        start_time=datetime(2025, 1, 6, 6, 0))
        for day in plan.days:
            total = sum(day.totals.values())
            self.assertAlmostEqual(total, 24.0, places=3)

    def test_active_time_conserved_across_days(self):
        # Off-duty padding is presentational; driving + on-duty + sleeper time
        # must match the engine timeline exactly.
        legs = [Leg(700, 12.5, "A", "B", purpose="to_dropoff")]
        plan = plan_trip(legs, cycle_hours_used=0.0,
                        start_time=datetime(2025, 1, 6, 6, 0))
        active = [DutyStatus.DRIVING, DutyStatus.ON_DUTY, DutyStatus.SLEEPER]
        engine_active = sum(s.hours for s in plan.segments if s.status in active)
        day_active = sum(
            sum(d.totals[st.value] for st in active) for d in plan.days
        )
        self.assertAlmostEqual(engine_active, day_active, places=3)


class CycleLimitTests(unittest.TestCase):
    """Starting near the 70-hour ceiling forces a restart on a long trip."""

    def test_restart_when_cycle_exhausted(self):
        legs = [Leg(1200, 22.0, "A", "B", purpose="to_dropoff")]
        plan = plan_trip(legs, cycle_hours_used=65.0,
                        start_time=datetime(2025, 1, 6, 6, 0))
        restarts = [s for s in plan.segments if "34-hr restart" in s.note]
        self.assertGreaterEqual(len(restarts), 1)


if __name__ == "__main__":
    unittest.main()
