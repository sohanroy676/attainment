"""Settings shared by every environment. Secrets come from the environment (.env)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = [
    h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost").split(",") if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "csp",
    "apps.tenancy",
    "apps.accounts",
    "apps.academics",
    "apps.roster",
    "apps.outcomes",
    "apps.assessments",
    "apps.marks",
    "apps.methodology",
    "apps.results",
    "apps.workflow",
    "apps.quality",
    "apps.reports",
    "apps.imports",
    "apps.audit",
    "apps.integration",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Opens the request transaction and sets the current college (SET LOCAL). It must run
    # before AuthenticationMiddleware, because loading the user is already a tenant query.
    "apps.tenancy.middleware.TenantMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

# Two database roles on one database (design 13.1):
#   default = the app role: not the table owner, no BYPASSRLS. Serves every request.
#   owner   = runs migrations only: `manage.py migrate --database owner`.
_DB_COMMON = {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": env("POSTGRES_DB", "attainment"),
    "HOST": env("DB_HOST", "127.0.0.1"),
    "PORT": env("DB_PORT", "5432"),
}
DB_APP_USER = env("DB_APP_USER", "attainment_app")
DB_OWNER_USER = env("DB_OWNER_USER", "attainment_owner")
DATABASES = {
    "default": {
        **_DB_COMMON,
        "USER": DB_APP_USER,
        "PASSWORD": env("DB_APP_PASSWORD"),
        "ATOMIC_REQUESTS": True,
    },
    "owner": {
        **_DB_COMMON,
        "USER": DB_OWNER_USER,
        "PASSWORD": env("DB_OWNER_PASSWORD"),
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "apps.accounts.backends.TenantAuthBackend",
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "accounts:login"
PASSWORD_RESET_TIMEOUT = 3600  # seconds

# Lockout after repeated failures (django-axes).
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25  # hours
# Per username only. Behind the Caddy proxy every client shares one address until forwarded
# headers are configured, so locking by IP would let one attacker lock out a whole college.
AXES_LOCKOUT_PARAMETERS = ["username"]
# W021 (HSTS preload) is a per-deployment decision: preload is hard to undo.
SILENCED_SYSTEM_CHECKS = ["axes.W006", "security.W021"]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "accounts/locked.html"

# Sessions: 30 minutes idle (the expiry slides on every request).
SESSION_COOKIE_AGE = 30 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

# Transport and header security. Dev and the local-http compose setup relax the https parts.
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^healthz/?$"]

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": ["'self'"],
        "style-src": ["'self'"],
        "img-src": ["'self'", "data:"],
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'none'"],
    }
}

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

EMAIL_HOST = env("EMAIL_HOST")
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_HOST
    else "django.core.mail.backends.console.EmailBackend"
)
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = bool(EMAIL_HOST)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "attainment@localhost")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
