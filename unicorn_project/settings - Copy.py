import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv

# --- Paths ----------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent


# --- Load .env early (and overwrite OS env if needed) ------------------------
try:
    import environ, os as _os
    _env = environ.Env()
    # Ensure the project .env is loaded and can override stale OS env vars
    environ.Env.read_env(str(BASE_DIR / ".env"), overwrite=True)
except Exception as _e:
    # Fallback: try python-dotenv if available
    try:
        from dotenv import load_dotenv as _load_dotenv
        _load_dotenv(BASE_DIR / ".env", override=True)
    except Exception:
        pass



# --- Env (.env) ----------------------------------------------
# Local dev: values from .env ; Render/Prod: env vars from dashboard
load_dotenv(BASE_DIR / ".env", override=True)

# --- Third-party / feature flags ------------------------------
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# --- Core -----------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-key-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"

# Allow everything in dev; use env in prod
if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = [
        h.strip()
        for h in os.getenv("ALLOWED_HOSTS", "").split(",")
        if h.strip()
    ]

# CSRF trusted origins (env list) + Render convenience
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Database: Postgres via DATABASE_URL; fallback to SQLite ---
def _is_postgres(url: str | None) -> bool:
    return bool(url) and url.startswith(("postgres://", "postgresql://"))

DB_URL = os.getenv("DATABASE_URL", "").strip()

if _is_postgres(DB_URL):
    # Production (Render): PostgreSQL with SSL
    DATABASES = {
        "default": dj_database_url.config(
            default=DB_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    # Development: SQLite (no sslmode arguments)
    sqlite_url = DB_URL or f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
    DATABASES = {
        "default": dj_database_url.parse(sqlite_url, conn_max_age=0)
    }

# --- Installed apps ------------------------------------------
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
]

# --- Middleware (WhiteNoise just after Security) --------------
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

# --- Templates ------------------------------------------------
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
            ],
        },
    },
]

WSGI_APPLICATION = "unicorn_project.wsgi.application"

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
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/post-login/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Feature flags
BOOKING_AUTO_UPDATE_ON_PAGE = False
BOOKING_TEST_INTERVAL_MIN = 0

# --- Email destinations --------------------------------------
# Always present and overridable by env on both dev/prod
DEV_CATCH_ALL_EMAIL = os.getenv("DEV_CATCH_ALL_EMAIL", "unicornfss@gmail.com")
ADMIN_INBOX_EMAIL = os.getenv("ADMIN_INBOX_EMAIL", "unicornfss@gmail.com")

# --- HTML invoice rendering & wkhtmltopdf --------------------
WKHTMLTOPDF_CMD = os.getenv("WKHTMLTOPDF_CMD", "")
if not WKHTMLTOPDF_CMD and os.name == "nt":
    from pathlib import Path as _P
    for c in [
        r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
    ]:
        if _P(c).exists():
            WKHTMLTOPDF_CMD = c
            break

# --- Email transport -----------------------------------------
# EMAIL_MODE controls behaviour. Options:
#   - "console": log emails to console (good for dev)
#   - "dummy":   drop all emails (no-op)
#   - "gmail":   send via Gmail SMTP (App Password / OAuth)
#   - "mailersend": send via MailerSend SMTP
#   - "smtp":    generic SMTP using EMAIL_HOST/PORT/USER/PASS
#   - "auto":    (default) -> console in DEBUG, else generic SMTP
EMAIL_MODE = os.getenv("EMAIL_MODE", "auto").lower()

if EMAIL_MODE in {"console", "dev"} or (EMAIL_MODE == "auto" and DEBUG):
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@unicornsafety.co.uk")

elif EMAIL_MODE == "dummy":
    EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
    DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@unicornsafety.co.uk")



elif EMAIL_MODE == "gmail":
    # Gmail SMTP (use App Password if 2FA enabled). Safer than "less secure apps".
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))  # STARTTLS
    EMAIL_USE_TLS = True
    EMAIL_USE_SSL = False
    EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "30"))
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")           # your Gmail address
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")   # 16-char App Password
    DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "no-reply@unicornsafety.co.uk")
    SERVER_EMAIL = DEFAULT_FROM_EMAIL


elif EMAIL_MODE == "mailersend":
    # MailerSend SMTP: https://www.mailersend.com/help/smtp
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp.mailersend.net"
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))  # TLS port
    EMAIL_USE_TLS = True
    EMAIL_USE_SSL = False
    EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "30"))
    # Username must literally be "apikey"; password is the API key
    EMAIL_HOST_USER = os.getenv("MAILERSEND_USERNAME", "apikey")
    EMAIL_HOST_PASSWORD = os.getenv("MAILERSEND_API_KEY", "")
    DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@unicornsafety.co.uk")

else:
    # Generic SMTP (e.g. Gmail/Outlook) driven by env
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))        # 587 for STARTTLS
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") == "1"  # "1" or "0"
    EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "0") == "1"  # rarely needed
    EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "30"))
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
    DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "no-reply@unicornsafety.co.uk")

# Handy to render on the diagnostics page if you add one
SETTINGS_EMAIL_SUMMARY = {
    "backend": locals().get("EMAIL_BACKEND"),
    "mode": EMAIL_MODE,
    "host": locals().get("EMAIL_HOST", "(console/dummy)"),
    "port": locals().get("EMAIL_PORT", "(n/a)"),
    "user": locals().get("EMAIL_HOST_USER", ""),
    "default_from": DEFAULT_FROM_EMAIL,
    "admin_inbox": ADMIN_INBOX_EMAIL,
    "dev_catch_all": DEV_CATCH_ALL_EMAIL,
}
