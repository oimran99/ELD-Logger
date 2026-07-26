"""Tests for fuel-stop planning and PDF export. Network lookups are mocked so
these run fast and offline.
Run with:  venv/Scripts/python.exe manage.py test trips
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from hos import DutyStatus, Leg, plan_trip
from trips import services
from trips.models import Trip
from trips.pdf import render_trip_pdf

# A simple west-to-east line; total mileage is supplied explicitly, decoupled
# from the geometry's own length.
GEOMETRY = [[-104.0, 39.0], [-100.0, 39.0], [-96.0, 39.0], [-92.0, 39.0],
            [-88.0, 39.0], [-84.0, 39.0], [-80.0, 39.0]]


def _gaps(stops, total):
    """Distances between successive fuelings, including start->first and
    last->end."""
    marks = [0.0] + [s.mile for s in stops] + [total]
    return [b - a for a, b in zip(marks, marks[1:])]


class FuelStopPlanningTests(SimpleTestCase):
    def test_never_exceeds_cap_when_stations_found(self):
        # A station always sits right at the cap.
        def fake(lat, lon):
            return {"name": "Love's", "lat": lat, "lon": lon}

        with patch.object(services, "_nearest_fuel_station", side_effect=fake):
            stops = services.find_fuel_stops(GEOMETRY, total_miles=2500)

        self.assertTrue(all(s.verified for s in stops))
        self.assertTrue(all(g <= 1000 + 1e-6 for g in _gaps(stops, 2500)))
        self.assertTrue(all(s.lat is not None and s.lon is not None for s in stops))

    def test_stops_early_when_no_station_at_cap(self):
        # No station at the 1000-mi cap, but one exists 100 mi earlier.
        def fake(lat, lon):
            # point_at_fraction on GEOMETRY maps fraction -> lon in [-104,-80].
            # cap (1000/2500 = 0.4) lands near lon -94.4; 900mi (0.36) near -95.4.
            # Only "find" a station for the earlier (more-western) candidate.
            return {"name": "TA", "lat": lat, "lon": lon} if lon <= -95.0 else None

        with patch.object(services, "_nearest_fuel_station", side_effect=fake):
            stops = services.find_fuel_stops(GEOMETRY, total_miles=2500)

        # First stop must be at or before 1000, and strictly under it here.
        self.assertLess(stops[0].mile, 1000)
        self.assertGreaterEqual(stops[0].mile, 800)
        self.assertTrue(all(g <= 1000 + 1e-6 for g in _gaps(stops, 2500)))

    def test_unverified_fallback_when_no_stations(self):
        with patch.object(services, "_nearest_fuel_station", return_value=None):
            stops = services.find_fuel_stops(GEOMETRY, total_miles=2500)

        self.assertTrue(all(not s.verified for s in stops))
        # Fallback places stops exactly at the cap multiples.
        self.assertEqual([s.mile for s in stops], [1000.0, 2000.0])
        self.assertTrue(all(g <= 1000 + 1e-6 for g in _gaps(stops, 2500)))

    def test_no_stops_under_one_interval(self):
        with patch.object(services, "_nearest_fuel_station", return_value=None):
            stops = services.find_fuel_stops(GEOMETRY, total_miles=800)
        self.assertEqual(stops, [])

    def test_engine_respects_planned_fuel_gaps(self):
        # Feed the planned stops through the engine and confirm the driving
        # mileage between fuelings never exceeds the cap.
        with patch.object(services, "_nearest_fuel_station", return_value=None):
            fuel_stops = services.find_fuel_stops(GEOMETRY, total_miles=2400)
        legs = [Leg(2400, 43.0, "A", "B", purpose="to_dropoff")]
        plan = plan_trip(legs, cycle_hours_used=0.0, fuel_stops=fuel_stops)

        miles_since_fuel = 0.0
        for seg in plan.segments:
            if seg.status == DutyStatus.DRIVING:
                miles_since_fuel += seg.miles
                self.assertLessEqual(round(miles_since_fuel, 3), 1000.0)
            elif seg.note.startswith("Fueling"):
                miles_since_fuel = 0.0


DETAIL_FIELDS = dict(
    driver_name="Jane Trucker", co_driver_name="", carrier_name="Acme Freight",
    main_office_address="1 Depot Rd", home_terminal_address="Dallas Yard",
    truck_trailer_numbers="T-100 / TR-200", shipping_document="BOL-42",
    shipper_commodity="Electronics",
)


def _multiday_plan():
    legs = [
        Leg(60, 1.0, "Dallas, TX", "Oklahoma City, OK", purpose="to_pickup"),
        Leg(900, 16.0, "Oklahoma City, OK", "Denver, CO", purpose="to_dropoff"),
    ]
    return plan_trip(legs, cycle_hours_used=10.0)


class PdfRenderTests(SimpleTestCase):
    def test_render_produces_valid_pdf(self):
        plan = _multiday_plan()
        trip = SimpleNamespace(
            id=1, current_cycle_used=10.0,
            result={"plan": plan.to_dict()}, **DETAIL_FIELDS,
        )
        pdf = render_trip_pdf(trip)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 2000)
        # One page per day.
        self.assertEqual(pdf.count(b"/Type /Page\n") or pdf.count(b"/Type/Page"),
                         len(plan.days))

    def test_render_without_plan_raises(self):
        trip = SimpleNamespace(id=1, current_cycle_used=0.0, result={},
                               **DETAIL_FIELDS)
        with self.assertRaises(ValueError):
            render_trip_pdf(trip)


class PdfEndpointTests(TestCase):
    def _make_trip(self):
        plan = _multiday_plan()
        return Trip.objects.create(
            current_location="Dallas, TX", pickup_location="Oklahoma City, OK",
            dropoff_location="Denver, CO", current_cycle_used=10.0,
            result={"plan": plan.to_dict()},
        )

    def test_post_details_saves_and_returns_pdf(self):
        trip = self._make_trip()
        resp = self.client.post(
            f"/api/trips/{trip.id}/pdf/",
            data=DETAIL_FIELDS, content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))
        trip.refresh_from_db()
        self.assertEqual(trip.driver_name, "Jane Trucker")
        self.assertEqual(trip.carrier_name, "Acme Freight")

    def test_get_pdf_without_details(self):
        trip = self._make_trip()
        resp = self.client.get(f"/api/trips/{trip.id}/pdf/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_pdf_404_for_missing_trip(self):
        resp = self.client.get("/api/trips/99999/pdf/")
        self.assertEqual(resp.status_code, 404)
