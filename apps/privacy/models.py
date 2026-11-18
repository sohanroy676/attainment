"""Retention notices: the written warning that a student's identity will be anonymised."""

from django.conf import settings
from django.db import models

from apps.roster.models import Student
from apps.tenancy.models import TenantRecord


class RetentionNotice(TenantRecord):
    """A student whose batch is past the retention period has been put on notice.

    The identity is anonymised only once `notified_on` plus the notice period has passed.
    `anonymised_on` is set when it was done. One row per student.
    """

    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name="retention")
    notified_on = models.DateField()
    notified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    anonymised_on = models.DateField(null=True, blank=True)
