"""The quality loop (design 8.9): observations, action plans, actions taken and their proof."""

from django.conf import settings
from django.db import models

from apps.academics.models import CourseOffering
from apps.tenancy.models import TenantRecord


def _user_field() -> models.ForeignKey:  # type: ignore[type-arg]
    return models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )


class Observation(TenantRecord):
    """What the lecturer saw in this offering's results."""

    offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="observations"
    )
    text = models.TextField()
    written_by = _user_field()

    class Meta:
        ordering = ["created_at"]


class ActionPlan(TenantRecord):
    """What will be done about it next time. It shows up on the course's later offerings."""

    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="plans")
    text = models.TextField()
    owner = _user_field()
    due_date = models.DateField(null=True, blank=True)
    observation = models.ForeignKey(
        Observation, null=True, blank=True, on_delete=models.SET_NULL, related_name="plans"
    )
    written_by = _user_field()

    class Meta:
        ordering = ["created_at"]


class ActionTaken(TenantRecord):
    """What was actually done, when, recorded on a later offering of the same course."""

    plan = models.ForeignKey(ActionPlan, on_delete=models.CASCADE, related_name="actions")
    offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="actions_taken"
    )
    text = models.TextField()
    done_on = models.DateField()
    recorded_by = _user_field()

    class Meta:
        ordering = ["done_on", "created_at"]
        verbose_name_plural = "actions taken"


class Evidence(TenantRecord):
    """A proof file (PDF, PNG or JPEG) for an action taken. The type is decided from the file's
    own bytes, never from what the browser says."""

    action = models.ForeignKey(ActionTaken, on_delete=models.CASCADE, related_name="evidence")
    name = models.CharField(max_length=120)
    content_type = models.CharField(max_length=30)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    content = models.BinaryField()
    uploaded_by = _user_field()

    audit_exclude = ("content", "name")  # noqa: RUF012

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "evidence"
