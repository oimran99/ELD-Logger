"""API endpoints.

``POST /api/plan-trip/`` is the workhorse: it geocodes the three locations,
routes the two driving legs via OpenRouteService (HGV profile), runs the HOS
engine, places stop markers along the route geometry, persists the trip, and
returns everything the frontend needs to draw the map and the daily logs.
"""

from __future__ import annotations

from datetime import datetime, time

from django.conf import settings
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from hos import DutyStatus, Leg, plan_trip

from . import services
from .models import Trip
from .pdf import render_trip_pdf
from .serializers import (
    LogDetailsSerializer,
    TripInputSerializer,
    TripSerializer,
)

# Segment statuses that deserve a marker on the map.
_EVENT_STATUSES = {DutyStatus.OFF, DutyStatus.ON_DUTY, DutyStatus.SLEEPER}


def _default_start() -> datetime:
    today = datetime.now().date()
    return datetime.combine(today, time(8, 0))


def _build_stops(plan, geometry, total_miles) -> list[dict]:
    """Place a lon/lat marker for each non-driving event.

    Fuel stops snapped to a real station use that station's coordinates; every
    other event (pickup, drop-off, rest) is positioned by interpolating along
    the route at the cumulative miles driven when it occurs."""
    stops = []
    cum_miles = 0.0
    for seg in plan.segments:
        if seg.status == DutyStatus.DRIVING:
            cum_miles += seg.miles
            continue
        if seg.status not in _EVENT_STATUSES or not seg.note:
            continue

        is_fuel = seg.note.startswith("Fueling")
        if is_fuel and seg.lat is not None and seg.lon is not None:
            lat, lon = seg.lat, seg.lon
        else:
            frac = cum_miles / total_miles if total_miles > 0 else 0.0
            lon, lat = services.point_at_fraction(geometry, frac)

        stops.append({
            "note": seg.note,
            "status": seg.status.value,
            "start": seg.start.isoformat(),
            "hours": round(seg.hours, 2),
            "lat": lat,
            "lon": lon,
            "kind": "fuel" if is_fuel else "event",
            "verified": seg.verified if is_fuel else True,
            "station": seg.station,
        })
    return stops


@api_view(["POST"])
def plan_trip_view(request):
    serializer = TripInputSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        origin = services.geocode(data["current_location"])
        pickup = services.geocode(data["pickup_location"])
        dropoff = services.geocode(data["dropoff_location"])
        leg1 = services.route(origin, pickup)
        leg2 = services.route(pickup, dropoff)
    except services.RoutingError as exc:
        return Response({"error": str(exc)},
                        status=status.HTTP_502_BAD_GATEWAY)

    start_time = data.get("start_time")
    if start_time is not None:
        start_time = start_time.replace(tzinfo=None)
    else:
        start_time = _default_start()

    hos_legs = [
        Leg(leg1.distance_miles, leg1.drive_hours,
            origin.label, pickup.label, purpose="to_pickup"),
        Leg(leg2.distance_miles, leg2.drive_hours,
            pickup.label, dropoff.label, purpose="to_dropoff"),
    ]

    geometry = list(leg1.geometry) + list(leg2.geometry)
    total_miles = leg1.distance_miles + leg2.distance_miles

    # Resolve real fuel stations along the route (never exceeding 1,000 mi
    # between fuelings). Falls back to unverified route points if unavailable.
    fuel_stops = services.find_fuel_stops(geometry, total_miles)

    plan = plan_trip(hos_legs, cycle_hours_used=data["current_cycle_used"],
                     start_time=start_time, fuel_stops=fuel_stops)

    stops = _build_stops(plan, geometry, total_miles)

    route_payload = {
        "points": {
            "current": origin.to_dict(),
            "pickup": pickup.to_dict(),
            "dropoff": dropoff.to_dict(),
        },
        "geometry": geometry,  # [[lon, lat], ...]
        "legs": [
            {"from": origin.label, "to": pickup.label,
             "distance_miles": round(leg1.distance_miles, 1),
             "drive_hours": round(leg1.drive_hours, 2)},
            {"from": pickup.label, "to": dropoff.label,
             "distance_miles": round(leg2.distance_miles, 1),
             "drive_hours": round(leg2.drive_hours, 2)},
        ],
        "stops": stops,
    }

    trip = Trip.objects.create(
        current_location=data["current_location"],
        pickup_location=data["pickup_location"],
        dropoff_location=data["dropoff_location"],
        current_cycle_used=data["current_cycle_used"],
        start_time=start_time,
        result={"route": route_payload, "plan": plan.to_dict()},
    )

    return Response({
        "trip_id": trip.id,
        "inputs": {
            "current_location": data["current_location"],
            "pickup_location": data["pickup_location"],
            "dropoff_location": data["dropoff_location"],
            "current_cycle_used": data["current_cycle_used"],
            "start_time": start_time.isoformat(),
        },
        "route": route_payload,
        "plan": plan.to_dict(),
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
def trip_detail_view(request, pk: int):
    try:
        trip = Trip.objects.get(pk=pk)
    except Trip.DoesNotExist:
        return Response({"error": "Trip not found."},
                        status=status.HTTP_404_NOT_FOUND)
    return Response(TripSerializer(trip).data)


@api_view(["GET", "POST"])
def trip_pdf_view(request, pk: int):
    """Return the trip's daily logs as a PDF.

    POST accepts the optional log-header details (driver name, carrier,
    addresses, truck numbers, shipping docs); they are saved on the trip and
    used to fill the sheets. GET renders with whatever is already stored.
    """
    try:
        trip = Trip.objects.get(pk=pk)
    except Trip.DoesNotExist:
        return Response({"error": "Trip not found."},
                        status=status.HTTP_404_NOT_FOUND)

    if request.method == "POST":
        details = LogDetailsSerializer(trip, data=request.data, partial=True)
        details.is_valid(raise_exception=True)
        details.save()

    try:
        pdf_bytes = render_trip_pdf(trip)
    except ValueError as exc:
        return Response({"error": str(exc)},
                        status=status.HTTP_400_BAD_REQUEST)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    filename = f"eld-logs-trip-{trip.id}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@api_view(["GET"])
def health_view(request):
    return Response({
        "status": "ok",
        "routing_provider": (
            "openrouteservice" if settings.ORS_API_KEY
            else "osrm+nominatim (keyless fallback)"
        ),
    })
