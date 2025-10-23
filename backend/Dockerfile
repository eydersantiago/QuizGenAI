# Dockerfile (producción) - con ffmpeg y libsndfile para STT
FROM python:3.12-slim

# --- Ajustes base ---
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Para que pydub encuentre ffmpeg (por si no lo detecta automáticamente)
    FFMPEG_PATH=/usr/bin/ffmpeg \
    # Activa la ruta de conversión en el backend (tu flag)
    USE_FFMPEG=1

WORKDIR /app

# --- Paquetes del sistema ---
# - build-essential y libpq-dev: ya los usabas (psycopg2, etc.)
# - ffmpeg: requerido para convertir/leer ogg/mp3/webm, etc.
# - libsndfile1: requerido para soundfile (PySoundFile)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    ffmpeg \
    libsndfile1 \
 && rm -rf /var/lib/apt/lists/*

# --- Python deps ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Código ---
COPY . .

# (Opcional) si usas whitenoise y STATIC_ROOT configurado:
# Necesita DJANGO_SETTINGS_MODULE ya definido en el entorno del runtime o aquí.
# Puedes definirlo en tu servicio/orquestador en lugar de bakearlo en la imagen.
# ENV DJANGO_SETTINGS_MODULE=backend.settings
RUN python manage.py collectstatic --noinput || true

# (Opcional) Puerto expuesto
EXPOSE 8000

# (Opcional) Healthcheck simple (requiere curl; si no lo quieres, bórralo)
# RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
# HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
#   CMD curl -fsS http://localhost:8000/api/health/ || exit 1

# --- Run ---
CMD ["gunicorn", "backend.wsgi:application", "--bind", "0.0.0.0:8000"]
