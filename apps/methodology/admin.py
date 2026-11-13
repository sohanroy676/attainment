from django.contrib import admin

from apps.audit.admin_base import AuditedModelAdmin

from . import models


@admin.register(models.Method)
class MethodAdmin(AuditedModelAdmin):
    list_display = ("name", "kind")


@admin.register(models.MethodAssignment)
class MethodAssignmentAdmin(AuditedModelAdmin):
    list_display = ("scope_type", "method", "valid_from", "valid_to", "locked")
