"""Marks per student and question part, with states, history and script mapping (design 5.4).

Blank, 0 and absent are different states and are never merged. A cell carries a row version so
two people cannot silently overwrite each other; every change is written to MarkChange, which
the database refuses to update or delete.
"""

from django.conf import settings
from django.db import models

from apps.assessments.models import Assessment, QuestionPart
from apps.roster.models import Enrolment, Student
from apps.tenancy.models import TenantRecord


class MarkSheetRow(TenantRecord):
    """One student's row for one assessment. No row at all means "not started"."""

    class Attempt(models.TextChoices):
        REGULAR = "regular", "Regular"
        SUPPLEMENTARY = "supplementary", "Supplementary"
        IMPROVEMENT = "improvement", "Improvement"

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        ENTERED = "entered", "Entered"
        SUBMITTED = "submitted", "Submitted"

    enrolment = models.ForeignKey(Enrolment, on_delete=models.CASCADE, related_name="mark_rows")
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="rows")
    attempt = models.CharField(max_length=14, choices=Attempt.choices, default=Attempt.REGULAR)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NOT_STARTED)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["enrolment", "assessment", "attempt"], name="mark_row_unique"
            )
        ]


class MarkCell(TenantRecord):
    class State(models.TextChoices):
        VALUE = "value", "Value"  # a number, including 0
        BLANK = "blank", "Blank"
        ABSENT = "absent", "Absent"
        WITHHELD = "withheld", "Withheld"
        EXEMPTED = "exempted", "Exempted"
        NOT_APPLICABLE = "not_applicable", "Not applicable"
        NOT_ATTEMPTED = "not_attempted", "Not attempted"

    row = models.ForeignKey(MarkSheetRow, on_delete=models.CASCADE, related_name="cells")
    part = models.ForeignKey(QuestionPart, on_delete=models.CASCADE, related_name="cells")
    state = models.CharField(max_length=14, choices=State.choices)
    value = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    entered_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=10, default="manual")  # manual or import
    import_batch = models.UUIDField(null=True, blank=True)
    row_version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["row", "part"], name="mark_cell_unique"),
            models.CheckConstraint(
                condition=(models.Q(state="value", value__isnull=False))
                | (~models.Q(state="value") & models.Q(value__isnull=True)),
                name="mark_cell_value_matches_state",
            ),
            models.CheckConstraint(condition=models.Q(value__gte=0), name="mark_cell_not_negative"),
        ]


class MarkChange(TenantRecord):
    """Append-only history of every cell change (design 12): who, when, old, new, why."""

    cell_id_value = models.UUIDField()  # the cell's id; kept even if the cell is removed later
    row_id_value = models.UUIDField()
    part_code = models.CharField(max_length=40)
    old_state = models.CharField(max_length=14, blank=True)
    old_value = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    new_state = models.CharField(max_length=14)
    new_value = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    at = models.DateTimeField()
    reason = models.TextField(blank=True)
    import_batch = models.UUIDField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["cell_id_value", "at"])]
        ordering = ["at"]


class ScriptMapping(TenantRecord):
    """Joins SEE script numbers to students (the exam branch's mapping)."""

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="scripts")
    script_no = models.CharField(max_length=40)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="scripts")
    source = models.CharField(max_length=40, default="import")
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    audit_exclude = ("script_no",)  # noqa: RUF012

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["assessment", "script_no"], name="script_no_unique"),
            models.UniqueConstraint(fields=["assessment", "student"], name="script_student_unique"),
        ]
