#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
APP_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$APP_ROOT/backend"

python manage.py migrate --noinput
python manage.py load_sample_data
python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
