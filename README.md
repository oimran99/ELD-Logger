# ELD Trip Planner

Takes a truck driver's trip details and produces **FMCSA-compliant route
instructions** and **filled-out ELD daily log sheets**.

- **Inputs:** current location, pickup location, drop-off location, current
  cycle hours used (70 hr / 8 day).
- **Outputs:** an interactive route map with rest/fuel/stop markers, and one
  drawn daily-log grid per calendar day of the trip.

Assumptions: property-carrying driver, 70 hr / 8 day cycle, no adverse driving
conditions, fueling at least every 1,000 miles, 1 hour each for pickup and
drop-off.

## Architecture

```
ELD-Logger/
├── backend/                 Django + DRF API
│   ├── hos/                 ← HOS scheduling engine (pure Python, no Django)
│   │   ├── rules.py         FMCSA constants (49 CFR Part 395)
│   │   ├── scheduler.py     timeline simulator + per-day log slicing
│   │   └── tests/           15 unit tests for the engine
│   ├── trips/               API app: services (geocode/route), views, models
│   └── config/              Django project settings/urls
└── frontend/                React (Vite) + Leaflet
    └── src/components/       TripForm, RouteMap, LogSheet, TripSummary
```

The **HOS engine** (`backend/hos/`) is the core. It is framework-agnostic and
fully unit-tested. Given driving legs + the driver's cycle usage it enforces:

| Rule | Limit |
|------|-------|
| Driving per shift | 11 hr (after 10 hr off) |
| On-duty window | 14 hr |
| 30-minute break | required after 8 hr driving |
| Cycle | 70 hr / 8 day (34-hr restart when exhausted) |
| Fuel | on-duty stop every ≤1,000 mi |
| Pickup / drop-off | 1 hr on-duty each |

It returns a duty-status timeline sliced into midnight-to-midnight days, ready
to draw on the log grid.

**Routing:** OpenRouteService (heavy-goods-vehicle profile) when `ORS_API_KEY`
is set; otherwise it falls back to the keyless public Nominatim (geocoding) +
OSRM (routing) endpoints, so the app runs out of the box.

**Fuel stops:** planned so the gap between fuelings never exceeds 1,000 miles.
For each stop the app looks for a real fuel station (OpenStreetMap via the
Overpass API) at the mileage cap, stepping backward (e.g. 900, 800 mi) if none
is nearby, so it stops *early* rather than overrunning the cap. Stations are
labelled **"suggested"** — OSM is community-maintained and may be incomplete or
stale, so a stop is never treated as a guaranteed-open station; if none is
found (or Overpass is rate-limited) it degrades to an unverified point on the
route. The lookup is isolated in `services._nearest_fuel_station`, so a paid /
truck-specific provider (Google Places, HERE, Trucker Path) can be swapped in
without touching the planning logic.

## Running locally

### Backend (Python 3.14, Django 6)

```bash
cd backend
py -3.14 -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env          # optional; add ORS_API_KEY for production routing
venv/Scripts/python.exe manage.py migrate
venv/Scripts/python.exe manage.py runserver 8000
```

Run the engine tests:

```bash
cd backend
venv/Scripts/python.exe -m unittest discover -s hos/tests -t .
```

### Frontend (Node 22, Vite)

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173 (proxies /api → :8000)
```
