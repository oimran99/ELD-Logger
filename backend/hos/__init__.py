"""FMCSA Hours-of-Service (HOS) scheduling engine.

Framework-agnostic pure-Python package. Given driving legs and the driver's
current cycle usage, it produces a compliant, time-stamped duty-status timeline
and slices it into per-day ELD log sheets.
"""

from .scheduler import (
    DutyStatus,
    Leg,
    Segment,
    FuelStop,
    TripPlan,
    DayLog,
    plan_trip,
    default_fuel_stops,
)

__all__ = [
    "DutyStatus",
    "Leg",
    "Segment",
    "FuelStop",
    "TripPlan",
    "DayLog",
    "plan_trip",
    "default_fuel_stops",
]
