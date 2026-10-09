#!/usr/bin/env bash
# Render start script: migrate, seed if empty, then run gunicorn.
set -e

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Seeding demo data (skips if already present)..."
python manage.py seed_demo || echo "Seed skipped or failed — continuing."

echo "==> Starting gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:"${PORT:-8000}" --workers 2 --timeout 120
