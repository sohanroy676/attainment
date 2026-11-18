from django.contrib import admin

from apps.audit.admin_base import AuditedModelAdmin

from . import models


class ChoiceGroupInline(admin.TabularInline):  # type: ignore[type-arg]
    model = models.ChoiceGroup
    extra = 0


class QuestionInline(admin.TabularInline):  # type: ignore[type-arg]
    model = models.Question
    extra = 0


@admin.register(models.Assessment)
class AssessmentAdmin(AuditedModelAdmin):
    list_display = ("name", "tool", "offering", "behaviour", "max_total", "status")
    inlines = [ChoiceGroupInline, QuestionInline]


class PartInline(admin.TabularInline):  # type: ignore[type-arg]
    model = models.QuestionPart
    extra = 1
    fields = ("label", "code", "max", "co", "order")


@admin.register(models.Question)
class QuestionAdmin(AuditedModelAdmin):
    list_display = ("assessment", "number", "choice_group")
    inlines = [PartInline]

    def save_formset(self, request, form, formset, change):  # type: ignore[no-untyped-def]
        for part in formset.save(commit=False):
            part.assessment = part.question.assessment
            part.save()
        formset.save_m2m()
