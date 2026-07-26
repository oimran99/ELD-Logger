---
title: ELD Logger API
emoji: 🚚
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
pinned: false
---

# ELD Logger — Django API

FMCSA Hours-of-Service trip-planner backend (Django + DRF), deployed as a Docker
Space. This directory is the deployable backend; the full project (React
frontend + backend) lives at <https://github.com/oimran99/ERD-Logger>.

- Health check: `GET /api/health/`
- Plan a trip: `POST /api/plan-trip/`
- Daily-log PDF: `GET|POST /api/trips/<id>/pdf/`

The container listens on port 8000 (`app_port` above). Configure via the Space's
**Settings → Variables and secrets**: `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS=.hf.space`, `DATABASE_URL` (Neon Postgres), and
`CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` (your frontend URL).
