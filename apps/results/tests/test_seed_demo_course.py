"""v1.0.0: the demo data. Two colleges with different roll schemes and a calculated course."""

import io
import uuid

import pytest
from django.core.management import call_command

from apps.academics.models import CourseOffering
from apps.accounts.management.commands.seed_demo import NAMESPACE
from apps.results import services
from apps.results.present import present
from apps.roster import services as roster
from apps.roster.models import Student
from apps.tenancy.services import college_context

pytestmark = [pytest.mark.integration]


def test_the_demo_course_is_seeded_in_both_colleges_with_different_roll_schemes(
    committed_db: None,
) -> None:
    call_command("seed_demo", "--password", "A long demo password 1", stdout=io.StringIO())
    out = io.StringIO()
    call_command("seed_demo_course", stdout=out)
    assert "Added the demo course to college(s) A, B" in out.getvalue()
    for code, sizes in (("a", (40, 27)), ("b", (66, 64))):
        with college_context(uuid.uuid5(NAMESPACE, f"college:{code}")):
            offering = CourseOffering.objects.get()
            counts = [
                roster.enrolled_students(offering, s).count()
                for s in offering.sections.order_by("name")
            ]
            assert tuple(counts) == sizes and Student.objects.count() == sum(sizes)
            programme = services.programmes_of(offering)[0]
            run = services.latest_run(offering, programme)
            shown = present(run)
            assert run is not None and shown.course_text != "-" and shown.tables
    with college_context(uuid.uuid5(NAMESPACE, "college:b")):
        offering = CourseOffering.objects.get()
        section_b = offering.sections.get(name="B")
        assert (
            roster.find_by_identifier("67", batch=section_b.batch) is not None
        )  # 1-66 then 67-130
    with college_context(uuid.uuid5(NAMESPACE, "college:a")):
        offering = CourseOffering.objects.get()
        assert roster.find_by_identifier("1", section=offering.sections.get(name="A")) is not None
        assert roster.find_by_identifier("1", section=offering.sections.get(name="B")) is not None
    again = io.StringIO()
    call_command("seed_demo_course", stdout=again)
    assert again.getvalue().count("already has the course") == 2


def test_seeding_the_course_needs_the_demo_colleges_first(committed_db: None) -> None:
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="seed_demo"):
        call_command("seed_demo_course", stdout=io.StringIO())
