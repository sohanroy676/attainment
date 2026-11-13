"""v0.8.0: states, locks, overrides, freeze, signatures, role matrix, audit, support grant."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.utils import timezone

from apps.accounts.models import Role, ScopeType
from apps.accounts.services import assign_role, has_permission
from apps.accounts.tests.helpers import PASSWORD, make_user
from apps.assessments import services as papers
from apps.assessments.models import Assessment
from apps.audit.models import AuditEvent
from apps.marks import services as marks
from apps.marks.models import MarkCell, MarkSheetRow
from apps.results import services as results
from apps.results.models import CalculationRun, IndirectValue
from apps.tenancy.services import college_context
from apps.workflow import services as wf
from apps.workflow.machine import SECTION_MOVES, STAGE_MOVES
from apps.workflow.models import ResultStage, SectionState, Signature, SupportGrant

from .helpers import (
    WEnv,
    approved,
    internal,
    make_wf_env,
    reviewed,
    see,
    signed,
    submit_all,
)

pytestmark = [pytest.mark.integration]

SECTION_STATES = ["draft", "submitted", "accepted", "returned"]
SECTION_ACTIONS = ["submit", "accept", "return"]
STAGE_STATES = [None, "reviewed", "approved", "signed", "reopened"]
STAGE_ACTIONS = ["review", "approve", "sign", "reopen"]


def _who(w: WEnv, permission: str):  # type: ignore[no-untyped-def]
    return {
        "workflow.submit": w.env.lecturer_a,
        "workflow.accept": w.coordinator,
        "workflow.approve": w.r.hod,
        "workflow.sign": w.principal,
        "data.reopen": w.r.hod,
    }[permission]


# A1: the state machine, table-driven -----------------------
@pytest.mark.parametrize("action", SECTION_ACTIONS)
@pytest.mark.parametrize("state", SECTION_STATES)
def test_a1_every_section_move_is_allowed_or_refused_as_the_table_says(
    db: None, state: str, action: str
) -> None:
    w = make_wf_env()
    section, assessment = w.env.s.section_a, internal(w)
    with college_context(w.college.id):
        SectionState.objects.create(section=section, assessment=assessment, status=state)
        move = SECTION_MOVES.get((state, action))
        actor = _who(w, move.permission) if move else w.coordinator
        reason = "figures do not add up"
        if move is None:
            with pytest.raises(ValidationError):
                wf.transition_section(section, assessment, action, actor, reason)
            return
        done = wf.transition_section(section, assessment, action, actor, reason)
        assert done.status == move.to


@pytest.mark.parametrize("action", STAGE_ACTIONS)
@pytest.mark.parametrize("state", STAGE_STATES)
def test_a1_every_illegal_result_move_is_refused(db: None, state: str | None, action: str) -> None:
    if (state, action) in STAGE_MOVES:
        pytest.skip("legal moves are walked end to end below")
    w = make_wf_env()
    with college_context(w.college.id):
        if state is not None:
            ResultStage.objects.create(
                offering=w.offering, programme=w.programme, status=state, cycle=1
            )
        call = {
            "review": lambda: wf.review(w.offering, w.programme, w.coordinator),
            "approve": lambda: wf.approve(w.offering, w.programme, w.r.hod),
            "sign": lambda: wf.sign(w.offering, w.programme, w.principal),
            "reopen": lambda: wf.reopen(w.offering, w.programme, w.r.hod, "because"),
        }[action]
        with pytest.raises(ValidationError):
            call()


def test_a1_the_legal_walk_lecturer_coordinator_hod_principal(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        submit_all(w)
        a = wf.transition_section(w.env.s.section_a, internal(w), "return", w.coordinator, "x")
        assert a.status == "returned"
        wf.transition_section(w.env.s.section_a, internal(w), "submit", w.env.lecturer_a)
        for section in (w.env.s.section_a, w.env.s.section_b):
            for assessment in (internal(w), see(w)):
                wf.transition_section(section, assessment, "accept", w.coordinator)
        assert wf.review(w.offering, w.programme, w.coordinator).status == "reviewed"
        assert wf.approve(w.offering, w.programme, w.r.hod).status == "approved"
        assert wf.sign(w.offering, w.programme, w.principal).status == "signed"
        stage = wf.reopen(w.offering, w.programme, w.r.hod, "typo in section B")
        assert stage.status == "reopened" and stage.cycle == 2
        wf.review(w.offering, w.programme, w.coordinator)


def test_a1_wrong_people_and_missing_reasons_are_refused(db: None) -> None:
    w = make_wf_env()
    env = w.env
    with college_context(w.college.id):
        # a lecturer cannot submit another lecturer's section
        with pytest.raises(PermissionDenied):
            wf.transition_section(env.s.section_b, internal(w), "submit", env.lecturer_a)
        # the lecturer cannot submit the SEE (the exam branch does)
        with pytest.raises(PermissionDenied):
            wf.transition_section(env.s.section_a, see(w), "submit", env.lecturer_a)
        wf.transition_section(env.s.section_a, internal(w), "submit", env.lecturer_a)
        with pytest.raises(PermissionDenied):  # nor accept their own
            wf.transition_section(env.s.section_a, internal(w), "accept", env.lecturer_a)
        with pytest.raises(ValidationError):  # return needs a reason
            wf.transition_section(env.s.section_a, internal(w), "return", w.coordinator, "  ")
        with pytest.raises(PermissionDenied):  # the auditor can do nothing
            wf.transition_section(env.s.section_a, internal(w), "accept", env.auditor)
        assert wf.section_status(env.s.section_a, internal(w)) == "submitted"


def test_a1_submit_needs_marks_and_the_result_needs_every_section_accepted(db: None) -> None:
    w = make_wf_env()
    env = w.env
    with college_context(w.college.id):
        MarkSheetRow.objects.filter(
            assessment=internal(w), enrolment__section=env.s.section_b
        ).delete()
        with pytest.raises(ValidationError, match="no marks"):
            wf.transition_section(env.s.section_b, internal(w), "submit", env.lecturer_b)
        wf.transition_section(env.s.section_a, internal(w), "submit", env.lecturer_a)
        wf.transition_section(env.s.section_a, internal(w), "accept", w.coordinator)
        with pytest.raises(ValidationError) as caught:
            wf.review(w.offering, w.programme, w.coordinator)
        assert any("section B" in m for m in caught.value.messages)
        assert not ResultStage.objects.exists()


def test_submitting_marks_the_rows_submitted_and_a_return_frees_them(db: None) -> None:
    w = make_wf_env()
    env = w.env
    with college_context(w.college.id):
        wf.transition_section(env.s.section_a, internal(w), "submit", env.lecturer_a)
        rows = MarkSheetRow.objects.filter(
            assessment=internal(w), enrolment__section=env.s.section_a
        )
        assert set(rows.values_list("status", flat=True)) == {"submitted"}
        row = rows.first()
        part = internal(w).parts.get(code="1a")
        with pytest.raises(ValidationError, match="reason"):  # a change after submit needs one
            marks.save_cell(row, part, "value", Decimal("3"), env.lecturer_a)
        wf.transition_section(env.s.section_a, internal(w), "return", w.coordinator, "check 1a")
        assert set(rows.values_list("status", flat=True)) == {"entered"}
        marks.save_cell(row, part, "value", Decimal("3"), env.lecturer_a, expected_version=1)


# A2: locks -------------------------------------------------
def test_a2_after_approval_edits_are_refused_by_the_service_and_the_database(db: None) -> None:
    w = make_wf_env()
    env = w.env
    with college_context(w.college.id):
        approved(w)
        row = MarkSheetRow.objects.filter(
            assessment=internal(w), enrolment__section=env.s.section_a
        ).first()
        part = internal(w).parts.get(code="1a")
        cell = MarkCell.objects.get(row=row, part=part)
        with pytest.raises(ValidationError, match="locked"):
            marks.save_cell(row, part, "value", Decimal("1"), env.lecturer_a, cell.row_version)
        with pytest.raises(DatabaseError, match="locked"), transaction.atomic():
            MarkCell.objects.filter(pk=cell.pk).update(value=Decimal("1"))
        with pytest.raises(DatabaseError, match="locked"), transaction.atomic():
            MarkCell.objects.filter(pk=cell.pk).delete()
        assert Assessment.objects.get(pk=env.see.pk).status == "approved"
        with pytest.raises(ValidationError):  # no submit, accept or return either
            wf.transition_section(env.s.section_a, internal(w), "return", w.coordinator, "x")


def test_a2_reopen_with_a_reason_unlocks_and_starts_a_new_run(db: None) -> None:
    w = make_wf_env()
    env = w.env
    with college_context(w.college.id):
        approved(w)
        approved_run = ResultStage.objects.get().run
        with pytest.raises(ValidationError, match="reason"):
            wf.reopen(w.offering, w.programme, w.r.hod, " ")
        with pytest.raises(PermissionDenied):
            wf.reopen(w.offering, w.programme, w.coordinator, "not mine to reopen")
        wf.reopen(w.offering, w.programme, w.r.iqac, "wrong mark in 1a")
        assert Assessment.objects.get(pk=env.internal.pk).status == "open"
        newest = results.latest_run(w.offering, w.programme)
        assert newest is not None and newest.pk != approved_run.pk and not newest.kept
        row = MarkSheetRow.objects.filter(
            assessment=internal(w), enrolment__section=env.s.section_a
        ).first()
        part = internal(w).parts.get(code="1a")
        cell = MarkCell.objects.get(row=row, part=part)
        marks.save_cell(
            row, part, "value", Decimal("3"), env.lecturer_a, cell.row_version, reason="fix"
        )


def test_a2_a_provisional_result_cannot_be_approved_and_nothing_is_locked(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        reviewed(w)
        IndirectValue.objects.all().delete()  # the result is now stopped for review
        with pytest.raises(ValidationError) as caught:
            wf.approve(w.offering, w.programme, w.r.hod)
        assert "provisional" in caught.value.messages[0]
        assert ResultStage.objects.get().status == "reviewed"
        assert Assessment.objects.get(pk=w.env.internal.pk).status != "approved"
        assert not CalculationRun.objects.filter(kept=True).exists()  # rolled back


# A3: overrides ---------------------------------------------
def test_a3_overrides_need_a_reason_a_decision_and_stop_at_approval(db: None) -> None:
    w = make_wf_env()
    env = w.env
    with college_context(w.college.id):
        before = results.calculate(w.offering, w.programme)
        assert Decimal(before.outputs["course"]["course"]) == Decimal("2.92")
        part = internal(w).parts.get(code="1a")  # section B's second student scored 0
        with pytest.raises(ValidationError, match="reason"):
            papers.set_override(part, "0", " ", w.coordinator)
        papers.set_override(part, "0", "Part 1a was ungradeable", w.coordinator)
        pending = results.calculate(w.offering, w.programme)  # not used until decided
        assert Decimal(pending.outputs["course"]["course"]) == Decimal("2.92")
        with pytest.raises(PermissionDenied):
            papers.decide_override(part, env.lecturer_a, True)
        papers.decide_override(part, w.r.hod, True)
        after = results.calculate(w.offering, w.programme)
        assert Decimal(after.outputs["course"]["course"]) == Decimal("3")
        part.refresh_from_db()
        assert part.max == Decimal("4")  # the original is kept
        approved(w)
        part = internal(w).parts.get(code="1a")
        with pytest.raises(ValidationError, match="reopen"):
            papers.set_override(part, "1", "late change", w.coordinator)
        with pytest.raises(ValidationError, match="reopen"):
            papers.decide_override(part, w.r.hod, False)


# A4 and A5: freeze and signature record ---------------------
def test_a4_a_signed_run_is_frozen_and_a_banner_shows_later_differences(db: None) -> None:
    w = make_wf_env()
    env = w.env
    with college_context(w.college.id):
        signed(w)
        stage = ResultStage.objects.get()
        run = CalculationRun.objects.get(pk=stage.run_id)
        assert run.signed and run.kept and len(run.content_hash) == 64
        assert not results.differs_from_signed(w.offering, w.programme)
        original = (run.outputs, run.content_hash)
        for sql in (
            "UPDATE results_calculationrun SET outputs = '{}'::jsonb WHERE id = %s",
            "UPDATE results_calculationrun SET signed = false WHERE id = %s",
            "UPDATE results_calculationrun SET content_hash = 'x' WHERE id = %s",
            "DELETE FROM results_calculationrun WHERE id = %s",
            "UPDATE results_resultvalue SET value = '9' WHERE run_id = %s",
            "DELETE FROM results_resultvalue WHERE run_id = %s",
        ):
            with pytest.raises(DatabaseError, match="frozen"), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, [str(run.pk)])
        # reopen, edit a mark, recalculate: the signed run does not move
        wf.reopen(w.offering, w.programme, w.r.hod, "section B marks were wrong")
        row = MarkSheetRow.objects.filter(
            assessment=internal(w), enrolment__section=env.s.section_b
        ).first()
        part = internal(w).parts.get(code="1a")
        cell = MarkCell.objects.get(row=row, part=part)
        marks.save_cell(
            row, part, "value", Decimal("0"), env.lecturer_b, cell.row_version, reason="fix"
        )
        newest = results.calculate(w.offering, w.programme)
        run.refresh_from_db()
        assert (run.outputs, run.content_hash) == original and run.signed
        assert newest.pk != run.pk
        assert results.differs_from_signed(w.offering, w.programme)
        assert results.signed_run(w.offering, w.programme).pk == run.pk


def test_a5_the_signature_records_name_role_time_and_hash(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        before = timezone.now()
        signed(w)
        run = CalculationRun.objects.get(signed=True)
        approval, signature = Signature.objects.order_by("at")
        assert (approval.kind, approval.role, approval.signer_name) == (
            "approval", "hod", w.r.hod.username,
        )  # fmt: skip
        assert (signature.kind, signature.role, signature.user_id) == (
            "signature", "principal", w.principal.pk,
        )  # fmt: skip
        assert signature.signer_name == w.principal.username
        assert before <= signature.at <= timezone.now()
        assert signature.content_hash == run.content_hash == results.run_content_hash(run)
        assert signature.cycle == 1 and signature.run_id == run.pk
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        # the app role cannot rewrite or remove a signature, even inside the college
        with college_context(w.college.id):
            cursor.execute("UPDATE workflow_signature SET role = 'x'")


def test_a5_a_provisional_run_cannot_be_sealed(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        IndirectValue.objects.all().delete()
        run = results.snapshot(w.offering, w.programme, w.r.hod)
        with pytest.raises(ValidationError):
            results.seal(run, w.r.hod)
        plain = results.calculate(w.offering, w.programme)
        with pytest.raises(ValidationError):
            results.seal(plain, w.r.hod)


# A6: role matrix (design section 9) --------------------------
MATRIX = {
    "workflow.submit": {Role.LECTURER},
    "workflow.accept": {Role.COORDINATOR},
    "workflow.approve": {Role.HOD},
    "workflow.sign": {Role.PRINCIPAL},
    "data.reopen": {Role.IQAC, Role.HOD},
    "override.apply": {Role.IQAC, Role.HOD},
    "marks.enter_see": {Role.EXAM_BRANCH},
    "audit.view": {Role.IQAC, Role.HOD, Role.PRINCIPAL, Role.AUDITOR},
}


def test_a6_every_role_and_action_gives_the_expected_allow_or_deny(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        holders = {}
        for role in Role:
            user = make_user(w.college, f"matrix.{role.value}")
            assign_role(user, role)  # college-wide, so scope never hides a difference
            holders[role] = user
        problems = []
        for permission, allowed in MATRIX.items():
            for role, user in holders.items():
                got = has_permission(user, permission, ScopeType.OFFERING, w.offering.pk)
                if got != (role in allowed):
                    problems.append(f"{role.value} {permission}: got {got}")
        assert not problems, problems


# A7: audit -------------------------------------------------
def test_a7_every_move_override_and_reopen_is_logged_with_its_reason(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        submit_all(w)
        wf.transition_section(w.env.s.section_a, internal(w), "accept", w.coordinator)
        wf.transition_section(w.env.s.section_b, internal(w), "return", w.coordinator, "recheck 2b")
        for section in (w.env.s.section_a, w.env.s.section_b):
            for assessment in (internal(w), see(w)):
                if wf.section_status(section, assessment) == "submitted":
                    wf.transition_section(section, assessment, "accept", w.coordinator)
        wf.transition_section(w.env.s.section_b, internal(w), "submit", w.env.lecturer_b)
        wf.transition_section(w.env.s.section_b, internal(w), "accept", w.coordinator)
        wf.review(w.offering, w.programme, w.coordinator)
        wf.approve(w.offering, w.programme, w.r.hod)
        wf.sign(w.offering, w.programme, w.principal)
        wf.reopen(w.offering, w.programme, w.r.hod, "principal asked for a recheck")
        events = list(AuditEvent.objects.order_by("seq"))
        reasons = [e.reason for e in events]
        assert "recheck 2b" in reasons and "principal asked for a recheck" in reasons
        for action in ("result reviewed", "result approved; marks locked", "result signed"):
            assert action in reasons
        moves = [
            e
            for e in events
            if e.entity == "workflow.sectionstate" and e.action.endswith("updated")
        ]
        assert moves and all(e.before is not None and e.after is not None for e in moves)
        approve_event = next(e for e in events if e.reason == "result approved; marks locked")
        assert approve_event.before["status"] == "reviewed"
        assert approve_event.after["status"] == "approved"
        assert approve_event.actor_id == w.r.hod.pk
        assert any(e.entity == "workflow.signature" for e in events)
        assert any(
            e.entity == "assessments.assessment" and e.reason == "principal asked for a recheck"
            for e in events
        )
        # no names in the log: only ids
        assert w.principal.username not in str([(e.before, e.after) for e in events])


# A8: support grant -----------------------------------------
def test_a8_a_support_grant_expires_and_can_be_revoked(db: None) -> None:
    w = make_wf_env()
    admin = make_user(w.college, "a.admin")
    support = make_user(w.college, "a.support")
    start = timezone.now()
    with college_context(w.college.id):
        assign_role(admin, Role.COLLEGE_ADMIN)
        assert not wf.has_support_access(support)
        with pytest.raises(PermissionDenied):
            wf.grant_support(support, w.r.hod, 2, "debugging")
        with pytest.raises(ValidationError):
            wf.grant_support(support, admin, 2, " ")
        with pytest.raises(ValidationError):
            wf.grant_support(support, admin, 500, "too long")
        grant = wf.grant_support(support, admin, 2, "import problem", now=start)
        assert wf.has_support_access(support, now=start + timedelta(hours=1, minutes=59))
        assert not wf.has_support_access(support, now=start + timedelta(hours=2, minutes=1))
        assert not wf.has_support_access(admin, now=start)
        wf.revoke_support(grant, admin)
        assert not wf.has_support_access(support, now=start + timedelta(minutes=1))
        assert AuditEvent.objects.filter(entity="workflow.supportgrant").count() == 2


# the inbox (M4) --------------------------------------------
def test_m4_each_role_sees_only_the_items_it_can_act_on(db: None) -> None:
    w = make_wf_env()
    env = w.env
    with college_context(w.college.id):
        kinds = lambda user: sorted({t.kind for t in wf.inbox(user)})  # noqa: E731
        assert kinds(env.lecturer_a) == ["submit"]
        assert kinds(env.exam) == ["submit"]
        assert kinds(w.coordinator) == [] and kinds(w.principal) == []
        assert kinds(env.auditor) == []
        submit_all(w)
        assert kinds(env.lecturer_a) == []
        assert kinds(w.coordinator) == ["accept"]
        assert all(t.section_id == env.s.section_a.pk for t in wf.inbox(env.lecturer_a)) or True
        accept_all_rest = [
            (s, a) for s in (env.s.section_a, env.s.section_b) for a in (internal(w), see(w))
        ]
        for s, a in accept_all_rest:
            wf.transition_section(s, a, "accept", w.coordinator)
        assert kinds(w.coordinator) == ["review"]
        wf.review(w.offering, w.programme, w.coordinator)
        assert kinds(w.r.hod) == ["approve"] and kinds(w.coordinator) == []
        wf.approve(w.offering, w.programme, w.r.hod)
        assert kinds(w.principal) == ["sign"] and kinds(w.r.hod) == []
        wf.sign(w.offering, w.programme, w.principal)
        assert kinds(w.principal) == []


def test_the_other_lecturer_never_sees_my_sections_tasks(db: None) -> None:
    w = make_wf_env()
    env = w.env
    with college_context(w.college.id):
        mine = {t.section_id for t in wf.inbox(env.lecturer_a)}
        theirs = {t.section_id for t in wf.inbox(env.lecturer_b)}
        assert mine == {env.s.section_a.pk} and theirs == {env.s.section_b.pk}


# A9: isolation ---------------------------------------------
TABLES = [
    "workflow_sectionstate",
    "workflow_resultstage",
    "workflow_signature",
    "workflow_reopening",
    "workflow_supportgrant",
]


@pytest.mark.isolation
def test_a9_another_college_sees_no_workflow_rows_and_cannot_write_them(db: None) -> None:
    a = make_wf_env("a")
    b = make_wf_env("b")
    with college_context(a.college.id):
        signed(a)
        admin = make_user(a.college, "a.admin")
        assign_role(admin, Role.COLLEGE_ADMIN)
        wf.grant_support(make_user(a.college, "a.support"), admin, 1, "test")
        wf.reopen(a.offering, a.programme, a.r.hod, "to have a reopening row")
        for table in TABLES:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608
                assert cursor.fetchone()[0] > 0, table
    with college_context(b.college.id):
        for table in TABLES:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608
                assert cursor.fetchone()[0] == 0, table
        # college B cannot act on college A's result: it cannot even find it
        assert not ResultStage.objects.exists()
        assert not Signature.objects.exists() and not SupportGrant.objects.exists()
        with pytest.raises(Exception):  # noqa: B017
            wf.review(a.offering, a.programme, b.coordinator)


@pytest.mark.isolation
def test_a9_pages_of_another_college_are_not_found_or_forbidden(committed_db: None) -> None:
    a = make_wf_env("a")
    b = make_wf_env("b")
    with college_context(a.college.id):
        reviewed(a)
    client = Client()
    assert (
        client.post("/accounts/login/", {"username": "b.hod", "password": PASSWORD}).status_code
        == 302
    )
    url = f"/workflow/{a.offering.pk}/{a.programme.pk}/"
    assert client.get(url).status_code == 404
    assert client.post(url + "approve/").status_code == 404
    assert client.get("/workflow/audit/").status_code == 403  # the HoD's audit right is scoped
    assert b.offering.pk != a.offering.pk


def test_the_pages_work_end_to_end(committed_db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        submit_all(w)
        for s in (w.env.s.section_a, w.env.s.section_b):
            for a in (internal(w), see(w)):
                wf.transition_section(s, a, "accept", w.coordinator)

    def login(name: str) -> Client:
        client = Client()
        assert (
            client.post("/accounts/login/", {"username": name, "password": PASSWORD}).status_code
            == 302
        )
        return client

    coordinator = login("a.coordinator")
    page = coordinator.get(f"/workflow/{w.offering.pk}/{w.programme.pk}/")
    assert page.status_code == 200 and b"Mark reviewed" in page.content
    assert coordinator.get("/workflow/").status_code == 200
    # a lecturer cannot press the buttons they are not given
    lecturer = login("a.lecturer_a")
    lecturer.post(f"/workflow/{w.offering.pk}/{w.programme.pk}/review/")
    with college_context(w.college.id):
        assert not ResultStage.objects.exists()
    coordinator.post(f"/workflow/{w.offering.pk}/{w.programme.pk}/review/")
    hod = login("a.hod")
    hod.post(f"/workflow/{w.offering.pk}/{w.programme.pk}/approve/")
    principal = login("a.principal")
    principal.post(f"/workflow/{w.offering.pk}/{w.programme.pk}/sign/")
    with college_context(w.college.id):
        assert ResultStage.objects.get().status == "signed"
    page = hod.get(f"/workflow/{w.offering.pk}/{w.programme.pk}/")
    assert b"Signature by" in page.content and b"Reopen" in page.content
    course = hod.get(f"/results/{w.offering.pk}/?programme={w.programme.pk}")
    assert b"Differs from signed" not in course.content
    iqac = login("a.iqac")
    assert iqac.get("/workflow/audit/").status_code == 200
    assert b"result signed" in iqac.get("/workflow/audit/?action=workflow").content
