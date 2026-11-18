"""v0.9.0: the batch roll-up from course runs (synthetic data only)."""

from decimal import Decimal, localcontext

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from apps.academics.models import Batch, Course, Section
from apps.accounts.tests.helpers import PASSWORD
from apps.outcomes import services as outcomes
from apps.outcomes.models import ProgrammeOutcome
from apps.results import services
from apps.results.models import BatchRun, CalculationRun
from apps.tenancy.services import college_context
from apps.workflow.tests.helpers import make_wf_env, signed
from engine.precision import CALCULATION_CONTEXT

from .helpers import make_results_env, second_programme

pytestmark = [pytest.mark.integration]

D = Decimal


def _prepare(w, target: str = "2.5"):  # type: ignore[no-untyped-def]
    """Targets and indirect values for the batch (PO1 and PO2)."""
    batch = w.env.s.batch
    with college_context(w.college.id):
        for code in ("PO1", "PO2"):
            po = ProgrammeOutcome.objects.get(programme=w.programme, code=code)
            outcomes.set_target(target, outcome=po, batch=batch)
        services.set_batch_indirect(batch, {"PO1": "3", "PO2": "3"}, "test", w.r.iqac)
    return batch


def test_a1_batch_values_follow_the_signed_course_run(db: None) -> None:
    w = make_wf_env()
    batch = _prepare(w)
    with college_context(w.college.id):
        signed(w)
        run = services.signed_run(w.offering, w.programme)
        course_po1 = D(run.values.get(entity="po", key="PO1").value)
        result = services.calculate_batch(batch, w.r.iqac)
        row = result.outputs["outcomes"]["PO1"]
        # [courses, direct, indirect, total, target, attained, status, flag]
        assert row[0] == 1 and D(row[1]) == course_po1 and D(row[2]) == D("3")
        with localcontext(CALCULATION_CONTEXT):  # the engine's precision, so the last digit agrees
            assert D(row[3]) == D("0.8") * course_po1 + D("0.2") * D("3")
        assert row[4] == "2.5" and row[5] is True and row[6] == "ok"
        assert result.status == "complete" and result.checklist == []
        assert result.courses[0]["run"] == str(run.pk) and result.courses[0]["signed"] is True
        assert result.engine_version and result.input_hash


def test_a1_an_unmet_target_says_not_attained(db: None) -> None:
    w = make_wf_env()
    batch = _prepare(w, target="3.9")
    with college_context(w.college.id):
        signed(w)
        result = services.calculate_batch(batch, w.r.iqac)
        assert result.outputs["outcomes"]["PO2"][5] is False


def test_a2_unsigned_courses_are_listed_and_left_out_by_default(db: None) -> None:
    w = make_wf_env()
    batch = _prepare(w)
    with college_context(w.college.id):
        services.calculate(w.offering, w.programme)  # a result exists, but nobody signed it
        default = services.calculate_batch(batch, w.r.iqac)
        assert default.courses == []
        assert [e["reason"] for e in default.excluded] == ["not signed yet"]
        assert default.status == "provisional"
        assert default.outputs["outcomes"]["PO1"][6] == "missing"
        both = services.calculate_batch(batch, w.r.iqac, include_unsigned=True)
        assert len(both.courses) == 1 and both.courses[0]["signed"] is False
        assert both.excluded == []
        assert any("not signed" in line for line in both.checklist)
        assert both.status == "provisional"  # an unsigned course keeps the batch provisional


def test_a3_programmes_sharing_a_course_stay_separate(db: None) -> None:
    r = make_results_env()
    other, _section, _enrolments = second_programme(r)
    w_batch = r.env.s.batch
    with college_context(r.college.id):
        services.calculate(r.offering, r.programme)
        services.calculate(r.offering, other)
        other_batch = Batch.objects.get(programme=other)
        assert [o.pk for o in services.batch_offerings(w_batch)] == [r.offering.pk]
        assert [o.pk for o in services.batch_offerings(other_batch)] == [r.offering.pk]
        first = services.calculate_batch(w_batch, include_unsigned=True)
        second = services.calculate_batch(other_batch, include_unsigned=True)
        assert first.courses[0]["run"] != second.courses[0]["run"]
        assert CalculationRun.objects.get(pk=first.courses[0]["run"]).programme_id == r.programme.pk
        assert CalculationRun.objects.get(pk=second.courses[0]["run"]).programme_id == other.pk


def test_a4_counts_split_into_core_and_non_core(db: None) -> None:
    w = make_wf_env()
    batch = _prepare(w)
    with college_context(w.college.id):
        signed(w)
        core = services.calculate_batch(batch)
        assert core.outputs["counts"] == {"core": [1, 0, 0]}
        Course.objects.filter(pk=w.offering.course_id).update(category="non_core")
        non_core = services.calculate_batch(batch)
        assert non_core.outputs["counts"] == {"non_core": [1, 0, 0]}


def test_a10_a_course_counts_only_where_a_section_of_the_batch_exists(db: None) -> None:
    w = make_wf_env()
    s = w.env.s
    with college_context(w.college.id):
        later = Batch.objects.create(
            programme=w.programme, name="2022-26", start_year=2022, end_year=2026
        )
        assert services.batch_offerings(later) == []
        Section.objects.create(offering=w.offering, name="D", programme=w.programme, batch=later)
        assert [o.pk for o in services.batch_offerings(later)] == [w.offering.pk]
        services.calculate(w.offering, w.programme)
        mixed = services.calculate_batch(s.batch, include_unsigned=True)
        assert any("another batch" in line for line in mixed.checklist)


def test_a_new_run_replaces_the_latest_but_a_kept_one_stays(db: None) -> None:
    w = make_wf_env()
    batch = _prepare(w)
    with college_context(w.college.id):
        signed(w)
        first = services.calculate_batch(batch)
        kept = services.calculate_batch(batch, keep=True)
        last = services.calculate_batch(batch)
        assert not BatchRun.objects.filter(pk=first.pk).exists()
        assert BatchRun.objects.filter(pk=kept.pk, is_latest=False).exists()
        assert services.latest_batch_run(batch).pk == last.pk


def test_the_batch_is_stopped_without_indirect_values_or_targets(db: None) -> None:
    w = make_wf_env()
    batch = w.env.s.batch
    with college_context(w.college.id):
        signed(w)
        result = services.calculate_batch(batch)
        assert result.status == "provisional"
        assert result.outputs["outcomes"]["PO1"][6] == "blocked"
        assert any("indirect value" in line for line in result.checklist)
        assert any("No target" in line for line in result.checklist)


def test_batch_indirect_values_are_checked(db: None) -> None:
    w = make_wf_env()
    batch = w.env.s.batch
    with college_context(w.college.id):
        with pytest.raises(ValidationError, match="not an outcome"):
            services.set_batch_indirect(batch, {"PO99": "3"}, "x", w.r.iqac)
        with pytest.raises(ValidationError, match="between 0 and 10"):
            services.set_batch_indirect(batch, {"PO1": "11"}, "x", w.r.iqac)
        services.set_batch_indirect(batch, {"PO1": "2"}, "first", w.r.iqac)
        services.set_batch_indirect(batch, {"PO1": "4"}, "second", w.r.iqac)
        assert services.BatchIndirect.objects.get(batch=batch, outcome_code="PO1").value == D(4)


def test_a12_another_college_never_sees_the_batch_run(db: None) -> None:
    a = make_wf_env("a")
    b = make_wf_env("b")
    batch_a = _prepare(a)
    with college_context(a.college.id):
        signed(a)
        services.calculate_batch(batch_a)
    with college_context(b.college.id):
        assert BatchRun.objects.count() == 0
        assert services.BatchIndirect.objects.count() == 0
    with college_context(a.college.id):
        assert BatchRun.objects.count() == 1


# the pages -------------------------------------------------
def _login(username: str) -> Client:
    client = Client()
    response = client.post("/accounts/login/", {"username": username, "password": PASSWORD})
    assert response.status_code == 302
    return client


def test_the_batch_page_shows_values_and_says_indirect_is_entered(committed_db: None) -> None:
    w = make_wf_env()
    batch = w.env.s.batch
    with college_context(w.college.id):
        signed(w)
    iqac = _login("a.iqac")
    inputs = f"/results/batch/{batch.pk}/inputs/"
    page = iqac.get(inputs).content.decode()
    assert 'name="target:PO1"' in page and "entered, not measured" in page
    saved = iqac.post(
        inputs, {"target:PO1": "2.5", "target:PO2": "2.5", "indirect:PO1": "3", "indirect:PO2": "3"}
    )
    assert saved.status_code == 302
    assert iqac.post(f"/results/batch/{batch.pk}/", {}).status_code == 302
    page = iqac.get(f"/results/batch/{batch.pk}/").content.decode()
    assert "PO1" in page and "Complete" in page and "Attained" in page
    assert "entered, not measured" in page
    assert "Deep Learning (synthetic)" in page


def test_only_the_right_roles_open_or_change_a_batch(committed_db: None) -> None:
    w = make_wf_env()
    batch = w.env.s.batch
    other = make_wf_env("b")
    url = f"/results/batch/{batch.pk}/"
    assert _login("a.hod").get(url).status_code == 200  # reports.view over the department
    assert _login("a.hod").post(url, {}).status_code == 403  # but not batch.prepare
    assert _login("a.hod").get(url + "inputs/").status_code == 403
    assert _login("a.lecturer_a").get(url).status_code == 403  # section scope only
    assert Client().get(url).status_code == 302  # not logged in: sent to log in
    assert other.college.id != w.college.id
    assert _login("b.iqac").get(url).status_code == 404  # another college's batch is invisible


def test_the_unsigned_switch_marks_the_courses_it_adds(committed_db: None) -> None:
    w = make_wf_env()
    batch = w.env.s.batch
    with college_context(w.college.id):
        services.calculate(w.offering, w.programme)
    iqac = _login("a.iqac")
    url = f"/results/batch/{batch.pk}/"
    iqac.post(url, {})
    assert "Left out" in iqac.get(url).content.decode()
    iqac.post(url, {"include_unsigned": "1"})
    page = iqac.get(url).content.decode()
    assert "not signed yet" in page and "not signed" in page and "checked" in page
