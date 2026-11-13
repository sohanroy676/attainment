from django.db import models

from apps.tenancy.models import TenantModel


class AuditEvent(TenantModel):
    """One line of the append-only audit log (design section 12).

    The database refuses UPDATE and DELETE for every role (trigger) and the app role holds no
    such privilege either. Each row carries the hash of the previous row of the same college,
    so a removed or edited row breaks the chain. Students are referred to by internal id only.
    """

    seq = models.PositiveBigIntegerField()
    actor_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=80)
    entity = models.CharField(max_length=80)
    entity_id = models.CharField(max_length=80, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField()
    hash_prev = models.CharField(max_length=64, blank=True)
    hash = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["college", "seq"], name="audit_seq_unique_per_college")
        ]
        ordering = ["seq"]

    def __str__(self) -> str:
        return f"{self.seq} {self.action}"
