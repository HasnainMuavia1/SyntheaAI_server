#!/usr/bin/env bash
set -e

# Apply database migrations on startup (sqlite db is bind/volume-mounted).
echo "[entrypoint] Applying database migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Starting: $*"
exec "$@"
