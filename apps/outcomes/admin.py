from django.contrib import admin

from apps.audit.admin_base import AuditedModelAdmin

from . import models


@admin.register(models.ProgrammeOutcome)
class ProgrammeOutcomeAdmin(AuditedModelAdmin):
    list_display = ("programme", "code", "kind", "version")


class CourseOutcomeInline(admin.TabularInline):  # type: ignore[type-arg]
    model = models.CourseOutcome
    extra = 1


@admin.register(models.CourseDefinitionVersion)
class CourseDefinitionAdmin(AuditedModelAdmin):
    list_display = ("course", "version", "valid_from", "valid_to")
    inlines = [CourseOutcomeInline]


@admin.register(models.Target)
class TargetAdmin(AuditedModelAdmin):
    list_display = ("offering", "outcome", "batch", "value", "source")
