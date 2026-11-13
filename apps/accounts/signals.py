from typing import Any

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.http import HttpRequest

from apps.tenancy.middleware import SESSION_KEY


@receiver(user_logged_in)
def remember_college(sender: Any, request: HttpRequest, user: Any, **kwargs: Any) -> None:
    """Pin the session to the user's college; the tenant middleware reads it on every request."""
    request.session[SESSION_KEY] = str(user.college_id)
