"""Programme outcomes, course outcomes, the CO-PO map and targets (design 5.3)."""

from django.conf import settings
from django.db import models

from apps.academics.models import Batch, Course, CourseOffering, Programme
from apps.tenancy.models import TenantRecord


class ProgrammeOutcome(TenantRecord):
    """A PO, PSO or PEO of a programme. PEOs are stored for reports, not calculated."""

    class Kind(models.TextChoices):
        PO = "PO", "Programme outcome"
        PSO = "PSO", "Programme specific outcome"
        PEO = "PEO", "Programme educational objective"

    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="outcomes")
    kind = models.CharField(max_length=3, choices=Kind.choices)
    code = models.CharField(max_length=10)  # PO1, PSO2, PEO1
    text = models.TextField(blank=True)
    version = models.PositiveSmallIntegerField(default=1)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["programme", "code", "version"], name="programme_outcome_unique"
            )
        ]
        ordering = ["programme", "kind", "code"]

    def __str__(self) -> str:
        return f"{self.programme} {self.code}"


class CourseDefinitionVersion(TenantRecord):
    """COs and their mapping are versioned per course: a revised syllabus is a new version."""

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="definitions")
    version = models.PositiveSmallIntegerField(default=1)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["course", "version"], name="course_definition_unique")
        ]

    def __str__(self) -> str:
        return f"{self.course} v{self.version}"


class CourseOutcome(TenantRecord):
    definition = models.ForeignKey(
        CourseDefinitionVersion, on_delete=models.CASCADE, related_name="outcomes"
    )
    code = models.CharField(max_length=10)  # CO1 .. COn (four COs are fine)
    text = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["definition", "code"], name="course_outcome_unique")
        ]
        ordering = ["definition", "order", "code"]

    def __str__(self) -> str:
        return self.code


class COPOMap(TenantRecord):
    """Strength 1 to 3 or an explicit 0. No row at all means "not mapped" (blank, not 0)."""

    co = models.ForeignKey(CourseOutcome, on_delete=models.CASCADE, related_name="mappings")
    outcome = models.ForeignKey(ProgrammeOutcome, on_delete=models.PROTECT, related_name="+")
    strength = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["co", "outcome"], name="copo_unique"),
            models.CheckConstraint(
                condition=models.Q(strength__gte=0, strength__lte=3), name="copo_strength_0_to_3"
            ),
        ]


class Target(TenantRecord):
    """A target for a course offering, or for a programme outcome of a batch (exactly one)."""

    class Source(models.TextChoices):
        SET = "set", "Set"
        REVISED = "revised", "Revised by rule"

    offering = models.ForeignKey(
        CourseOffering, null=True, blank=True, on_delete=models.CASCADE, related_name="targets"
    )
    outcome = models.ForeignKey(
        ProgrammeOutcome, null=True, blank=True, on_delete=models.PROTECT, related_name="targets"
    )
    batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    value = models.DecimalField(max_digits=5, decimal_places=3)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.SET)
    rule_used = models.CharField(max_length=80, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(offering__isnull=False, outcome__isnull=True, batch__isnull=True)
                    | models.Q(offering__isnull=True, outcome__isnull=False, batch__isnull=False)
                ),
                name="target_one_scope",
            ),
            models.CheckConstraint(
                condition=models.Q(value__gte=0, value__lte=10), name="target_value_range"
            ),
            models.UniqueConstraint(
                fields=["offering"],
                condition=models.Q(offering__isnull=False),
                name="target_offering",
            ),
            models.UniqueConstraint(
                fields=["outcome", "batch"],
                condition=models.Q(outcome__isnull=False),
                name="target_outcome_batch",
            ),
        ]
