import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv
from unicorn_project.version import APP_VERSION

# --- Paths ----------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Load .env ------------------------------------------------
load_dotenv(BASE_DIR / ".env", override=True)

# --- Core -----------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-key-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"

_register_show_date = os.getenv("REGISTER_SHOW_DATE", "").strip().lower()
if _register_show_date in ("1", "true", "yes"):
    REGISTER_SHOW_DATE = True
elif _register_show_date in ("0", "false", "no"):
    REGISTER_SHOW_DATE = False
else:
    REGISTER_SHOW_DATE = DEBUG

def _env_host_list(*keys: str) -> list[str]:
    hosts: list[str] = []
    for key in keys:
        for h in os.getenv(key, "").split(","):
            h = h.strip()
            if h and h not in hosts:
                hosts.append(h)
    return hosts


RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = _env_host_list("ALLOWED_HOSTS", "DJANGO_ALLOWED_HOSTS")
    if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    for host in ("unicorn.adminforge.co.uk",):
        if host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)

# CSRF trusted origins (env list) + Render convenience
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
if RENDER_EXTERNAL_HOSTNAME:
    origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)
for host in ALLOWED_HOSTS:
    if host == "*":
        continue
    for origin in (f"https://{host}", f"http://{host}"):
        if origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Database -------------------------------------------------
def _is_postgres(url: str | None) -> bool:
    return bool(url) and url.startswith(("postgres://", "postgresql://"))

DB_URL = os.getenv("DATABASE_URL", "").strip()
if _is_postgres(DB_URL):
    DATABASES = {"default": dj_database_url.config(default=DB_URL, conn_max_age=600, ssl_require=True)}
else:
    sqlite_url = DB_URL or f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
    DATABASES = {"default": dj_database_url.parse(sqlite_url, conn_max_age=0)}

# ----- APIs ------------------------
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# --- Telegram bot (local polling on dev; worker service on Render) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "").lstrip("@")
SITE_URL = (os.getenv("SITE_URL", "") or "").rstrip("/")
if not SITE_URL and RENDER_EXTERNAL_HOSTNAME:
    SITE_URL = f"https://{RENDER_EXTERNAL_HOSTNAME}"
if not SITE_URL:
    SITE_URL = "http://127.0.0.1:8000"

# Shared cache for Telegram link tokens (web + telegram_poll must see the same store).
REDIS_URL = os.getenv("REDIS_URL", "").strip()
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
elif _is_postgres(DB_URL) and not DEBUG:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "pegasus_cache_table",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": BASE_DIR / ".django_cache",
        }
    }

# --- Apps / Middleware ---------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "import_export",
    "unicorn_project.training.apps.TrainingConfig",
    "anymail"
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "unicorn_project.training.middleware.MustChangePasswordMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "unicorn_project.training.middleware.AdminGateMiddleware",
]

ROOT_URLCONF = "unicorn_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "unicorn_project" / "training" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "unicorn_project.training.context_processors.globals",
                "unicorn_project.training.context_processors.role_context",
                "unicorn_project.training.context_processors.logo_context",
                'unicorn_project.training.context_processors.user_display_name',
                'unicorn_project.training.context_processors.two_factor_prompt',
            ],
        },
    },
]

WSGI_APPLICATION = "unicorn_project.wsgi.application"

# --- I18N -----------------------------------------------------
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
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/post-login/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Feature flags
BOOKING_AUTO_UPDATE_ON_PAGE = False
BOOKING_TEST_INTERVAL_MIN = 0

# --- Email (API-first) ---------------------------------------
# Use HTTPS APIs (Resend/MailerSend/SMTP2GO) via utils.emailing helper.
# No SMTP by default to avoid port/egress issues and surprises.
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "resend").lower()  # 'resend' | 'mailersend' | 'smtp2go'
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
MAILERSEND_API_KEY = os.getenv("MAILERSEND_API_KEY", "")
SMTP2GO_API_KEY = os.getenv("SMTP2GO_API_KEY", "")

# From must be a verified sender on your chosen provider (or onboarding@resend.dev for initial test)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Unicorn Admin System <onboarding@resend.dev>")

# Destinations
DEV_CATCH_ALL_EMAIL = os.getenv("DEV_CATCH_ALL_EMAIL", "unicornfss@gmail.com")
ADMIN_INBOX_EMAIL = os.getenv("ADMIN_INBOX_EMAIL", "info@unicornsafety.co.uk")

# Email backend selection
if os.getenv("EMAIL_PROVIDER", "").lower() == "resend":
    EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
elif DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"  # or dummy if you want

# Office phone
OFFICE_PHONE = os.getenv("OFFICE_PHONE", "")


# --- HTML invoice rendering & wkhtmltopdf --------------------
WKHTMLTOPDF_CMD = os.getenv("WKHTMLTOPDF_CMD", "")
if not WKHTMLTOPDF_CMD and os.name == "nt":
    for c in [r"C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe", r"C:\\Program Files (x86)\\wkhtmltopdf\\bin\\wkhtmltopdf.exe"]:
        if Path(c).exists():
            WKHTMLTOPDF_CMD = c
            break

# --- Google Drive / OAuth ------------------------------------
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_TOKEN = os.getenv("GOOGLE_OAUTH_TOKEN", "")
GOOGLE_DRIVE_ROOT_RECEIPTS = os.getenv("GOOGLE_DRIVE_ROOT_RECEIPTS", "")


# --- Diagnostics ---------------------------------------------
SETTINGS_EMAIL_SUMMARY = {
    "provider": EMAIL_PROVIDER,
    "backend": EMAIL_BACKEND,
    "default_from": DEFAULT_FROM_EMAIL,
    "admin_inbox": ADMIN_INBOX_EMAIL,
    "dev_catch_all": DEV_CATCH_ALL_EMAIL,
}

ANYMAIL = {
    "RESEND_API_KEY": os.getenv("RESEND_API_KEY"),
    "SEND_DEFAULTS": {"from_email": DEFAULT_FROM_EMAIL},
}

AUTHENTICATION_BACKENDS = [
    "unicorn_project.training.auth_backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

