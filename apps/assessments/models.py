"""Assessments and question papers (design 5.4). Marks live in the marks module (later)."""

from django.conf import settings
from django.db import models

from apps.academics.models import CourseOffering
from apps.outcomes.models import CourseOutcome
from apps.tenancy.models import TenantRecord


class Assessment(TenantRecord):
    """One assessment of one offering, shared by all its sections: Internal-I, SEE, Quiz..."""

    class Behaviour(models.TextChoices):
        QUESTION_WISE = "question_wise", "Question-wise"
        PER_STUDENT_AVERAGE = "per_student_average", "Per-student average"
        SINGLE_TOTAL = "single_total", "Single total"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open for marks"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        LOCKED = "locked", "Locked"

    offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="assessments"
    )
    tool = models.CharField(max_length=20)  # the key the method uses: INT1, INT2, SEE, QUIZ ...
    name = models.CharField(max_length=100)
    behaviour = models.CharField(max_length=20, choices=Behaviour.choices)
    max_total = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["offering", "tool"], name="assessment_tool_unique")
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.offering})"


class ChoiceGroup(TenantRecord):
    """Questions of which a student answers only some: best N questions, best K parts of one."""

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="groups")
    code = models.CharField(max_length=10)
    best_n = models.PositiveSmallIntegerField()
    best_k_parts = models.JSONField(default=dict, blank=True)  # question number -> K
    missing_counts_as = models.CharField(
        max_length=10, default="excluded", choices=[("excluded", "Excluded"), ("zero", "Zero")]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["assessment", "code"], name="choice_group_unique"),
            models.CheckConstraint(
                condition=models.Q(best_n__gte=1), name="choice_best_n_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.assessment.tool} group {self.code}"


class Question(TenantRecord):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="questions")
    number = models.CharField(max_length=10)  # "11"
    order = models.PositiveSmallIntegerField(default=0)
    choice_group = models.ForeignKey(
        ChoiceGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name="questions"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["assessment", "number"], name="question_number_unique")
        ]
        ordering = ["assessment", "order", "number"]

    def __str__(self) -> str:
        return f"Q{self.number}"


class QuestionPart(TenantRecord):
    """Marks and CO tags live at part level. A part with no CO applies to every CO (quiz item)."""

    class OverrideStatus(models.TextChoices):
        NONE = "none", "No override"
        PENDING = "pending", "Waiting for IQAC approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="parts")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="parts")
    label = models.CharField(max_length=10, blank=True)  # "a"
    code = models.CharField(max_length=40)  # the id the engine uses, unique within the paper
    max = models.DecimalField(max_digits=6, decimal_places=2)
    co = models.ForeignKey(
        CourseOutcome, null=True, blank=True, on_delete=models.PROTECT, related_name="parts"
    )
    order = models.PositiveSmallIntegerField(default=0)

    # a per-part pass mark that replaces the method's percentage, with a reason and approval
    override_pass_mark = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    override_reason = models.TextField(blank=True)
    override_status = models.CharField(
        max_length=10, choices=OverrideStatus.choices, default=OverrideStatus.NONE
    )
    override_entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    override_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["assessment", "code"], name="part_code_unique"),
            models.CheckConstraint(condition=models.Q(max__gt=0), name="part_max_positive"),
            models.CheckConstraint(
                condition=models.Q(override_pass_mark__isnull=True) | ~models.Q(override_reason=""),
                name="part_override_needs_reason",
            ),
        ]
        ordering = ["assessment", "order", "code"]

    def __str__(self) -> str:
        return self.code
