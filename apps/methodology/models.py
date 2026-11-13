"""Methods as versioned data (design 6.4, 7). The rules are JSON from the engine's schema.

An active version is immutable: the database refuses to change its configuration, hash or
number (a trigger in migration 0001), so a published method can never be edited in place.
"""

from django.conf import settings
from django.db import models

from apps.tenancy.models import TenantRecord


class Method(TenantRecord):
    class Kind(models.TextChoices):
        THEORY = "theory", "Theory"
        LAB = "lab", "Lab"
        OTHER = "other", "Other"

    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.THEORY)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["college", "name"], name="method_name_unique")
        ]

    def __str__(self) -> str:
        return self.name


class MethodVersion(TenantRecord):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired"

    method = models.ForeignKey(Method, on_delete=models.PROTECT, related_name="versions")
    number = models.PositiveSmallIntegerField()
    config_text = models.TextField()  # the exact JSON, validated by engine.schema
    content_hash = models.CharField(max_length=64, blank=True)  # set when activated
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["method", "number"], name="method_version_unique")
        ]
        ordering = ["method", "number"]

    def __str__(self) -> str:
        return f"{self.method} v{self.number}"


class MethodAssignment(TenantRecord):
    """Which method applies at which level. The most specific level wins unless a wider level is
    locked (design section 7.1)."""

    class Scope(models.TextChoices):
        UNIVERSITY = "university", "University"
        COLLEGE = "college", "College"
        PROGRAMME = "programme", "Programme"
        COURSE = "course", "Course"

    scope_type = models.CharField(max_length=12, choices=Scope.choices)
    scope_id = models.UUIDField(null=True, blank=True)  # empty for the college itself
    method = models.ForeignKey(Method, on_delete=models.PROTECT, related_name="assignments")
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    locked = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(scope_type="college", scope_id__isnull=True)
                | (~models.Q(scope_type="college") & models.Q(scope_id__isnull=False)),
                name="method_assignment_scope_id",
            )
        ]
