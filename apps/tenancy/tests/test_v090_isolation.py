"""v0.9.0 A12: another college reaches nothing of this college's batch, comparison, gap, sign-off,
import or quality pages, and its requests change nothing (synthetic data only)."""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client

from apps.academics.models import AcademicYear, CourseOffering, Section, Term
from apps.accounts.models import Role, ScopeType
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import PASSWORD, make_user
from apps.imports.models import ImportBatch
from apps.outcomes import services as outcomes
from apps.outcomes.models import ProgrammeOutcome
from apps.quality import services as quality
from apps.quality.models import ActionPlan, ActionTaken, Evidence, Observation
from apps.results import services as results
from apps.results.models import BatchIndirect, BatchRun, HistoricResult
from apps.tenancy.services import college_context
from apps.workflow import services as wf
from apps.workflow.models import BatchReopening, BatchSignature, BatchStage
from apps.workflow.tests.helpers import make_wf_env, signed

pytestmark = [pytest.mark.isolation, pytest.mark.integration]

PDF = b"%PDF-1.4\n%synthetic\n"
NEW_TABLES = (
    "results_batchindirect",
    "results_batchrun",
    "results_historicresult",
    "workflow_batchstage",
    "workflow_batchsignature",
    "workflow_batchreopening",
    "quality_observation",
    "quality_actionplan",
    "quality_actiontaken",
    "quality_evidence",
)
COUNTED = (
    BatchIndirect, BatchRun, HistoricResult, BatchStage, BatchSignature, BatchReopening,
    ImportBatch, Observation, ActionPlan, ActionTaken, Evidence,
)  # fmt: skip


def _build():  # type: ignore[no-untyped-def]
    """College A with everything the new pages show: a signed batch, history, a plan and proof."""
    a = make_wf_env("a")
    batch = a.env.s.batch
    with college_context(a.college.id):
        for code in ("PO1", "PO2"):
            po = ProgrammeOutcome.objects.get(programme=a.programme, code=code)
            outcomes.set_target("2.5", outcome=po, batch=batch)
        results.set_batch_indirect(batch, {"PO1": "3", "PO2": "3"}, "test", a.r.iqac)
        signed(a)
        wf.prepare_batch(batch, a.r.iqac)
        wf.approve_batch(batch, a.r.hod)
        wf.sign_batch(batch, a.principal)
        year = AcademicYear.objects.create(
            label="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31)
        )
        later = CourseOffering.objects.create(
            course=a.offering.course, term=Term.objects.create(academic_year=year, number=6)
        )
        section = Section.objects.create(
            offering=later, name="A", programme=a.programme, batch=batch
        )
        teacher = make_user(a.college, "a.lecturer2")
        assign_role(teacher, Role.LECTURER, ScopeType.SECTION, section.pk)
        plan = quality.add_plan(a.offering, "A plan", a.r.hod)
        quality.add_observation(a.offering, "An observation", a.r.hod)
        action = quality.add_action(plan, later, "Done", date(2026, 8, 1), teacher)
        proof = quality.add_evidence(action, [("proof.pdf", PDF)], teacher)[0]
    return a, batch, later, plan, proof


def _login(username: str) -> Client:
    client = Client()
    response = client.post("/accounts/login/", {"username": username, "password": PASSWORD})
    assert response.status_code == 302
    return client


def _urls(batch, offering, later, plan, proof):  # type: ignore[no-untyped-def]
    return {
        "get": [
            f"/results/batch/{batch.pk}/",
            f"/results/batch/{batch.pk}/inputs/",
            f"/results/batch/{batch.pk}/compare/",
            f"/results/batch/{batch.pk}/gaps/",
            f"/results/{offering.pk}/gaps/",
            f"/workflow/batch/{batch.pk}/",
            f"/imports/historic/{batch.pk}/",
            f"/quality/{offering.pk}/",
            f"/quality/{later.pk}/",
            f"/quality/evidence/{proof.pk}/",
        ],
        "post": [
            (f"/results/batch/{batch.pk}/", {"include_unsigned": "1"}),
            (f"/results/batch/{batch.pk}/", {"snapshot": "1"}),
            (f"/results/batch/{batch.pk}/inputs/", {"target:PO1": "9", "indirect:PO1": "9"}),
            (f"/workflow/batch/{batch.pk}/prepare/", {}),
            (f"/workflow/batch/{batch.pk}/approve/", {}),
            (f"/workflow/batch/{batch.pk}/sign/", {}),
            (f"/workflow/batch/{batch.pk}/reopen/", {"reason": "intrusion"}),
            (
                f"/imports/historic/{batch.pk}/",
                {"file": SimpleUploadedFile("x.csv", b"Outcome,Total\nPO1,1\n")},
            ),
            (f"/quality/{offering.pk}/observation/", {"text": "intrusion"}),
            (f"/quality/{offering.pk}/plan/", {"text": "intrusion"}),
            (
                f"/quality/{later.pk}/action/{plan.pk}/",
                {
                    "text": "intrusion",
                    "done_on": "2026-08-01",
                    "files": SimpleUploadedFile("x.pdf", PDF),
                },
            ),  # fmt: skip
        ],
    }


def _snapshot(college_id):  # type: ignore[no-untyped-def]
    with college_context(college_id):
        return {model.__name__: model.objects.count() for model in COUNTED}


def test_a12_another_college_reaches_none_of_the_new_pages_and_changes_nothing(
    committed_db: None,
) -> None:
    a, batch, later, plan, proof = _build()
    b = make_wf_env("b")  # a second college with its own IQAC, HoD and principal
    urls = _urls(batch, a.offering, later, plan, proof)
    before = _snapshot(a.college.id)
    assert before["BatchRun"] >= 1 and before["Evidence"] == 1  # there is something to protect
    for username in ("b.iqac", "b.hod", "b.principal", "b.lecturer_a"):
        client = _login(username)
        for url in urls["get"]:
            response = client.get(url)
            assert response.status_code == 404, (username, url, response.status_code)
        for url, data in urls["post"]:
            response = client.post(url, data)
            assert response.status_code == 404, (username, url, response.status_code)
    assert _snapshot(a.college.id) == before  # not one row added, changed or removed
    with college_context(b.college.id):
        assert {m.__name__: m.objects.count() for m in COUNTED} == dict.fromkeys(
            (m.__name__ for m in COUNTED), 0
        )


def test_a12_anyone_not_logged_in_is_sent_to_log_in(committed_db: None) -> None:
    a, batch, later, plan, proof = _build()
    urls = _urls(batch, a.offering, later, plan, proof)
    before = _snapshot(a.college.id)
    anonymous = Client()
    for url in urls["get"]:
        response = anonymous.get(url)
        assert response.status_code == 302 and "/accounts/login/" in response["Location"], url
    for url, data in urls["post"]:
        response = anonymous.post(url, data)
        assert response.status_code == 302 and "/accounts/login/" in response["Location"], url
    assert _snapshot(a.college.id) == before


def test_a12_a_user_of_this_college_without_a_role_is_refused(committed_db: None) -> None:
    a, batch, later, plan, proof = _build()
    urls = _urls(batch, a.offering, later, plan, proof)
    before = _snapshot(a.college.id)
    make_user(a.college, "a.stranger")  # a user of this college who holds no role at all
    client = _login("a.stranger")
    for url in urls["get"]:
        assert client.get(url).status_code == 403, url
    for url, data in urls["post"]:
        response = client.post(url, data)
        assert response.status_code in (302, 403), url  # a refusal message or a 403
    assert _snapshot(a.college.id) == before


def test_a12_every_new_table_has_row_level_security_forced_on(db: None) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = ANY(%s)",
            [list(NEW_TABLES)],
        )
        found = {name: (secure, forced) for name, secure, forced in cursor.fetchall()}
    assert set(found) == set(NEW_TABLES)
    assert all(flags == (True, True) for flags in found.values()), found
