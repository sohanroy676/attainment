from django.contrib import admin

from apps.audit.admin_base import AuditedModelAdmin

from . import models


class IdentifierInline(admin.TabularInline):  # type: ignore[type-arg]
    model = models.StudentIdentifier
    extra = 1


@admin.register(models.Student)
class StudentAdmin(AuditedModelAdmin):
    list_display = ("id", "status")  # names are shown on the detail page only
    inlines = [IdentifierInline]


@admin.register(models.Enrolment)
class EnrolmentAdmin(AuditedModelAdmin):
    list_display = ("student", "offering", "section", "status")


@admin.register(models.BatchMembership)
class BatchMembershipAdmin(AuditedModelAdmin):
    list_display = ("student", "batch", "valid_from", "valid_to")


@admin.register(models.SectionMembership)
class SectionMembershipAdmin(AuditedModelAdmin):
    list_display = ("student", "section", "valid_from", "valid_to")
