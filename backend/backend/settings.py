from pathlib import Path
import os
from dotenv import load_dotenv
import dj_database_url  # <- asegúrate de tenerlo en requirements

BASE_DIR = Path(__file__).resolve().parent.parent

# Carga .env local (no afecta a Railway; allí usarás Variables del Proyecto)
load_dotenv(dotenv_path=BASE_DIR / ".env")

# --- Utilidades ---
def csv_env(name, default=""):
    """
    Lee una env var separada por comas y devuelve lista sin espacios.
    Ej: "a.com, b.com" -> ["a.com","b.com"]
    """
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]

# --- Seguridad/Entorno ---
SECRET_KEY = os.getenv("SECRET_KEY", "!!!_dev_only_change_me_!!!")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# En producción: configura ALLOWED_HOSTS desde env, ej.:
# ALLOWED_HOSTS=tu-api.up.railway.app,api.tudominio.com
ALLOWED_HOSTS = csv_env("ALLOWED_HOSTS", "localhost,127.0.0.1")

# CSRF_TRUSTED_ORIGINS debe incluir los ORÍGENES (con esquema) que te van a hacer POST, ej.:
# CSRF_TRUSTED_ORIGINS=https://tu-api.up.railway.app,https://tuapp.vercel.app
CSRF_TRUSTED_ORIGINS = csv_env("CSRF_TRUSTED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")

# CORS: permite solo tu frontend en prod. Puedes inyectar la lista por env
# CORS_ALLOWED_ORIGINS=https://tuapp.vercel.app,https://tu-dominio.com
CORS_ALLOWED_ORIGINS = csv_env("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

# Si necesitas credenciales (cookies) entre dominios:
CORS_ALLOW_CREDENTIALS = True

# Métodos/headers (lo que ya tenías, compacto)
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = ["*"]

# --- Apps ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # externas
    "rest_framework",
    "corsheaders",

    # tu app
    "api",
]

# --- Middleware (orden importante) ---
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # <- sirve estáticos
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

WSGI_APPLICATION = "backend.wsgi.application"

# --- Base de datos ---
# En local (sin DATABASE_URL): usa SQLite
# En Railway: define DATABASE_URL (Postgres) y se usará automáticamente
DATABASES = {
    "default": dj_database_url.parse(
        os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=600,
        ssl_require=bool(os.getenv("DATABASE_URL", ""))  # exige SSL si hay Postgres
    )
}

# --- Password validators ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- i18n ---
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static (Whitenoise) ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Desarrollo: relajamos CORS/CSRF si DEBUG ---
if DEBUG:
    # Permite todo CORS en dev (útil si haces pruebas locales)
    CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS or []
    CORS_ALLOW_ALL_ORIGINS = True
