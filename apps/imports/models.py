from django.conf import settings
from django.db import models

from apps.academics.models import Section
from apps.tenancy.models import TenantRecord


class ImportBatch(TenantRecord):
    """One uploaded file and what the system understood from it (design 5.5).

    A batch is first `previewed` (nothing in the roster changed), then `committed` after
    someone confirms, or `rejected` when the file had errors. The parsed rows are kept in
    `payload` so the confirm step applies exactly what was previewed.
    """

    class Kind(models.TextChoices):
        ROSTER = "roster", "Roster"

    class Status(models.TextChoices):
        PREVIEWED = "previewed", "Previewed"
        COMMITTED = "committed", "Committed"
        REJECTED = "rejected", "Rejected"

    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.ROSTER)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PREVIEWED)
    filename = models.CharField(max_length=200)
    file_sha256 = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="+")
    scope = models.CharField(max_length=10, default="section")  # where roll numbers are unique
    payload = models.JSONField(default=dict)  # parsed rows (personal data stays in this table)
    report = models.JSONField(default=dict)  # counts and row errors shown in the preview

    # the audit log records the import by id and counts, never the rows
    audit_exclude = ("payload", "report", "filename")  # noqa: RUF012

    def __str__(self) -> str:
        return f"{self.kind} {self.status}"
