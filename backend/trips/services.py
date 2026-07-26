"""Geocoding + routing.

Primary provider is OpenRouteService (ORS) using the heavy-goods-vehicle
profile, which is the correct routing model for a property-carrying truck.
When no ``ORS_API_KEY`` is configured the service transparently falls back to
the keyless public Nominatim (geocoding) + OSRM (routing) endpoints so the app
still runs end-to-end for local development and demos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import requests
from django.conf import settings

from hos import FuelStop

METERS_PER_MILE = 1609.344
SECONDS_PER_HOUR = 3600.0

ORS_GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

USER_AGENT = "ELD-Logger/1.0 (FMCSA HOS planner)"
TIMEOUT = 20


class RoutingError(Exception):
    """Raised when a location cannot be resolved or a route cannot be built."""


@dataclass
class GeoPoint:
    label: str          # resolved place name
    query: str          # what the user typed
    lat: float
    lon: float

    def to_dict(self) -> dict:
        return {"label": self.label, "query": self.query,
                "lat": self.lat, "lon": self.lon}


@dataclass
class RouteLeg:
    distance_miles: float
    drive_hours: float
    geometry: list[list[float]]   # [[lon, lat], ...] for drawing on the map


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

def geocode(query: str) -> GeoPoint:
    query = (query or "").strip()
    if not query:
        raise RoutingError("Empty location.")
    if settings.ORS_API_KEY:
        return _geocode_ors(query)
    return _geocode_nominatim(query)


def _geocode_ors(query: str) -> GeoPoint:
    try:
        resp = requests.get(
            ORS_GEOCODE_URL,
            params={"api_key": settings.ORS_API_KEY, "text": query,
                    "size": 1, "boundary.country": "US"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
    except requests.RequestException as exc:
        raise RoutingError(f"Geocoding failed for '{query}': {exc}") from exc
    if not features:
        raise RoutingError(f"No match for location '{query}'.")
    feat = features[0]
    lon, lat = feat["geometry"]["coordinates"]
    label = feat.get("properties", {}).get("label", query)
    return GeoPoint(label=label, query=query, lat=lat, lon=lon)


def _geocode_nominatim(query: str) -> GeoPoint:
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1,
                    "countrycodes": "us"},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json()
    except requests.RequestException as exc:
        raise RoutingError(f"Geocoding failed for '{query}': {exc}") from exc
    if not results:
        raise RoutingError(f"No match for location '{query}'.")
    r = results[0]
    return GeoPoint(label=r.get("display_name", query), query=query,
                    lat=float(r["lat"]), lon=float(r["lon"]))


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route(a: GeoPoint, b: GeoPoint) -> RouteLeg:
    """Return the driving leg between two points."""
    if settings.ORS_API_KEY:
        return _route_ors(a, b)
    return _route_osrm(a, b)


def _route_ors(a: GeoPoint, b: GeoPoint) -> RouteLeg:
    try:
        resp = requests.post(
            ORS_DIRECTIONS_URL,
            json={"coordinates": [[a.lon, a.lat], [b.lon, b.lat]]},
            headers={"Authorization": settings.ORS_API_KEY,
                     "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        feature = data["features"][0]
        summary = feature["properties"]["summary"]
        geometry = feature["geometry"]["coordinates"]
    except (requests.RequestException, KeyError, IndexError) as exc:
        raise RoutingError(
            f"Routing failed ({a.query} -> {b.query}): {exc}") from exc
    return RouteLeg(
        distance_miles=summary["distance"] / METERS_PER_MILE,
        drive_hours=summary["duration"] / SECONDS_PER_HOUR,
        geometry=geometry,
    )


def _route_osrm(a: GeoPoint, b: GeoPoint) -> RouteLeg:
    coords = f"{a.lon},{a.lat};{b.lon},{b.lat}"
    try:
        resp = requests.get(
            f"{OSRM_URL}/{coords}",
            params={"overview": "full", "geometries": "geojson"},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        r = data["routes"][0]
        geometry = r["geometry"]["coordinates"]
    except (requests.RequestException, KeyError, IndexError) as exc:
        raise RoutingError(
            f"Routing failed ({a.query} -> {b.query}): {exc}") from exc
    return RouteLeg(
        distance_miles=r["distance"] / METERS_PER_MILE,
        drive_hours=r["duration"] / SECONDS_PER_HOUR,
        geometry=geometry,
    )


# ---------------------------------------------------------------------------
# Geometry helpers (for placing stop markers along the route)
# ---------------------------------------------------------------------------

def _haversine_miles(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 3958.7613  # Earth radius in miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def point_at_fraction(geometry: list[list[float]], fraction: float) -> list[float]:
    """Return the [lon, lat] point ``fraction`` (0..1) of the way along a
    polyline, measured by great-circle distance."""
    if not geometry:
        return [0.0, 0.0]
    fraction = max(0.0, min(1.0, fraction))
    # Cumulative length of each vertex.
    lengths = [0.0]
    for (lon1, lat1), (lon2, lat2) in zip(geometry, geometry[1:]):
        lengths.append(lengths[-1] + _haversine_miles(lon1, lat1, lon2, lat2))
    total = lengths[-1]
    if total <= 0:
        return list(geometry[0])
    target = fraction * total
    for i in range(1, len(lengths)):
        if lengths[i] >= target:
            seg = lengths[i] - lengths[i - 1]
            t = 0.0 if seg <= 0 else (target - lengths[i - 1]) / seg
            lon1, lat1 = geometry[i - 1]
            lon2, lat2 = geometry[i]
            return [lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t]
    return list(geometry[-1])


# ---------------------------------------------------------------------------
# Fuel-stop planning (real stations, never exceeding the mileage cap)
# ---------------------------------------------------------------------------
#
# Fuel stations come from OpenStreetMap via the Overpass API. This is free and
# keyless, but it is community-maintained: coverage is good on major routes yet
# a station may be missing or closed since last edited. Stops are therefore
# labelled "suggested" and are never treated as guaranteed-open. The lookup is
# isolated in `_nearest_fuel_station`, so a paid/truck-specific provider
# (Google Places, HERE, Trucker Path) can be swapped in without touching the
# planning logic.

FUEL_SEARCH_RADIUS_M = 12000    # how far off the route point to accept a station
FUEL_SEARCH_BACK_MILES = 200    # how far before the cap we may stop if needed
FUEL_SEARCH_STEP_MILES = 100    # granularity of the backward search


def _nearest_fuel_station(lat: float, lon: float):
    """Return the nearest OSM fuel station to a point, or None.

    Swap this function's body to change providers; the contract is a dict
    ``{"name", "lat", "lon"}`` or ``None``.
    """
    # `nwr` covers node/way/relation; fuel stations are often mapped as ways
    # (the forecourt polygon), so `out center` gives every match a coordinate.
    query = (
        f"[out:json][timeout:15];"
        f"nwr(around:{FUEL_SEARCH_RADIUS_M},{lat},{lon})[amenity=fuel];"
        f"out center 40;"
    )
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query},
                             headers={"User-Agent": USER_AGENT}, timeout=25)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except (requests.RequestException, ValueError):
        return None
    best = None
    best_d = float("inf")
    for el in elements:
        # Nodes carry lat/lon directly; ways/relations carry a "center".
        center = el.get("center") or {}
        elat = el.get("lat", center.get("lat"))
        elon = el.get("lon", center.get("lon"))
        if elat is None or elon is None:
            continue
        d = _haversine_miles(lon, lat, elon, elat)
        if d < best_d:
            best_d = d
            name = el.get("tags", {}).get("name") or "Fuel station"
            best = {"name": name, "lat": elat, "lon": elon}
    return best


def find_fuel_stops(geometry: list[list[float]], total_miles: float,
                    max_interval: float = 1000.0) -> list[FuelStop]:
    """Plan fuel stops so the gap between fuelings never exceeds ``max_interval``.

    For each stop we look for a real station at the mileage cap; if none is
    nearby we step backward (e.g. 900, then 800 miles) until one is found, so we
    stop a little early rather than overrun the cap. If nothing is found we fall
    back to an unverified point on the route at the cap.
    """
    stops: list[FuelStop] = []
    if not geometry or total_miles <= max_interval + 1e-6:
        return stops

    last = 0.0
    # Bound the number of backward candidates we probe per stop.
    backs = [b for b in range(0, int(FUEL_SEARCH_BACK_MILES) + 1,
                              int(FUEL_SEARCH_STEP_MILES))]
    while total_miles - last > max_interval + 1e-6:
        cap = last + max_interval
        chosen = None
        for back in backs:
            cand = cap - back
            if cand <= last:
                break
            frac = cand / total_miles
            lon, lat = point_at_fraction(geometry, frac)
            station = _nearest_fuel_station(lat, lon)
            if station:
                chosen = FuelStop(mile=cand, label=station["name"],
                                  lat=station["lat"], lon=station["lon"],
                                  verified=True)
                break
        if chosen is None:
            # No station resolved; place an unverified marker on the route.
            frac = min(cap, total_miles) / total_miles
            lon, lat = point_at_fraction(geometry, frac)
            chosen = FuelStop(mile=cap, label="", lat=lat, lon=lon,
                              verified=False)
        stops.append(chosen)
        last = chosen.mile
    return stops
