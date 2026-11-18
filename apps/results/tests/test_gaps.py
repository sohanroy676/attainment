"""v0.9.0: the gap view (COs and POs below target, the weakest questions)."""

import pytest
from django.test import Client

from apps.accounts.tests.helpers import PASSWORD
from apps.outcomes import services as outcomes
from apps.outcomes.models import ProgrammeOutcome
from apps.results import services
from apps.tenancy.services import college_context
from apps.workflow.tests.helpers import make_wf_env, signed

from .helpers import make_results_env

pytestmark = [pytest.mark.integration]


def test_a7_cos_under_the_target_are_listed_with_the_shortfall(db: None) -> None:
    r = make_results_env()
    with college_context(r.college.id):
        outcomes.set_target("3", offering=r.offering)
        services.calculate(r.offering, r.programme)
        gaps = services.course_gaps(r.offering, r.programme)
        # section B's half-passed Internal-I part 1a pulls CO1 to 2.84 (hand-worked in v0.7.0)
        assert [(g.key, g.value, g.target, g.shortfall) for g in gaps.cos] == [
            ("CO1", "2.84", "3", "0.16")
        ]
        assert gaps.complete


def test_no_gap_when_everything_meets_the_target(db: None) -> None:
    r = make_results_env()
    with college_context(r.college.id):
        services.calculate(r.offering, r.programme)  # the target is 2.2
        gaps = services.course_gaps(r.offering, r.programme)
        assert gaps.cos == []


def test_a7_the_weakest_question_comes_first_and_sections_are_pooled(db: None) -> None:
    r = make_results_env()
    with college_context(r.college.id):
        services.calculate(r.offering, r.programme)
        questions = services.course_gaps(r.offering, r.programme).questions
        first = questions[0]
        assert (first.tool, first.part, first.passed, first.denominator) == ("INT1", "1a", 6, 7)
        assert first.percent == "85.71" and first.co == "CO1"
        ranked = [q for q in questions if q.percent != "-"]
        assert [q.percent for q in ranked] == sorted(
            (q.percent for q in ranked), key=lambda p: float(p)
        )
        assert len(services.course_gaps(r.offering, r.programme, question_limit=2).questions) == 2


def test_there_are_no_gaps_to_show_before_any_result(db: None) -> None:
    r = make_results_env(with_marks=False)
    with college_context(r.college.id):
        assert services.course_gaps(r.offering, r.programme) is None


def test_a_provisional_result_says_so(db: None) -> None:
    r = make_results_env()
    with college_context(r.college.id):
        services.calculate(r.offering, r.programme)
        from apps.results.models import IndirectValue

        IndirectValue.objects.filter(offering=r.offering, co_code="CO1").delete()
        services.calculate(r.offering, r.programme)
        assert services.course_gaps(r.offering, r.programme).complete is False


def _batch_ready(w, target: str):  # type: ignore[no-untyped-def]
    batch = w.env.s.batch
    with college_context(w.college.id):
        for code in ("PO1", "PO2"):
            po = ProgrammeOutcome.objects.get(programme=w.programme, code=code)
            outcomes.set_target(target, outcome=po, batch=batch)
        services.set_batch_indirect(batch, {"PO1": "3", "PO2": "3"}, "test", w.r.iqac)
        if services.signed_run(w.offering, w.programme) is None:
            signed(w)
        services.calculate_batch(batch, w.r.iqac)
    return batch


def test_a7_pos_under_their_batch_target_are_listed(db: None) -> None:
    w = make_wf_env()
    batch = _batch_ready(w, "3.9")
    with college_context(w.college.id):
        run, rows = services.batch_gaps(batch)
        assert sorted(g.key for g in rows) == ["PO1", "PO2"]
        assert all(g.target == "3.9" for g in rows)
        assert rows[0].shortfall >= rows[1].shortfall  # biggest shortfall first
        met = _batch_ready(w, "2.5")
        assert services.batch_gaps(met)[1] == []


def test_the_gap_pages(committed_db: None) -> None:
    w = make_wf_env()
    batch = _batch_ready(w, "3.9")
    with college_context(w.college.id):
        outcomes.set_target("3", offering=w.offering)
        services.calculate(w.offering, w.programme)
    client = Client()
    login = client.post("/accounts/login/", {"username": "a.iqac", "password": PASSWORD})
    assert login.status_code == 302
    page = client.get(f"/results/{w.offering.pk}/gaps/").content.decode()
    assert "CO1" in page and "2.84" in page and "Weakest questions" in page and "1a" in page
    page = client.get(f"/results/batch/{batch.pk}/gaps/").content.decode()
    assert "PO1" in page and "3.9" in page
    hod = Client()
    assert (
        hod.post("/accounts/login/", {"username": "a.hod", "password": PASSWORD}).status_code == 302
    )
    assert hod.get(f"/results/{w.offering.pk}/gaps/").status_code == 200
    lecturer = Client()
    lecturer.post("/accounts/login/", {"username": "a.lecturer_a", "password": PASSWORD})
    assert lecturer.get(f"/results/{w.offering.pk}/gaps/").status_code == 403
    assert lecturer.get(f"/results/batch/{batch.pk}/gaps/").status_code == 403
    other = make_wf_env("b")
    assert other.college.id != w.college.id
    foreign = Client()
    foreign.post("/accounts/login/", {"username": "b.iqac", "password": PASSWORD})
    assert foreign.get(f"/results/{w.offering.pk}/gaps/").status_code == 404
    assert foreign.get(f"/results/batch/{batch.pk}/gaps/").status_code == 404
