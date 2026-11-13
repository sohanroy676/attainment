"""Local development: plain http, debug on."""

from .base import *  # noqa: F403
from .base import env

DEBUG = True
SECRET_KEY = env("DJANGO_SECRET_KEY") or "dev-only-not-a-secret"  # noqa: S105
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
