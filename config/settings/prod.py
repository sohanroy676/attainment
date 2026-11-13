"""Production and the docker compose setup. Fails to start without a secret key."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import ALLOWED_HOSTS, SECRET_KEY, env_bool

if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set")

# Behind Caddy, which terminates TLS and forwards the scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Local http only (no TLS yet): never set this on a real server.
if env_bool("ALLOW_INSECURE_HTTP"):
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0
