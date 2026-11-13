"""A ModelAdmin that writes to the audit log instead of Django's own admin log.

Django's LogEntry keeps a text copy of each object (names included) and is not hash-chained, so
the setup screens skip it and log through apps.audit instead: who, what, before and after.
"""

from typing import Any

from django.contrib import admin
from django.db.models import Model, QuerySet
from django.http import HttpRequest

from . import services as audit


class AuditedModelAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    def save_model(self, request: HttpRequest, obj: Model, form: Any, change: bool) -> None:
        before = None
        if change:
            old = type(obj)._default_manager.filter(pk=obj.pk).first()
            before = audit.snapshot(old) if old is not None else None
        super().save_model(request, obj, form, change)
        audit.record_model(
            "updated" if change else "created",
            obj,
            actor_id=request.user.pk,
            before=before,
            after=audit.snapshot(obj),
            ip=audit.client_ip(request),
        )

    def delete_model(self, request: HttpRequest, obj: Model) -> None:
        before = audit.snapshot(obj)
        super().delete_model(request, obj)
        audit.record_model(
            "deleted", obj, actor_id=request.user.pk, before=before, ip=audit.client_ip(request)
        )

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> None:
        for obj in list(queryset):
            self.delete_model(request, obj)

    # Django's own admin log is not used.
    def log_addition(self, request: HttpRequest, obj: Model, message: Any) -> None:  # type: ignore[override]
        return None

    def log_change(self, request: HttpRequest, obj: Model, message: Any) -> None:  # type: ignore[override]
        return None

    def log_deletions(self, request: HttpRequest, queryset: QuerySet[Any]) -> None:  # type: ignore[override]
        return None
