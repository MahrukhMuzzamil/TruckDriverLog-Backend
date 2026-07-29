# TruckDriverLog — Backend

Django + DRF API that plans FMCSA-compliant truck trips and generates ELD daily-log data. Part of the [RouteLedger](https://github.com/MahrukhMuzzamil/TruckDriverLog) project (see the root repo for full docs, Docker Compose and deployment).

## Stack

- **Django 5 + Django REST Framework** — API
- **PostgreSQL** — trip storage (results as JSON documents)
- **Redis** — cache for geocoding (30d) & routing (7d) → sub-second responses
- **Celery + Redis broker** — async planning mode and nightly cleanup (beat)
- **OSRM** (routing) & **Nominatim** (geocoding) — free, no API keys

## Layout

```
config/            settings, urls, celery app
trips/
  models.py        Trip (inputs + JSON result)
  views.py         TripViewSet, geocode suggest, health
  serializers.py   input validation / output shapes
  tasks.py         plan_trip_task (async mode), cleanup_old_trips (beat)
  services/
    hos.py         ⭐ HOS simulation engine (pure, unit-tested)
    logs.py        timeline → per-day ELD log sheets
    planner.py     orchestrator: geocode → route → simulate → payload
    routing.py     OSRM client + Redis cache + point-at-mile interpolation
    geocoding.py   Nominatim client + Redis cache
  tests/           engine + log-splitting tests
```

## Run (dev, without Docker)

```bash
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt

# needs local Postgres + Redis, or export DATABASE_URL / REDIS_URL
python manage.py migrate
python manage.py runserver          # http://localhost:8000

celery -A config worker -l info     # optional: async mode
celery -A config beat -l info       # optional: scheduled cleanup
```

## Test

```bash
python manage.py test trips
```

## Key endpoints

- `POST /api/trips/` — plan a trip (sync, fast path)
- `POST /api/trips/?mode=async` — plan via Celery, poll `GET /api/trips/{id}/`
- `GET /api/geocode/suggest/?q=…` — autocomplete
- `GET /api/health/` — liveness + cache check

Environment variables: see `.env.example`.
