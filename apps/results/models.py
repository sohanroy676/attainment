"""Calculation runs and result values (design 5.5, 6.6).

A run stores everything needed to explain it: the method version, the engine version, the input
hash, the full output and the trace. Automatic runs replace the one "latest" run of their scope;
a run that is kept (snapshot) stays forever.
"""

from django.conf import settings
from django.db import models

from apps.academics.models import CourseOffering, Programme
from apps.methodology.models import MethodVersion
from apps.tenancy.models import TenantRecord


class IndirectValue(TenantRecord):
    """An indirect attainment value entered by IQAC. Until surveys exist (v1.3) it is entered,
    not measured, and every screen says so."""

    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="indirect")
    co_code = models.CharField(max_length=10)
    value = models.DecimalField(max_digits=5, decimal_places=3)
    source_note = models.CharField(max_length=200, blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["offering", "co_code"], name="indirect_unique"),
            models.CheckConstraint(
                condition=models.Q(value__gte=0, value__lte=10), name="indirect_value_range"
            ),
        ]


class CalculationRun(TenantRecord):
    class Status(models.TextChoices):
        PROVISIONAL = "provisional", "Provisional"
        COMPLETE = "complete", "Complete"

    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="runs")
    programme = models.ForeignKey(
        Programme, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    method_version = models.ForeignKey(
        MethodVersion, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    engine_version = models.CharField(max_length=20, blank=True)
    input_hash = models.CharField(max_length=64, blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    at = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROVISIONAL)
    is_latest = models.BooleanField(default=True)
    kept = models.BooleanField(default=False)  # a snapshot: never replaced or removed
    signed = models.BooleanField(default=False)  # frozen at sign-off: the database refuses changes
    content_hash = models.CharField(max_length=64, blank=True)  # set when signed
    outputs = models.JSONField(default=dict)
    trace = models.JSONField(default=dict)
    checklist = models.JSONField(default=list)  # what is missing, in plain words

    audit_exclude = ("outputs", "trace", "checklist")  # noqa: RUF012

    class Meta:
        ordering = ["-at"]
        indexes = [models.Index(fields=["offering", "programme", "is_latest"])]


class ResultValue(TenantRecord):
    """One queryable value of a run: a CO, the course, or a PO/PSO. The value is exact text."""

    run = models.ForeignKey(CalculationRun, on_delete=models.CASCADE, related_name="values")
    entity = models.CharField(max_length=10)  # co_direct, co_final, course, po
    key = models.CharField(max_length=40)
    value = models.CharField(max_length=60, blank=True)  # exact decimal text; blank when none
    display = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10)  # ok, missing, blocked
    flags = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "entity", "key"], name="result_value_unique")
        ]
