"""The college's academic structure (design 5.1). Every table is tenant-owned and RLS-protected."""

from django.conf import settings
from django.db import models

from apps.tenancy.models import TenantRecord


class University(TenantRecord):
    """The affiliating university, as this college records it."""

    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=40, blank=True)

    class Meta:
        verbose_name_plural = "universities"

    def __str__(self) -> str:
        return self.short_name or self.name


class Department(TenantRecord):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["college", "code"], name="dept_code_unique")]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Programme(TenantRecord):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="programmes")
    name = models.CharField(max_length=200)  # B.E. CSE
    level = models.CharField(max_length=40, blank=True)  # UG, PG

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["department", "name"], name="programme_name_unique")
        ]

    def __str__(self) -> str:
        return self.name


class Batch(TenantRecord):
    """A graduating cohort of a programme, for example 2021-25."""

    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="batches")
    name = models.CharField(max_length=40)
    start_year = models.PositiveSmallIntegerField()
    end_year = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name_plural = "batches"
        constraints = [
            models.UniqueConstraint(fields=["programme", "name"], name="batch_name_unique"),
            models.CheckConstraint(
                condition=models.Q(end_year__gt=models.F("start_year")), name="batch_years_ordered"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.programme} {self.name}"


class AcademicYear(TenantRecord):
    label = models.CharField(max_length=20)  # 2025-26
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["college", "label"], name="academic_year_unique"),
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")), name="year_dates_ordered"
            ),
        ]

    def __str__(self) -> str:
        return self.label


class Term(TenantRecord):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="terms")
    number = models.PositiveSmallIntegerField()  # semester number
    name = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["academic_year", "number"], name="term_number_unique")
        ]

    def __str__(self) -> str:
        return f"{self.academic_year} sem {self.number}"


class Course(TenantRecord):
    """A course keeps its identity when its typed code changes (see CourseCode)."""

    class Category(models.TextChoices):
        CORE = "core", "Core"
        NON_CORE = "non_core", "Non-core"

    class Kind(models.TextChoices):
        THEORY = "theory", "Theory"
        LAB = "lab", "Lab"
        PROJECT = "project", "Project"
        ELECTIVE = "elective", "Elective"

    title = models.CharField(max_length=200)
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.CORE)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.THEORY)
    credits = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    def __str__(self) -> str:
        return self.title


class CourseCode(TenantRecord):
    """One of the codes a course has carried (typo fixes, twin codes such as UI21 and UII21)."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="codes")
    code = models.CharField(max_length=40)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["course", "code"], name="course_code_unique"),
        ]

    def __str__(self) -> str:
        return self.code


class CourseGroup(TenantRecord):
    """Links courses that belong together: an open-elective row, or CSE and AIML twin courses."""

    class Kind(models.TextChoices):
        OPEN_ELECTIVE = "open_elective", "Open elective group"
        TWIN = "twin", "Twin courses"

    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    courses = models.ManyToManyField(Course, through="CourseGroupMember", related_name="groups")

    def __str__(self) -> str:
        return self.name


class CourseGroupMember(TenantRecord):
    group = models.ForeignKey(CourseGroup, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "course"], name="group_member_unique")
        ]


class CourseOffering(TenantRecord):
    """One course taught in one term. It may serve several programmes (through its sections)."""

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="offerings")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="offerings")
    coordinator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["course", "term"], name="offering_unique")]

    def __str__(self) -> str:
        return f"{self.course} / {self.term}"


class Section(TenantRecord):
    """A section carries its programme and batch, so results stay separate per programme."""

    offering = models.ForeignKey(CourseOffering, on_delete=models.PROTECT, related_name="sections")
    name = models.CharField(max_length=40)
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="sections")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="sections")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["offering", "name"], name="section_name_unique"),
            # a section's batch always belongs to the section's programme (checked in services)
        ]

    def __str__(self) -> str:
        return f"{self.offering} {self.name}"


class FacultyAssignment(TenantRecord):
    """Who teaches what. A missing section means every section of the offering."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="faculty_assignments"
    )
    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="faculty")
    section = models.ForeignKey(
        Section, null=True, blank=True, on_delete=models.CASCADE, related_name="faculty"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "offering", "section"], nulls_distinct=False, name="faculty_unique"
            )
        ]
