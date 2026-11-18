"""v0.11.0 A7: the performance suite on synthetic data.

Batch run (100 courses by 15 outcomes) is timed in apps/results/tests/test_batch_speed.py (under
3 s, the limit here is 5 s). This file times the marks grid (130 students by 30 parts, under 2 s),
the course result page (under 1 s) and the rendering of a report.
"""

import time
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.tests.helpers import PASSWORD
from apps.assessments import services as papers
from apps.assessments.models import Assessment
from apps.marks.models import MarkCell, MarkSheetRow
from apps.marks.tests.helpers import make_env
from apps.results import services as results
from apps.results.tests.helpers import make_results_env
from apps.tenancy.services import college_context

pytestmark = [pytest.mark.integration, pytest.mark.perf]

STUDENTS, QUESTIONS, PARTS_PER_QUESTION = 130, 6, 5  # 30 parts


def _login(username: str) -> Client:
    client = Client()
    assert (
        client.post("/accounts/login/", {"username": username, "password": PASSWORD}).status_code
        == 302
    )
    return client


def test_a7_a_marks_grid_of_130_students_by_30_parts_opens_in_under_two_seconds(
    committed_db: None,
) -> None:
    env = make_env(students_a=STUDENTS)
    with college_context(env.college.id):
        paper = papers.create_paper(
            env.s.offering,
            "PERF",
            "Perf test",
            Assessment.Behaviour.QUESTION_WISE,
            [
                {
                    "number": str(q),
                    "choice_group": None,
                    "parts": [
                        {"label": f"{chr(97 + p)}", "max": "2", "co": "CO1"}
                        for p in range(PARTS_PER_QUESTION)
                    ],
                }
                for q in range(1, QUESTIONS + 1)
            ],
        )
        parts = list(paper.parts.all())
        assert len(parts) == QUESTIONS * PARTS_PER_QUESTION
        rows = MarkSheetRow.objects.bulk_create(
            MarkSheetRow(college_id=env.college.id, enrolment=e, assessment=paper)
            for e in env.enrolments_a
        )
        MarkCell.objects.bulk_create(
            MarkCell(
                college_id=env.college.id, row=row, part=part, state="value",
                value=Decimal("1.5"), entered_at=timezone.now(), source="import",
            )
            for row in rows
            for part in parts
        )  # fmt: skip
    client = _login("a.lecturer_a")
    url = f"/marks/{paper.pk}/{env.s.section_a.pk}/"
    started = time.monotonic()
    response = client.get(url)
    seconds = time.monotonic() - started
    assert response.status_code == 200, url
    assert response.content.count(b'name="cell:') == STUDENTS * QUESTIONS * PARTS_PER_QUESTION
    assert seconds < 2, f"the grid took {seconds:.2f} s"


def test_a7_the_course_result_page_and_a_report_open_in_under_a_second(
    committed_db: None,
) -> None:
    r = make_results_env()
    with college_context(r.college.id):
        results.calculate(r.offering, r.programme)
    client = _login("a.iqac")
    for url in (
        f"/results/{r.offering.pk}/",
        f"/reports/course/{r.offering.pk}/analysis.html",
    ):
        started = time.monotonic()
        response = client.get(url)
        seconds = time.monotonic() - started
        assert response.status_code == 200, url
        assert seconds < 1, f"{url} took {seconds:.2f} s"
