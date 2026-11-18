from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from apps.audit.admin_base import AuditedModelAdmin

from . import models
from .services import assign_faculty, check_section


@admin.register(models.University)
class UniversityAdmin(AuditedModelAdmin):
    list_display = ("name", "short_name")


@admin.register(models.Department)
class DepartmentAdmin(AuditedModelAdmin):
    list_display = ("code", "name")


@admin.register(models.Programme)
class ProgrammeAdmin(AuditedModelAdmin):
    list_display = ("name", "department", "level")


@admin.register(models.Batch)
class BatchAdmin(AuditedModelAdmin):
    list_display = ("name", "programme", "start_year", "end_year")


@admin.register(models.AcademicYear)
class AcademicYearAdmin(AuditedModelAdmin):
    list_display = ("label", "start_date", "end_date")


@admin.register(models.Term)
class TermAdmin(AuditedModelAdmin):
    list_display = ("academic_year", "number", "name")


class CourseCodeInline(admin.TabularInline):  # type: ignore[type-arg]
    model = models.CourseCode
    extra = 1


@admin.register(models.Course)
class CourseAdmin(AuditedModelAdmin):
    list_display = ("title", "category", "kind", "credits")
    inlines = [CourseCodeInline]


class CourseGroupMemberInline(admin.TabularInline):  # type: ignore[type-arg]
    model = models.CourseGroupMember
    extra = 1


@admin.register(models.CourseGroup)
class CourseGroupAdmin(AuditedModelAdmin):
    list_display = ("name", "kind")
    inlines = [CourseGroupMemberInline]


class SectionInline(admin.TabularInline):  # type: ignore[type-arg]
    model = models.Section
    extra = 1


@admin.register(models.CourseOffering)
class CourseOfferingAdmin(AuditedModelAdmin):
    list_display = ("course", "term", "coordinator")
    inlines = [SectionInline]


@admin.register(models.Section)
class SectionAdmin(AuditedModelAdmin):
    list_display = ("offering", "name", "programme", "batch")

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        check_section(obj)
        super().save_model(request, obj, form, change)


@admin.register(models.FacultyAssignment)
class FacultyAssignmentAdmin(AuditedModelAdmin):
    list_display = ("user", "offering", "section")

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        # goes through the service so the lecturer role and the log entries are created too
        assign_faculty(obj.user, obj.offering, obj.section, actor=request.user)
