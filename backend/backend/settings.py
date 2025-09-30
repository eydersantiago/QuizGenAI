from pathlib import Path
import os
from dotenv import load_dotenv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# --- Util ---
def csv_env(name, default=""):
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]

# --- Seguridad/Entorno ---
SECRET_KEY = os.getenv("SECRET_KEY", "!!!_dev_only_change_me_!!!")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# ✅ HOSTS del backend (sin esquema)
ALLOWED_HOSTS = csv_env(
    "ALLOWED_HOSTS",
    "localhost,127.0.0.1,.onrender.com"
)

# ✅ Orígenes FRONTEND permitidos (con esquema)
# - Local CRA
# - Tu dominio de Vercel
# - (Opcional) el propio backend por si pruebas directas con curl desde el mismo host
CORS_ALLOWED_ORIGINS = csv_env(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,https://quiz-gen-ai-three.vercel.app,https://quizgenai-9xdk.onrender.com"
)

# ✅ Regex para permitir TODOS los previews de Vercel (*.vercel.app)
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.vercel\.app$",
]

# ✅ CSRF confía en los orígenes que te harán POST (con esquema)
CSRF_TRUSTED_ORIGINS = csv_env(
    "CSRF_TRUSTED_ORIGINS",
    "https://quizgenai-9xdk.onrender.com,https://quiz-gen-ai-three.vercel.app,http://localhost:3000,http://127.0.0.1:3000"
)

# Si usas cookies/sesión entre dominios
CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = ["*"]

# --- Apps ---
INSTALLED_APPS = [
    "corsheaders",  # arriba ayuda a que el middleware corra primero
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "api",
]

# --- Middleware (orden importante) ---
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",   # MUY ARRIBA
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

WSGI_APPLICATION = "backend.wsgi.application"

# --- Base de datos ---
DATABASES = {
    "default": dj_database_url.parse(
        os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=600,
        ssl_require=bool(os.getenv("DATABASE_URL", "")),
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
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- HTTPS/Proxy (Render) ---
# Asegura que Django detecte HTTPS detrás del proxy y ponga cookies seguras en prod
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

# --- Desarrollo: modo laxo si DEBUG ---
if DEBUG:
    # Permite todo CORS en dev si no configuraste CORS_ALLOWED_ORIGINS
    if not CORS_ALLOWED_ORIGINS:
        CORS_ALLOW_ALL_ORIGINS = True
