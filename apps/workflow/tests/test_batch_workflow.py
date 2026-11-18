"""v0.9.0: batch sign-off (prepared, HoD, principal) and the freeze (synthetic data only)."""

from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client

from apps.accounts.tests.helpers import PASSWORD
from apps.marks import services as marks
from apps.marks.models import MarkCell
from apps.outcomes import services as outcomes
from apps.outcomes.models import ProgrammeOutcome
from apps.results import services as results
from apps.results.models import BatchRun
from apps.tenancy.services import college_context
from apps.workflow import services as wf
from apps.workflow.machine import BATCH_MOVES
from apps.workflow.models import BatchReopening, BatchSignature, BatchStage

from .helpers import internal, make_wf_env, signed

pytestmark = [pytest.mark.integration]


def _ready(w):  # type: ignore[no-untyped-def]
    """A signed course with targets and indirect values, so the batch can be prepared."""
    batch = w.env.s.batch
    with college_context(w.college.id):
        for code in ("PO1", "PO2"):
            po = ProgrammeOutcome.objects.get(programme=w.programme, code=code)
            outcomes.set_target("2.5", outcome=po, batch=batch)
        results.set_batch_indirect(batch, {"PO1": "3", "PO2": "3"}, "test", w.r.iqac)
        signed(w)
    return batch


def _signed_batch(w):  # type: ignore[no-untyped-def]
    batch = _ready(w)
    with college_context(w.college.id):
        wf.prepare_batch(batch, w.r.iqac)
        wf.approve_batch(batch, w.r.hod)
        wf.sign_batch(batch, w.principal)
    return batch


def test_a_batch_goes_prepared_approved_signed_and_the_records_say_who(db: None) -> None:
    w = make_wf_env()
    batch = _ready(w)
    with college_context(w.college.id):
        stage = wf.prepare_batch(batch, w.r.iqac)
        assert stage.status == "prepared" and stage.run.kept and not stage.run.signed
        wf.approve_batch(batch, w.r.hod)
        stage = wf.sign_batch(batch, w.principal)
        run = BatchRun.objects.get(pk=stage.run_id)
        assert stage.status == "signed" and run.signed
        assert run.content_hash == results.batch_content_hash(run)
        approval, signature = BatchSignature.objects.order_by("at")
        assert (approval.kind, approval.role, approval.signer_name) == (
            "approval", "hod", w.r.hod.username,
        )  # fmt: skip
        assert (signature.kind, signature.role) == ("signature", "principal")
        assert approval.content_hash == signature.content_hash == run.content_hash
        assert approval.run_id == signature.run_id == run.pk and signature.cycle == 1


def test_every_move_outside_the_table_is_refused(db: None) -> None:
    w = make_wf_env()
    batch = _ready(w)
    actors = {
        "prepare": w.r.iqac, "approve": w.r.hod, "sign": w.principal, "reopen": w.r.iqac,
    }  # fmt: skip
    with college_context(w.college.id):
        for action in ("approve", "sign", "reopen"):  # nothing prepared yet
            with pytest.raises(ValidationError, match="not yet prepared"):
                _act(action, batch, actors[action])
        wf.prepare_batch(batch, w.r.iqac)
        for action in ("sign", "reopen"):
            with pytest.raises(ValidationError, match="prepared"):
                _act(action, batch, actors[action])
        wf.approve_batch(batch, w.r.hod)
        for action in ("prepare", "approve"):
            with pytest.raises(ValidationError, match="approved"):
                _act(action, batch, actors[action])
        wf.sign_batch(batch, w.principal)
        for action in ("prepare", "approve", "sign"):
            with pytest.raises(ValidationError, match="signed"):
                _act(action, batch, actors[action])
    assert {("prepared", "prepare"), ("approved", "sign")} <= set(BATCH_MOVES)


def _act(action, batch, actor):  # type: ignore[no-untyped-def]
    if action == "reopen":
        return wf.reopen_batch(batch, actor, "a reason")
    return {"prepare": wf.prepare_batch, "approve": wf.approve_batch, "sign": wf.sign_batch}[
        action
    ](batch, actor)


def test_each_step_needs_the_right_role(db: None) -> None:
    w = make_wf_env()
    batch = _ready(w)
    env = w.env
    with college_context(w.college.id):
        for who in (env.lecturer_a, w.coordinator, w.r.hod, w.principal):
            with pytest.raises(PermissionDenied):
                wf.prepare_batch(batch, who)
        wf.prepare_batch(batch, w.r.iqac)
        for who in (w.r.iqac, w.principal, w.coordinator, env.lecturer_a):
            with pytest.raises(PermissionDenied):
                wf.approve_batch(batch, who)
        wf.approve_batch(batch, w.r.hod)
        for who in (w.r.iqac, w.r.hod, w.coordinator):
            with pytest.raises(PermissionDenied):
                wf.sign_batch(batch, who)
        for who in (w.principal, w.coordinator, env.lecturer_a):
            with pytest.raises(PermissionDenied):
                wf.reopen_batch(batch, who, "needs a change")


def test_an_incomplete_batch_cannot_be_prepared(db: None) -> None:
    w = make_wf_env()
    batch = w.env.s.batch  # no targets, no indirect values, nothing signed
    with college_context(w.college.id):
        with pytest.raises(ValidationError) as caught:
            wf.prepare_batch(batch, w.r.iqac)
        assert any("left out" in m or "No target" in m for m in caught.value.messages)
        assert not BatchStage.objects.exists()


def test_a9_a_signed_batch_does_not_change_when_a_course_run_changes(db: None) -> None:
    w = make_wf_env()
    batch = _signed_batch(w)
    env = w.env
    with college_context(w.college.id):
        run = results.signed_batch_run(batch)
        original = (run.outputs, run.courses, run.content_hash)
        assert not results.batch_differs_from_signed(batch)
        for sql in (
            "UPDATE results_batchrun SET outputs = '{}'::jsonb WHERE id = %s",
            "UPDATE results_batchrun SET courses = '[]'::jsonb WHERE id = %s",
            "UPDATE results_batchrun SET signed = false WHERE id = %s",
            "UPDATE results_batchrun SET content_hash = 'x' WHERE id = %s",
            "DELETE FROM results_batchrun WHERE id = %s",
        ):
            with (
                pytest.raises(DatabaseError, match="frozen"),
                transaction.atomic(),
                connection.cursor() as cursor,
            ):
                cursor.execute(sql, [str(run.pk)])
        # reopen the course, change a mark, recalculate everything: the signed batch holds
        wf.reopen(w.offering, w.programme, w.r.hod, "section B marks were wrong")
        part = internal(w).parts.get(code="1a")
        cell = (
            MarkCell.objects.filter(
                row__assessment=internal(w), row__enrolment__section=env.s.section_b, part=part
            )
            .exclude(value=0)
            .first()
        )
        marks.save_cell(
            cell.row, part, "value", Decimal("0"), env.lecturer_b, cell.row_version, reason="fix"
        )
        results.calculate(w.offering, w.programme)
        # the course's signed run still rules, so a fresh batch run holds the same numbers
        later = results.calculate_batch(batch, w.r.iqac, include_unsigned=True)
        run.refresh_from_db()
        assert (run.outputs, run.courses, run.content_hash) == original and run.signed
        assert later.pk != run.pk and results.signed_batch_run(batch).pk == run.pk
        assert later.courses == run.courses and later.input_hash == run.input_hash
        assert not results.batch_differs_from_signed(batch)
        # a signed course run is what the batch uses, even after its own result moved on
        assert results.differs_from_signed(w.offering, w.programme)


def test_reopening_a_batch_needs_a_reason_and_starts_a_new_cycle(db: None) -> None:
    w = make_wf_env()
    batch = _signed_batch(w)
    with college_context(w.college.id):
        with pytest.raises(ValidationError, match="reason"):
            wf.reopen_batch(batch, w.r.hod, "  ")
        stage = wf.reopen_batch(batch, w.r.hod, "the PO9 comparison needs another look")
        assert stage.status == "reopened" and stage.cycle == 2 and stage.run_id is None
        reopening = BatchReopening.objects.get()
        assert (reopening.from_cycle, reopening.from_status) == (1, "signed")
        assert BatchSignature.objects.count() == 2  # the old signatures stay
        assert results.signed_batch_run(batch) is not None
        again = wf.prepare_batch(batch, w.r.iqac)  # a second cycle, a new kept run
        assert again.status == "prepared" and again.run_id != results.signed_batch_run(batch).pk
        wf.approve_batch(batch, w.r.hod)
        wf.sign_batch(batch, w.principal)
        assert BatchSignature.objects.filter(cycle=2).count() == 2
        assert BatchRun.objects.filter(signed=True).count() == 2


def test_signatures_cannot_be_rewritten_by_the_app_role(db: None) -> None:
    w = make_wf_env()
    _signed_batch(w)
    for sql in (
        "UPDATE workflow_batchsignature SET role = 'x'",
        "DELETE FROM workflow_batchsignature",
        "UPDATE workflow_batchreopening SET reason = 'x'",
    ):
        with (
            pytest.raises(DatabaseError),
            transaction.atomic(),
            college_context(w.college.id),
            connection.cursor() as cursor,
        ):
            cursor.execute(sql)


def test_the_batch_steps_are_in_the_audit_log(db: None) -> None:
    from apps.audit.models import AuditEvent

    w = make_wf_env()
    _signed_batch(w)
    with college_context(w.college.id):
        entities = {e.entity for e in AuditEvent.objects.all()}
        assert {"workflow.batchstage", "workflow.batchsignature", "results.batchrun"} <= entities
        reasons = set(
            AuditEvent.objects.filter(entity="workflow.batchstage").values_list("reason", flat=True)
        )
        assert {"batch result prepared", "batch result approved", "batch result signed"} <= reasons


def _login(username: str) -> Client:
    client = Client()
    assert (
        client.post("/accounts/login/", {"username": username, "password": PASSWORD}).status_code
        == 302
    )
    return client


def test_the_batch_approval_page_walks_the_steps(committed_db: None) -> None:
    w = make_wf_env()
    batch = _ready(w)
    url = f"/workflow/batch/{batch.pk}/"
    iqac, hod, principal = _login("a.iqac"), _login("a.hod"), _login("a.principal")
    assert "Not yet prepared" in iqac.get(url).content.decode()
    assert iqac.post(url + "approve/").status_code == 302  # refused with a message, not a crash
    assert iqac.post(url + "prepare/").status_code == 302
    assert "Prepared" in hod.get(url).content.decode()
    assert "Approve" in hod.get(url).content.decode()
    assert "Approve" not in iqac.get(url).content.decode().replace("Approval", "")
    hod.post(url + "approve/")
    principal.post(url + "sign/")
    page = principal.get(url).content.decode()
    assert "Signed (cycle 1)" in page and "principal" in page and "hod" in page
    assert _login("a.lecturer_a").get(url).status_code == 403
    assert _login("a.lecturer_a").post(url + "prepare/").status_code == 302
    with college_context(w.college.id):
        assert BatchStage.objects.get().status == "signed"
    assert hod.post(url + "nonsense/").status_code == 404
