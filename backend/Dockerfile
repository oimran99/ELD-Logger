# Portable container for the Django API — runs on Back4App Containers, Hugging
# Face Spaces, Fly.io, or any Docker host. psycopg[binary] bundles libpq, so no
# apt packages are needed, keeping the image slim.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Build static assets at image-build time (no DB needed).
RUN python manage.py collectstatic --no-input

EXPOSE 8000

# Apply migrations, then serve. One worker + threads keeps memory low for small
# (256 MB) free instances while still handling the I/O-bound external
# geocoding/routing/Overpass calls concurrently. --timeout 120 covers slow calls.
CMD sh -c "python manage.py migrate --no-input && \
    gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} \
    --workers 1 --threads 4 --timeout 120"
