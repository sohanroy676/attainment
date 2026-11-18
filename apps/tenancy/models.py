import uuid
from typing import Any

from django.db import models

from .context import get_current_college_id
from .managers import CollegeManager, TenantManager


class College(models.Model):
    """A tenant. Everything else in the system belongs to exactly one college."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CollegeManager()

    def __str__(self) -> str:
        return self.name


class TenantModel(models.Model):
    """Base for every table that holds a college's data.

    Adds college_id and the always-filtering manager. A migration for the table must also
    call tenancy.rls.tenant_rls(table); a test fails the build if it does not.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    college = models.ForeignKey(College, on_delete=models.PROTECT, editable=False)

    objects = TenantManager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.college_id is None:
            current = get_current_college_id()
            if current is None:
                raise RuntimeError("No current college: cannot save a tenant record")
            self.college_id = current
        super().save(*args, **kwargs)


class TenantRecord(TenantModel):
    """A tenant table with created and updated times. Who changed what is in the audit log."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
