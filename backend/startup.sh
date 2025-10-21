rm -f /home/site/wwwroot/typing_extensions.py
rm -rf /home/site/wwwroot/typing_extensions
rm -rf /home/site/wwwroot/__pycache__
#!/bin/bash
rm -f /home/site/wwwroot/typing_extensions.py
rm -rf /home/site/wwwroot/typing_extensions
rm -rf /home/site/wwwroot/__pycache__
set -euo pipefail

APP_DIR="/home/site/wwwroot"
cd "$APP_DIR"

# ==== Azure App Service env fixes ====
# Desactivar completamente el agente de OpenTelemetry que inyecta /agents/python
export AZURE_EXTENSION_NO_OPENTELEMETRY=1
export OTEL_SDK_DISABLED=true

# Detectar python3 del sistema (en Azure suele estar en /opt/python/3.x/bin/python3)
PYBIN="$(command -v python3)"
if [ -z "$PYBIN" ]; then
  echo "No se encontró python3 en el contenedor" >&2
  exit 1
fi

# ==== venv ====
if [ ! -d "$APP_DIR/antenv" ]; then
  "$PYBIN" -m venv "$APP_DIR/antenv"
fi
# shellcheck disable=SC1091
source "$APP_DIR/antenv/bin/activate"

# Asegurar pip actualizado e instalar dependencias
python -m pip install --upgrade pip
pip install -r "$APP_DIR/requirements.txt"

# Poner site-packages del venv **primero** en PYTHONPATH para ganar a /agents/python
VENV_SITE="$(python -c 'import sys,site; print(site.getsitepackages()[0])')"
export PYTHONPATH="$VENV_SITE:$PYTHONPATH"

# Variables mínimas
export DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:=backend.settings}
export PORT=${PORT:=8000}

# Migraciones y estáticos (no fallar si no corresponde)
python manage.py migrate --noinput || true
python manage.py collectstatic --noinput || true

# Lanzar gunicorn
exec gunicorn backend.wsgi:application \
  --bind 0.0.0.0:$PORT \
  --workers 2 \
  --timeout 120
