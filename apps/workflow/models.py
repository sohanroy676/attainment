from django.conf import settings
from django.db import models

from apps.academics.models import CourseOffering, Programme, Section
from apps.assessments.models import Assessment
from apps.results.models import CalculationRun
from apps.tenancy.models import TenantRecord


class SectionState(TenantRecord):
    """Where one section's marks for one assessment stand: draft, submitted, accepted, returned."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        ACCEPTED = "accepted", "Accepted"
        RETURNED = "returned", "Returned for correction"

    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="states")
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="states")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    reason = models.TextField(blank=True)  # why it was returned
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["section", "assessment"], name="section_state_unique")
        ]


class ResultStage(TenantRecord):
    """Where one course result (offering and programme) stands: reviewed, approved, signed, or
    reopened. `cycle` counts signature cycles; a reopen starts the next one."""

    class Status(models.TextChoices):
        REVIEWED = "reviewed", "Reviewed"
        APPROVED = "approved", "Approved"
        SIGNED = "signed", "Signed"
        REOPENED = "reopened", "Reopened"

    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="stages")
    programme = models.ForeignKey(Programme, on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices)
    cycle = models.PositiveIntegerField(default=1)
    run = models.ForeignKey(
        CalculationRun, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )  # the kept run taken at approval

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["offering", "programme"], name="result_stage_unique")
        ]


class Signature(TenantRecord):
    """An approval record: who approved or signed what, in which role, when, and the hash of the
    run it covered. Never edited or deleted by the app."""

    class Kind(models.TextChoices):
        APPROVAL = "approval", "Approval"
        SIGNATURE = "signature", "Signature"

    stage = models.ForeignKey(ResultStage, on_delete=models.CASCADE, related_name="signatures")
    cycle = models.PositiveIntegerField()
    kind = models.CharField(max_length=10, choices=Kind.choices)
    run = models.ForeignKey(CalculationRun, on_delete=models.PROTECT, related_name="+")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    signer_name = models.CharField(max_length=200)
    role = models.CharField(max_length=30)
    at = models.DateTimeField()
    content_hash = models.CharField(max_length=64)

    audit_exclude = ("signer_name",)  # noqa: RUF012


class Reopening(TenantRecord):
    stage = models.ForeignKey(ResultStage, on_delete=models.CASCADE, related_name="reopenings")
    from_cycle = models.PositiveIntegerField()
    from_status = models.CharField(max_length=10)
    reason = models.TextField()
    by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    at = models.DateTimeField()


class SupportGrant(TenantRecord):
    """A time-limited right for a support person to see this college's marks (design section 9).
    Given by the college admin, logged, and void after `expires_at`."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    reason = models.TextField()
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False)
