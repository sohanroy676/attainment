"""Builds a small academic structure for tests. Synthetic names only."""

from dataclasses import dataclass
from datetime import date

from apps.academics.models import (
    AcademicYear,
    Batch,
    Course,
    CourseOffering,
    Department,
    Programme,
    Section,
    Term,
)
from apps.tenancy.models import College
from apps.tenancy.services import college_context


@dataclass
class Structure:
    college: College
    department: Department
    programme: Programme
    batch: Batch
    term: Term
    course: Course
    offering: CourseOffering
    section_a: Section
    section_b: Section


def make_structure(college: College, code: str = "CSE") -> Structure:
    with college_context(college.id):
        department = Department.objects.create(name=f"Department {code}", code=code)
        programme = Programme.objects.create(department=department, name=f"B.E. {code}", level="UG")
        batch = Batch.objects.create(
            programme=programme, name="2021-25", start_year=2021, end_year=2025
        )
        year, _ = AcademicYear.objects.get_or_create(
            label="2025-26",
            defaults={"start_date": date(2025, 6, 1), "end_date": date(2026, 5, 31)},
        )
        term, _ = Term.objects.get_or_create(academic_year=year, number=6)
        course = Course.objects.create(title="Deep Learning (synthetic)")
        offering = CourseOffering.objects.create(course=course, term=term)
        a = Section.objects.create(offering=offering, name="A", programme=programme, batch=batch)
        b = Section.objects.create(offering=offering, name="B", programme=programme, batch=batch)
        return Structure(college, department, programme, batch, term, course, offering, a, b)
