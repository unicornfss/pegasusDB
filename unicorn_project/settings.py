import os
from pathlib import Path

# --- Paths ----------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Env (.env) ----------------------------------------------
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env", override=True)

# --- Third-party / feature flags ------------------------------
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# --- Core -----------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-key-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"

# Allow everything in dev; use env in prod (Render etc.)
if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h.strip()]

# --- Installed apps ------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "unicorn_project.training",
]

# --- Middleware (WhiteNoise just after Security) --------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    'unicorn_project.training.middleware.MustChangePasswordMiddleware',
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "unicorn_project.urls"

# --- Templates ------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "unicorn_project" / "training" / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                 "unicorn_project.training.context_processors.globals",
                "unicorn_project.training.context_processors.role_context",
            ],
        },
    },
]

WSGI_APPLICATION = "unicorn_project.wsgi.application"

# --- Database (SQLite local; DATABASE_URL in prod) ------------
import dj_database_url

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

# --- Internationalization ------------------------------------
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

# --- Static / Media ------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "unicorn_project" / "training" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Auth redirects -------------------------------------------
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Render/Proxy headers (safe to leave on)
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS = [f"https://{RENDER_EXTERNAL_HOSTNAME}"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
