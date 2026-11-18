"""Items carried over from v0.8.0 and v0.9.0: batch tasks in the inbox, the department-scoped
audit viewer, the "overridden" marker, the target proposal, editing observations and plans."""

from decimal import Decimal as D

import pytest
from django.core.exceptions import PermissionDenied
from django.test import Client

from apps.accounts.tests.helpers import PASSWORD
from apps.assessments import services as papers
from apps.assessments.models import QuestionPart
from apps.audit import services as audit
from apps.audit.models import AuditEvent
from apps.outcomes import services as outcomes
from apps.outcomes.models import ProgrammeOutcome
from apps.quality import services as quality
from apps.quality.models import ActionPlan, Observation
from apps.results import services as results
from apps.tenancy.services import college_context
from apps.workflow import services as wf
from apps.workflow.tests.helpers import make_wf_env, signed
from engine.schema import ReviseRule

pytestmark = [pytest.mark.integration]


def _login(username: str) -> Client:
    client = Client()
    assert (
        client.post("/accounts/login/", {"username": username, "password": PASSWORD}).status_code
        == 302
    )
    return client


def _kinds(user) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    return [(t.kind, t.label) for t in wf.inbox(user) if t.batch_id]


# batch tasks in the inbox ----------------------------------------------------------------
def test_batch_steps_show_up_in_the_inbox_of_the_person_who_holds_the_next_step(db: None) -> None:
    w = make_wf_env()
    batch = w.env.s.batch
    with college_context(w.college.id):
        for code in ("PO1", "PO2"):
            po = ProgrammeOutcome.objects.get(programme=w.programme, code=code)
            outcomes.set_target("2.5", outcome=po, batch=batch)
        results.set_batch_indirect(batch, {"PO1": "3", "PO2": "3"}, "test", w.r.iqac)
        assert _kinds(w.r.iqac) == []  # no batch result yet: nothing to prepare
        signed(w)
        results.calculate_batch(batch, w.r.iqac)
        assert [k for k, _ in _kinds(w.r.iqac)] == ["prepare"]
        assert _kinds(w.r.hod) == [] and _kinds(w.principal) == []
        wf.prepare_batch(batch, w.r.iqac)
        assert [k for k, _ in _kinds(w.r.hod)] == ["approve"] and _kinds(w.r.iqac) == []
        wf.approve_batch(batch, w.r.hod)
        assert [k for k, _ in _kinds(w.principal)] == ["sign"] and _kinds(w.r.hod) == []
        assert _kinds(w.env.lecturer_a) == []
        wf.sign_batch(batch, w.principal)
        assert _kinds(w.principal) == []  # signed: nothing waits
    page = _login("a.principal")  # the inbox page itself renders with a batch task present
    assert page.get("/workflow/").status_code == 200


# department-scoped audit viewer ------------------------------------------------------------
def test_a_hod_reads_the_audit_events_of_their_department_only(committed_db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        signed(w)
        audit.record("note.made", "thing", entity_id="somewhere-else")
        scope = wf.audit_scope(w.r.hod)
        assert scope is not None
        actions = set(scope.values_list("action", flat=True))
        assert "note.made" not in actions  # not about this department
        assert any(a.startswith("results.calculationrun") for a in actions)  # about its results
        assert wf.audit_scope(w.r.iqac).filter(action="note.made").exists()  # college-wide right
        assert wf.audit_scope(w.env.lecturer_a) is None  # no audit right at all
        assert wf.audit_scope(w.env.exam) is None
    hod = _login("a.hod")
    page = hod.get("/workflow/audit/")
    assert page.status_code == 200 and b"note.made" not in page.content
    assert b"results.calculationrun" in page.content
    assert _login("a.iqac").get("/workflow/audit/").status_code == 200
    assert _login("a.lecturer_a").get("/workflow/audit/").status_code == 403


# the overridden marker and the target proposal ------------------------------------------------
def test_the_result_page_marks_overridden_pass_marks(committed_db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        part = QuestionPart.objects.get(assessment=w.env.internal, code="1a")
        results.calculate(w.offering, w.programme)
    iqac = _login("a.iqac")
    assert b"Overridden pass marks" not in iqac.get(f"/results/{w.offering.pk}/").content
    with college_context(w.college.id):
        papers.set_override(part, "2", "as used by the college", w.r.hod)
        assert results.overrides_of(w.offering) == []  # proposed, not approved: not shown
        papers.decide_override(part, w.r.iqac, approve=True)
    page = iqac.get(f"/results/{w.offering.pk}/").content.decode()
    assert (
        "Overridden pass marks" in page
        and "INT1 part 1a: pass mark 2 (as used by the college)" in page
    )


def test_the_target_proposal_follows_the_rule_and_is_never_applied(db: None, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    w = make_wf_env()
    with college_context(w.college.id):
        run = results.calculate(w.offering, w.programme)
        assert results.proposed_target(run) is None  # the default rule is manual
        config = results._config_of(run)

        def with_rule(rule: ReviseRule):  # type: ignore[no-untyped-def]
            return config.model_copy(
                update={"targets": config.targets.model_copy(update={"revise": rule})}
            )

        revised = with_rule(ReviseRule(rule="add_points", value="0.1"))
        monkeypatch.setattr(results, "_config_of", lambda _run: revised)
        proposal = results.proposed_target(run)
        assert (proposal.current, proposal.proposed) == ("2.2", "2.3")  # met: raised by 0.1
        revised = with_rule(ReviseRule(rule="add_points", value="0.1", if_not_met="lower"))
        monkeypatch.setattr(results, "_config_of", lambda _run: revised)
        run.outputs["course"]["attained"] = False
        assert results.proposed_target(run).proposed == "2.1"
        assert outcomes.Target.objects.get(offering=w.offering).value == D("2.2")  # untouched


# editing observations and plans ---------------------------------------------------------------
def test_observations_and_plans_can_be_edited_by_those_who_may_and_the_log_keeps_both(
    committed_db: None,
) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        observation = quality.add_observation(w.offering, "CO1 is weak", w.r.hod)
        plan = quality.add_plan(w.offering, "Add a tutorial", w.r.hod)
        quality.edit_observation(observation, "CO1 is weak in section B", w.r.hod)
        quality.edit_plan(plan, "Add two tutorials", None, w.r.hod)
        observation.refresh_from_db()
        plan.refresh_from_db()
        assert observation.text == "CO1 is weak in section B" and plan.text == "Add two tutorials"
        updated = AuditEvent.objects.filter(action="quality.observation.updated").get()
        assert updated.before["text"] == "CO1 is weak"
        assert updated.after["text"] == "CO1 is weak in section B"
        with pytest.raises(PermissionDenied):
            quality.edit_observation(observation, "tampering", w.env.auditor)
        with pytest.raises(Exception, match="observation"):
            quality.edit_observation(observation, "   ", w.r.hod)
    hod = _login("a.hod")
    url = f"/quality/{w.offering.pk}/observation/{observation.pk}/edit/"
    assert hod.post(url, {"text": "Edited on the page"}).status_code == 302
    plan_url = f"/quality/{w.offering.pk}/plan/{plan.pk}/edit/"
    assert hod.post(plan_url, {"text": "Plan edited", "due_date": "2026-12-01"}).status_code == 302
    with college_context(w.college.id):
        assert Observation.objects.get(pk=observation.pk).text == "Edited on the page"
        edited = ActionPlan.objects.get(pk=plan.pk)
        assert edited.text == "Plan edited" and str(edited.due_date) == "2026-12-01"
    page = hod.get(f"/quality/{w.offering.pk}/").content.decode()
    assert "Edited on the page" in page and "Plan edited" in page
    auditor = _login("a.auditor")
    auditor.post(url, {"text": "auditor edit"})
    with college_context(w.college.id):
        assert Observation.objects.get(pk=observation.pk).text == "Edited on the page"
