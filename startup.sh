#!/bin/bash
set -e

APP_DIR="/home/site/wwwroot"
cd "$APP_DIR"

# (opcional) limpiar venv viejo si quedó mal
if [ -d "$APP_DIR/antenv" ] && [ ! -f "$APP_DIR/antenv/bin/activate" ]; then
  rm -rf "$APP_DIR/antenv"
fi

# crear/usar venv
if [ ! -d "$APP_DIR/antenv" ]; then
  /usr/bin/python3 -m venv "$APP_DIR/antenv"
fi
source "$APP_DIR/antenv/bin/activate"

# pip al día e instalar dependencias
python -m pip install --upgrade pip
pip install -r "$APP_DIR/requirements.txt"

# variables mínimas por si no están en App Settings
export DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:=backend.settings}
export PORT=${PORT:=8000}

# migraciones y estáticos (no falla si no hay)
python manage.py migrate --noinput || true
python manage.py collectstatic --noinput || true

# arrancar gunicorn
exec gunicorn backend.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
