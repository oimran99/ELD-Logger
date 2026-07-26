"""HOS timeline simulator.

The core entry point is :func:`plan_trip`. It consumes an ordered list of
driving :class:`Leg` objects (typically current->pickup and pickup->dropoff),
inserts the on-duty stops (pickup, drop-off, fueling) and the rest periods
required by :mod:`hos.rules`, and returns a :class:`TripPlan` holding the full
duty-status timeline plus per-calendar-day ELD log sheets.

Everything is computed in the driver's home-terminal local time. Times are
naive ``datetime`` objects (the caller decides the terminal timezone).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from . import rules


class DutyStatus(str, Enum):
    """The four ELD duty statuses, ordered to match the grid rows on a log."""

    OFF = "off_duty"          # row 1
    SLEEPER = "sleeper"       # row 2
    DRIVING = "driving"       # row 3
    ON_DUTY = "on_duty"       # row 4 (on duty, not driving)


# ---------------------------------------------------------------------------
# Inputs / outputs
# ---------------------------------------------------------------------------

@dataclass
class Leg:
    """A single driving leg produced by the routing provider."""

    distance_miles: float
    drive_hours: float
    start_label: str          # human name of where this leg starts
    end_label: str            # human name of where this leg ends
    purpose: str = "drive"    # e.g. "to_pickup", "to_dropoff"

    @property
    def avg_mph(self) -> float:
        if self.drive_hours <= 0:
            return 0.0
        return self.distance_miles / self.drive_hours


@dataclass
class FuelStop:
    """A planned fuel stop at a fixed cumulative trip mileage.

    Positions are decided upstream (by the routing/POI layer) so the engine
    stays free of geocoding; it only reads ``mile`` to know when to stop. The
    coordinates/label are carried through opaquely for the map.
    """

    mile: float                  # cumulative trip miles at which to fuel
    label: str = ""              # station name, if snapped to a real one
    lat: float | None = None
    lon: float | None = None
    verified: bool = False       # True if snapped to a real (OSM) station


@dataclass
class Segment:
    """A contiguous block of a single duty status."""

    status: DutyStatus
    start: datetime
    end: datetime
    location: str = ""
    note: str = ""
    miles: float = 0.0        # distance covered (driving segments only)
    # Populated only for fuel stops snapped to a real station.
    lat: float | None = None
    lon: float | None = None
    verified: bool = False
    station: str = ""

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "hours": round(self.hours, 4),
            "location": self.location,
            "note": self.note,
            "miles": round(self.miles, 1),
            "lat": self.lat,
            "lon": self.lon,
            "verified": self.verified,
            "station": self.station,
        }


@dataclass
class DayLog:
    """One calendar day's worth of the timeline, ready to draw on a log grid."""

    date: str                             # ISO date (YYYY-MM-DD)
    segments: list[Segment] = field(default_factory=list)
    totals: dict[str, float] = field(default_factory=dict)  # hours per status
    driving_miles: float = 0.0

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "segments": [s.to_dict() for s in self.segments],
            "totals": {k: round(v, 2) for k, v in self.totals.items()},
            "total_on_duty": round(
                self.totals.get(DutyStatus.DRIVING.value, 0.0)
                + self.totals.get(DutyStatus.ON_DUTY.value, 0.0),
                2,
            ),
            "driving_miles": round(self.driving_miles, 1),
        }


@dataclass
class TripPlan:
    """Full planning result."""

    segments: list[Segment]
    days: list[DayLog]
    total_distance_miles: float
    total_drive_hours: float
    total_duration_hours: float          # wall-clock start -> finish
    cycle_hours_start: float
    cycle_hours_end: float
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "segments": [s.to_dict() for s in self.segments],
            "days": [d.to_dict() for d in self.days],
            "summary": {
                "total_distance_miles": round(self.total_distance_miles, 1),
                "total_drive_hours": round(self.total_drive_hours, 2),
                "total_duration_hours": round(self.total_duration_hours, 2),
                "cycle_hours_start": round(self.cycle_hours_start, 2),
                "cycle_hours_end": round(self.cycle_hours_end, 2),
                "days_required": len(self.days),
            },
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

class _Sim:
    """Mutable simulation state, driven forward one activity at a time."""

    def __init__(self, start: datetime, cycle_hours_used: float,
                 fuel_stops: Optional[list[FuelStop]] = None):
        self.clock = start
        self.cycle_used = float(cycle_hours_used)   # 70/8 on-duty hours used
        self.drive_today = 0.0                      # driving since last 10h reset
        self.drive_since_break = 0.0                # driving since last break
        self.window_start: Optional[datetime] = None  # 14h window anchor
        self.trip_miles = 0.0                       # cumulative miles driven
        # Fuel stops at fixed cumulative mileages, consumed in order.
        self.fuel_queue = sorted(fuel_stops or [], key=lambda f: f.mile)
        self._fuel_idx = 0
        self.segments: list[Segment] = []
        self.warnings: list[str] = []

    # -- low level ---------------------------------------------------------

    def _emit(self, status: DutyStatus, hours: float, location: str,
              note: str, miles: float = 0.0) -> None:
        if hours <= 1e-9:
            return
        start = self.clock
        end = start + timedelta(hours=hours)
        # Merge with previous segment if same status, location and adjacent.
        if self.segments:
            prev = self.segments[-1]
            if (prev.status == status and prev.end == start
                    and prev.location == location and prev.note == note):
                prev.end = end
                prev.miles += miles
                self.clock = end
                self._post_emit(status, hours, miles)
                return
        self.segments.append(
            Segment(status=status, start=start, end=end,
                    location=location, note=note, miles=miles)
        )
        self.clock = end
        self._post_emit(status, hours, miles)

    def _post_emit(self, status: DutyStatus, hours: float, miles: float) -> None:
        """Update HOS counters after a block of time is laid down."""
        if status == DutyStatus.DRIVING:
            self.drive_today += hours
            self.drive_since_break += hours
            self.cycle_used += hours
            self.trip_miles += miles
            if self.window_start is None:
                self.window_start = self.segments[-1].start
        elif status == DutyStatus.ON_DUTY:
            self.cycle_used += hours
            if self.window_start is None:
                self.window_start = self.segments[-1].start
            if hours >= rules.BREAK_QUALIFYING_MIN:
                self.drive_since_break = 0.0
        else:  # OFF or SLEEPER
            if hours >= rules.BREAK_QUALIFYING_MIN:
                self.drive_since_break = 0.0

    # -- rest / reset activities ------------------------------------------

    def take_break(self, location: str) -> None:
        self._emit(DutyStatus.OFF, rules.BREAK_DURATION, location,
                   "30-min break (395.3(a)(3)(ii))")

    def take_daily_reset(self, location: str, note: str = "10-hr off-duty reset") -> None:
        self._emit(DutyStatus.OFF, rules.DAILY_RESET, location, note)
        self.drive_today = 0.0
        self.drive_since_break = 0.0
        self.window_start = None

    def take_cycle_restart(self, location: str) -> None:
        self._emit(DutyStatus.OFF, rules.CYCLE_RESTART, location,
                   "34-hr restart (395.3(c))")
        self.cycle_used = 0.0
        self.drive_today = 0.0
        self.drive_since_break = 0.0
        self.window_start = None

    def _next_fuel(self) -> Optional[FuelStop]:
        if self._fuel_idx < len(self.fuel_queue):
            return self.fuel_queue[self._fuel_idx]
        return None

    def fuel(self, stop: FuelStop, fallback_location: str) -> None:
        location = stop.label or fallback_location
        note = f"Fueling — {stop.label}" if stop.label else "Fueling"
        start = self.clock
        end = start + timedelta(hours=rules.FUEL_DURATION)
        self.segments.append(Segment(
            status=DutyStatus.ON_DUTY, start=start, end=end,
            location=location, note=note, miles=0.0,
            lat=stop.lat, lon=stop.lon, verified=stop.verified,
            station=stop.label,
        ))
        self.clock = end
        self._post_emit(DutyStatus.ON_DUTY, rules.FUEL_DURATION, 0.0)
        self._fuel_idx += 1

    # -- capacity helpers --------------------------------------------------

    def window_elapsed(self) -> float:
        if self.window_start is None:
            return 0.0
        return (self.clock - self.window_start).total_seconds() / 3600.0

    def remaining_window(self) -> float:
        if self.window_start is None:
            return rules.MAX_DUTY_WINDOW
        return rules.MAX_DUTY_WINDOW - self.window_elapsed()

    def remaining_drive_shift(self) -> float:
        return rules.MAX_DRIVE_PER_SHIFT - self.drive_today

    def remaining_before_break(self) -> float:
        return rules.DRIVE_HOURS_BEFORE_BREAK - self.drive_since_break

    def remaining_cycle(self) -> float:
        return rules.CYCLE_LIMIT_HOURS - self.cycle_used

    # -- on-duty (non-driving) task ---------------------------------------

    def do_on_duty(self, hours: float, location: str, note: str) -> None:
        """Perform an on-duty, non-driving task (pickup, drop-off)."""
        # Make room in the 14h window / 70h cycle if needed.
        if self.remaining_window() < hours:
            self.take_daily_reset(location,
                                  "10-hr reset (insufficient 14-hr window)")
        if self.remaining_cycle() < hours:
            self.warnings.append(
                f"70-hr cycle reached before '{note}'; inserting 34-hr restart.")
            self.take_cycle_restart(location)
        self._emit(DutyStatus.ON_DUTY, hours, location, note)

    # -- driving -----------------------------------------------------------

    def drive_leg(self, leg: Leg) -> None:
        """Consume an entire driving leg, inserting stops/rests as required."""
        remaining_hours = leg.drive_hours
        mph = leg.avg_mph
        # guard against pathological zero-speed legs
        if mph <= 0 and remaining_hours > 0:
            mph = leg.distance_miles / remaining_hours if remaining_hours else 0.0

        while remaining_hours > 1e-6:
            # Ensure we are legal to drive at all right now.
            if self.remaining_cycle() <= 1e-6:
                self.warnings.append(
                    "70-hr cycle exhausted mid-trip; inserting 34-hr restart.")
                self.take_cycle_restart(leg.start_label)
            if self.remaining_drive_shift() <= 1e-6 or self.remaining_window() <= 1e-6:
                self.take_daily_reset(leg.start_label)
            if self.remaining_before_break() <= 1e-6:
                self.take_break(leg.start_label)

            # Time until the next planned fuel stop (a fixed trip mileage).
            next_fuel = self._next_fuel()
            if next_fuel is not None and mph > 0:
                hours_to_fuel = max(0.0, (next_fuel.mile - self.trip_miles) / mph)
            else:
                hours_to_fuel = float("inf")

            drive_now = min(
                remaining_hours,
                self.remaining_drive_shift(),
                self.remaining_window(),
                self.remaining_before_break(),
                self.remaining_cycle(),
                hours_to_fuel,
            )
            drive_now = max(drive_now, 0.0)

            if drive_now <= 1e-6:
                # Nothing drivable; force the tightest reset and retry.
                self.take_daily_reset(leg.start_label)
                continue

            miles_now = drive_now * mph
            self._emit(DutyStatus.DRIVING, drive_now, leg.start_label,
                       f"Driving {leg.start_label} → {leg.end_label}",
                       miles=miles_now)
            remaining_hours -= drive_now

            # If we've reached the next planned fuel mileage, fuel now.
            next_fuel = self._next_fuel()
            if next_fuel is not None and self.trip_miles >= next_fuel.mile - 1e-3:
                self.fuel(next_fuel, leg.end_label + " (en route)")


# ---------------------------------------------------------------------------
# Day slicing
# ---------------------------------------------------------------------------

def _split_into_days(segments: list[Segment]) -> list[DayLog]:
    """Clip the timeline at every local midnight into per-day logs."""
    days: list[DayLog] = []
    if not segments:
        return days

    by_date: dict[str, DayLog] = {}

    for seg in segments:
        cursor = seg.start
        while cursor < seg.end:
            day_end = datetime(cursor.year, cursor.month, cursor.day) + timedelta(days=1)
            piece_end = min(seg.end, day_end)
            date_key = cursor.strftime("%Y-%m-%d")
            day = by_date.get(date_key)
            if day is None:
                day = DayLog(date=date_key)
                by_date[date_key] = day
            piece = Segment(
                status=seg.status,
                start=cursor,
                end=piece_end,
                location=seg.location,
                note=seg.note,
                miles=seg.miles * ((piece_end - cursor) / (seg.end - seg.start))
                if seg.end > seg.start else 0.0,
            )
            day.segments.append(piece)
            cursor = piece_end

    for date_key in sorted(by_date):
        day = by_date[date_key]
        day.segments.sort(key=lambda s: s.start)
        _pad_day_off_duty(day, date_key)
        totals = {s.value: 0.0 for s in DutyStatus}
        miles = 0.0
        for piece in day.segments:
            totals[piece.status.value] += piece.hours
            miles += piece.miles
        day.totals = totals
        day.driving_miles = miles
        days.append(day)

    return days


def _pad_day_off_duty(day: DayLog, date_key: str) -> None:
    """Fill the parts of the 24h day not covered by the active trip with
    off-duty segments, so every log sheet spans exactly midnight to midnight."""
    day_start = datetime.strptime(date_key, "%Y-%m-%d")
    day_end = day_start + timedelta(days=1)
    if not day.segments:
        day.segments.append(Segment(DutyStatus.OFF, day_start, day_end,
                                    note="Off duty"))
        return
    first = day.segments[0]
    if first.start > day_start:
        day.segments.insert(0, Segment(DutyStatus.OFF, day_start, first.start,
                                       note="Off duty"))
    last = day.segments[-1]
    if last.end < day_end:
        day.segments.append(Segment(DutyStatus.OFF, last.end, day_end,
                                    note="Off duty"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def default_fuel_stops(total_miles: float,
                       interval: float = rules.FUEL_INTERVAL_MILES) -> list[FuelStop]:
    """Evenly spaced (unverified) fuel stops every ``interval`` miles.

    Used when no real stations have been resolved upstream. Each stop sits at a
    fixed cumulative mileage so the gap between fuelings never exceeds
    ``interval``.
    """
    stops: list[FuelStop] = []
    mile = interval
    while mile < total_miles - 1e-6:
        stops.append(FuelStop(mile=mile, label="", verified=False))
        mile += interval
    return stops


def plan_trip(
    legs: list[Leg],
    cycle_hours_used: float,
    start_time: Optional[datetime] = None,
    fuel_stops: Optional[list[FuelStop]] = None,
) -> TripPlan:
    """Build a compliant HOS plan.

    Legs are expected in travel order. Convention: the first leg's purpose is
    ``"to_pickup"`` and the leg whose ``purpose == "to_dropoff"`` is followed by
    a drop-off stop. A 1-hour pickup is inserted after the leg that arrives at
    the pickup, and a 1-hour drop-off after the final leg.

    ``fuel_stops`` lets the caller supply real (station-snapped) fuel stops at
    fixed cumulative mileages. When omitted, evenly spaced stops every
    ``FUEL_INTERVAL_MILES`` are used.
    """
    if start_time is None:
        start_time = datetime(2025, 1, 6, 8, 0)  # a Monday 08:00 by default

    total_distance = sum(l.distance_miles for l in legs)
    if fuel_stops is None:
        fuel_stops = default_fuel_stops(total_distance)

    sim = _Sim(start=start_time, cycle_hours_used=cycle_hours_used,
               fuel_stops=fuel_stops)
    cycle_start = sim.cycle_used

    for leg in legs:
        sim.drive_leg(leg)
        if leg.purpose == "to_pickup":
            sim.do_on_duty(rules.PICKUP_DROPOFF_DURATION, leg.end_label,
                           "Pickup (loading)")
        elif leg.purpose == "to_dropoff":
            sim.do_on_duty(rules.PICKUP_DROPOFF_DURATION, leg.end_label,
                           "Drop-off (unloading)")

    segments = sim.segments
    days = _split_into_days(segments)

    total_drive = sum(l.drive_hours for l in legs)
    duration = ((segments[-1].end - segments[0].start).total_seconds() / 3600.0
                if segments else 0.0)

    return TripPlan(
        segments=segments,
        days=days,
        total_distance_miles=total_distance,
        total_drive_hours=total_drive,
        total_duration_hours=duration,
        cycle_hours_start=cycle_start,
        cycle_hours_end=sim.cycle_used,
        warnings=sim.warnings,
    )
