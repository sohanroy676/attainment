from typing import Any

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.http import HttpRequest

from apps.audit import services as audit
from apps.tenancy.services import SESSION_KEY


@receiver(user_logged_in)
def on_login(sender: Any, request: HttpRequest, user: Any, **kwargs: Any) -> None:
    # Pin the session to the user's college; the tenant middleware reads it on every request.
    request.session[SESSION_KEY] = str(user.college_id)
    audit.record(
        "auth.login",
        "user",
        entity_id=user.pk,
        actor_id=user.pk,
        ip=audit.client_ip(request),
    )


@receiver(user_logged_out)
def on_logout(sender: Any, request: HttpRequest, user: Any, **kwargs: Any) -> None:
    if user is not None and getattr(user, "pk", None) is not None:
        audit.record(
            "auth.logout",
            "user",
            entity_id=user.pk,
            actor_id=user.pk,
            ip=audit.client_ip(request),
        )
