"""Students, identifiers and enrolments (design 5.2).

A roll number is only a label: it can change, repeat in another section, and take any shape. A
student is never created to fill a gap in a roll-number sequence.
"""

from django.db import models

from apps.academics.models import Batch, CourseOffering, Section
from apps.tenancy.models import TenantRecord


class Student(TenantRecord):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        WITHDRAWN = "withdrawn", "Withdrawn"
        DETAINED = "detained", "Detained"
        GRADUATED = "graduated", "Graduated"

    name = models.CharField(max_length=200)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)

    # The audit log refers to people by internal id only (design 12).
    audit_exclude = ("name",)  # noqa: RUF012

    def __str__(self) -> str:
        return str(self.pk)


class StudentIdentifier(TenantRecord):
    """A label for a student with a validity period and a scope.

    Scope says where the value must be unique: the whole college (both scopes empty), one batch,
    or one section. Two sections may both have roll number 1; a roll number that changes keeps
    its history because the old row is closed, not edited. Among current identifiers (no end
    date) the value is unique within its scope.
    """

    class Kind(models.TextChoices):
        ROLL_NO = "roll_no", "Roll number"
        HALL_TICKET = "hall_ticket", "Hall ticket"
        UNIVERSITY_REG = "university_reg", "University registration"
        ERP_ID = "erp_id", "ERP id"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="identifiers")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.ROLL_NO)
    value = models.CharField(max_length=60)
    scope_batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    scope_section = models.ForeignKey(
        Section, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    audit_exclude = ("value",)  # noqa: RUF012

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(scope_batch__isnull=True) | models.Q(scope_section__isnull=True),
                name="identifier_one_scope",
            ),
            models.UniqueConstraint(
                fields=["college", "kind", "value"],
                condition=models.Q(
                    valid_to__isnull=True, scope_batch__isnull=True, scope_section__isnull=True
                ),
                name="identifier_current_unique_college",
            ),
            models.UniqueConstraint(
                fields=["college", "kind", "value", "scope_batch"],
                condition=models.Q(valid_to__isnull=True, scope_batch__isnull=False),
                name="identifier_current_unique_batch",
            ),
            models.UniqueConstraint(
                fields=["college", "kind", "value", "scope_section"],
                condition=models.Q(valid_to__isnull=True, scope_section__isnull=False),
                name="identifier_current_unique_section",
            ),
        ]
        indexes = [models.Index(fields=["college", "kind", "value"])]

    def __str__(self) -> str:
        return f"{self.kind}:{self.pk}"


class BatchMembership(TenantRecord):
    """A student's batch over time. A detained student who joins the next batch keeps both."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="batches")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="memberships")
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True)


class SectionMembership(TenantRecord):
    """The student's home section over time. Where marks count is the enrolment's section."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="sections")
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="memberships")
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True)


class Enrolment(TenantRecord):
    """A student on a course offering. 'Not enrolled' (no row) is not 'enrolled with no mark'."""

    class Status(models.TextChoices):
        ENROLLED = "enrolled", "Enrolled"
        WITHDRAWN = "withdrawn", "Withdrawn"
        EXEMPTED = "exempted", "Exempted"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrolments")
    offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="enrolments"
    )
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="enrolments")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ENROLLED)
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "offering"], name="enrolment_unique")
        ]
