"""v0.9.0 A11: a batch of 100 courses by 15 outcomes builds and renders in under 3 seconds."""

import time
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

from apps.academics.models import Course, CourseOffering, Section
from apps.accounts.tests.helpers import PASSWORD
from apps.outcomes import services as outcomes
from apps.outcomes.models import ProgrammeOutcome
from apps.results import services
from apps.results.models import CalculationRun, ResultValue
from apps.tenancy.services import college_context

from .helpers import make_results_env

pytestmark = [pytest.mark.integration, pytest.mark.perf]

COURSES = 100
OUTCOMES = [("PO", f"PO{n}", "") for n in range(3, 13)] + [
    ("PSO", f"PSO{n}", "") for n in range(1, 4)
]  # with PO1 and PO2 from the helper: 12 POs and 3 PSOs


def _big_batch():  # type: ignore[no-untyped-def]
    """100 signed course runs with 15 outcome values each, written in bulk (no engine runs)."""
    r = make_results_env(with_marks=False)
    env = r.env
    college_id = r.college.id
    with college_context(college_id):
        outcomes.create_programme_outcomes(r.programme, OUTCOMES)
        codes = [o.code for o in services.batch_outcomes(r.programme)]
        assert len(codes) == 15
        for code in codes:
            po = ProgrammeOutcome.objects.get(programme=r.programme, code=code)
            outcomes.set_target("2.5", outcome=po, batch=env.s.batch)
        services.set_batch_indirect(env.s.batch, dict.fromkeys(codes, "3"), "speed", r.iqac)
        version = services.methods.method_for_offering(env.s.offering)[0]
        courses = Course.objects.bulk_create(
            Course(
                college_id=college_id,
                title=f"Course {i:03d}",
                category="core" if i % 2 else "non_core",
            )
            for i in range(COURSES - 1)
        )
        new = CourseOffering.objects.bulk_create(
            CourseOffering(college_id=college_id, course=c, term=env.s.term) for c in courses
        )
        Section.objects.bulk_create(
            Section(
                college_id=college_id,
                offering=o,
                name="A",
                programme=r.programme,
                batch=env.s.batch,
            )  # fmt: skip
            for o in new
        )
        offerings = [env.s.offering, *new]  # the helper's own course is the 100th
        runs = CalculationRun.objects.bulk_create(
            CalculationRun(
                college_id=college_id,
                offering=o,
                programme=r.programme,
                method_version=version,
                engine_version="speed",
                input_hash=f"{i:064d}",
                at=timezone.now(),
                status="complete",
                is_latest=True,
                kept=True,
                outputs={"attained": True},
            )  # fmt: skip
            for i, o in enumerate(offerings)
        )
        ResultValue.objects.bulk_create(
            ResultValue(
                college_id=college_id,
                run=run,
                entity="po",
                key=code,
                value=str(Decimal("2.5") + Decimal(i % 7) / 10),
                status="ok",
            )  # fmt: skip
            for i, run in enumerate(runs)
            for code in codes
        )
        CalculationRun.objects.filter(pk__in=[run.pk for run in runs]).update(
            signed=True, content_hash="f" * 64
        )  # sealed last: the database refuses values being added to a signed run
    return r, codes


def test_a11_a_batch_of_100_courses_by_15_outcomes_under_three_seconds(committed_db: None) -> None:
    r, codes = _big_batch()
    batch = r.env.s.batch
    client = Client()
    login = client.post("/accounts/login/", {"username": "a.iqac", "password": PASSWORD})
    assert login.status_code == 302

    started = time.perf_counter()
    posted = client.post(f"/results/batch/{batch.pk}/", {})  # the roll-up itself
    calculated = time.perf_counter() - started
    assert posted.status_code == 302

    started = time.perf_counter()
    page = client.get(f"/results/batch/{batch.pk}/")
    rendered = time.perf_counter() - started
    assert page.status_code == 200

    text = page.content.decode()
    assert all(f">{code}<" in text for code in codes)
    assert text.count("<li><a href=") >= COURSES  # every course is listed as used
    with college_context(r.college.id):
        checklist = services.latest_batch_run(batch).checklist
    assert "Complete" in text, checklist[:5]
    assert calculated < 3, f"roll-up took {calculated:.2f}s"
    assert rendered < 3, f"page took {rendered:.2f}s"
    with college_context(r.college.id):
        run = services.latest_batch_run(batch)
        assert len(run.courses) == COURSES and run.excluded == []
        assert run.outputs["counts"] == {
            "core": [COURSES // 2, 0, 0],
            "non_core": [COURSES // 2, 0, 0],
        }
