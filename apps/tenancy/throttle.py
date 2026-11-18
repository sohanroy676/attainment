"""A small per-user rate limit for the heavy endpoints (PDF rendering, uploads, exports).

The counter lives in Django's cache, so with several worker processes each keeps its own count:
the limit is a brake on abuse, not an exact quota. Limits are in `settings.RATE_LIMITS` as
name -> (requests, seconds).
"""

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse

DEFAULT_LIMITS = {"pdf": (20, 60), "upload": (30, 60), "export": (5, 3600)}


def throttled(request: HttpRequest, name: str) -> HttpResponse | None:
    """None when the request may go ahead, else a 429 response."""
    limits = getattr(settings, "RATE_LIMITS", DEFAULT_LIMITS)
    limit, seconds = limits.get(name, DEFAULT_LIMITS[name])
    key = f"throttle:{name}:{request.user.pk}"
    cache.add(key, 0, timeout=seconds)
    try:
        used = cache.incr(key)
    except ValueError:  # the entry expired between the two calls
        cache.set(key, 1, timeout=seconds)
        used = 1
    if used <= limit:
        return None
    response = HttpResponse(
        "Too many requests. Please wait a little and try again.",
        status=429,
        content_type="text/plain",
    )
    response["Retry-After"] = str(seconds)
    return response
