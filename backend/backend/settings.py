# backend/settings.py
from pathlib import Path
import os
import sys
from dotenv import load_dotenv
import dj_database_url
import logging 
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

# --- Mitigar conflictos por agentes de Azure (OpenTelemetry) ---
# Evita que /agents/python/typing_extensions.py sombree el del venv
sys.path = [p for p in sys.path if "/agents/python" not in p]
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")  # opcional en local

# Helper para leer listas desde variables de entorno (coma-separadas)
def csv_env(name, default=""):
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]

# --- Core ---
SECRET_KEY = os.getenv("SECRET_KEY", "!!!_dev_only_change_me_!!!")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = csv_env(
    "ALLOWED_HOSTS",
    # Azure + dev por defecto
    ".azurewebsites.net,.scm.azurewebsites.net,localhost,127.0.0.1"
)

# --- CORS / CSRF ---
# Autoriza tu frontend en Vercel (dominio fijo) + dev
CORS_ALLOWED_ORIGINS = csv_env(
    "CORS_ALLOWED_ORIGINS",
    "https://quiz-gen-ai-three.vercel.app,http://localhost:3000,http://127.0.0.1:3000"
)
# Acepta cualquier subdominio *.vercel.app adicional si lo necesitas
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.vercel\.app$"
]

CSRF_TRUSTED_ORIGINS = csv_env(
    "CSRF_TRUSTED_ORIGINS",
    "https://*.azurewebsites.net,https://*.vercel.app,http://localhost:3000,http://127.0.0.1:3000"
)

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = ["*"]

INSTALLED_APPS = [
    "corsheaders",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "api",
]

MIDDLEWARE = [
    # CORS debe ir muy arriba
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

SENTRY_DSN = os.getenv("SENTRY_DSN", "")

if SENTRY_DSN:
    sentry_logging = LoggingIntegration(
        level=logging.INFO,      # Nivel que se captura en breadcrumbs
        event_level=logging.ERROR,  # Nivel que se envía como evento a Sentry
    )

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            sentry_logging,
        ],
        # 0.0 = sin traces, subes a 0.1 / 0.2 si quieres perf más adelante
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        send_default_pii=False,  # True si quieres asociar usuarios autenticados
        environment=os.getenv("SENTRY_ENV", "local"),
        release=os.getenv("SENTRY_RELEASE", "quizgenai@dev"),
    )



WSGI_APPLICATION = "backend.wsgi.application"
ASGI_APPLICATION = "backend.asgi.application"

# --- Base de datos ---
# Evita pasar sslmode a SQLite (causa TypeError en sqlite3.connect)
_db_url = os.getenv("DATABASE_URL")
if _db_url:
    _is_postgres = _db_url.startswith("postgres://") or _db_url.startswith("postgresql://")
    DATABASES = {
        "default": dj_database_url.parse(
            _db_url,
            conn_max_age=600,
            ssl_require=_is_postgres,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --- Password validators ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- i18n / zona horaria ---
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Archivos estáticos (Whitenoise) ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Seguridad detrás de proxy de Azure ---
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Media (uploads) ---
# Directorio donde guardamos archivos generados/medias (ej: generated/)
MEDIA_URL = os.getenv("MEDIA_URL", "/media/")
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))

if not DEBUG:
    # Endurecer en producción
    #SECURE_SSL_REDIRECT = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    USE_X_FORWARDED_HOST = True
    # HSTS (opcional, actívalo cuando todo sirva por HTTPS estable)
    # SECURE_HSTS_SECONDS = 31536000
    # SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # SECURE_HSTS_PRELOAD = True
