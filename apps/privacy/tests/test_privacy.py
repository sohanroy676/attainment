"""v0.11.0 A8: the retention tool and the privacy exports (synthetic data only)."""

import csv
import io
import json
from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from apps.accounts.models import Role
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import PASSWORD, make_user
from apps.audit import services as audit
from apps.audit.models import AuditEvent
from apps.imports.models import ImportBatch
from apps.privacy import services
from apps.privacy.models import RetentionNotice
from apps.results import services as results
from apps.roster import services as roster
from apps.roster.models import Student, StudentIdentifier
from apps.tenancy.services import college_context
from apps.workflow.tests.helpers import make_wf_env

pytestmark = [pytest.mark.integration]

BATCH_END = 2025
LONG_AFTER = date(BATCH_END + 5, 6, 1)  # the retention period (5 years) has ended


def _env():  # type: ignore[no-untyped-def]
    w = make_wf_env()
    with college_context(w.college.id):
        for enrolment in w.env.enrolments_a + w.env.enrolments_b:
            roster.join_batch(enrolment.student, w.env.s.batch)
    return w


def _ids(w):  # type: ignore[no-untyped-def]
    return [e.student_id for e in w.env.enrolments_a + w.env.enrolments_b]


def test_a8_nobody_is_listed_while_the_batch_is_inside_the_retention_period(db: None) -> None:
    w = _env()
    with college_context(w.college.id):
        assert services.retention_list(date(BATCH_END + 4, 12, 31)) == []
        assert len(services.retention_list(LONG_AFTER)) == 7


def test_a8_a_student_with_no_batch_is_never_listed(db: None) -> None:
    w = make_wf_env()  # no batch memberships
    with college_context(w.college.id):
        assert services.retention_list(LONG_AFTER) == []


def test_a8_notice_then_wait_then_anonymise_and_the_chain_stays_valid(db: None) -> None:
    w = _env()
    with college_context(w.college.id):
        results.calculate(w.offering, w.programme)
        before = results.latest_run(w.offering, w.programme).outputs
        names = set(Student.objects.values_list("name", flat=True))
        assert services.notify(LONG_AFTER) == 7
        assert services.notify(LONG_AFTER) == 0  # idempotent: nobody is noticed twice
        assert {r.state for r in services.retention_list(LONG_AFTER)} == {"waiting"}
        assert services.anonymise_due(LONG_AFTER + timedelta(days=29)) == 0  # still waiting
        assert set(Student.objects.values_list("name", flat=True)) == names
        done = services.anonymise_due(LONG_AFTER + timedelta(days=30))
        assert done == 7
        assert set(Student.objects.values_list("name", flat=True)) == {roster.ANONYMISED_NAME}
        values = list(StudentIdentifier.objects.values_list("value", flat=True))
        assert values and all(v.startswith("ANON-") for v in values)
        assert len(set(values)) == len(values)
        assert services.retention_list(LONG_AFTER + timedelta(days=60)) == []
        assert audit.verify_chain()  # the log never held names, so nothing it hashed changed
        text = json.dumps(list(AuditEvent.objects.values_list("before", "after")), default=str)
        assert "Student A1" not in text
        # results are unchanged: marks and enrolments stayed
        results.calculate(w.offering, w.programme)
        assert results.latest_run(w.offering, w.programme).outputs == before


def test_a8_anonymising_purges_stored_upload_files_but_keeps_the_record(db: None) -> None:
    w = _env()
    section = w.env.s.section_a
    with college_context(w.college.id):
        upload = ImportBatch.objects.create(
            kind="roster", status="committed", filename="roster.csv", file_sha256="0" * 64,
            section=section, file_content=b"roll_no,name\n1,Real Name\n",
            payload={"rows": [{"roll_no": "1", "name": "Real Name"}]},
        )  # fmt: skip
        services.notify(LONG_AFTER)
        services.anonymise_due(LONG_AFTER + timedelta(days=31))
        upload.refresh_from_db()
        assert upload.file_content is None and upload.payload == {}
        assert upload.file_sha256 == "0" * 64 and upload.filename == "roster.csv"


def test_a8_an_anonymised_student_cannot_be_exported(db: None) -> None:
    w = _env()
    with college_context(w.college.id):
        student = Student.objects.get(pk=w.env.enrolments_a[0].student_id)
        services.notify(LONG_AFTER)
        services.anonymise_due(LONG_AFTER + timedelta(days=31))
        with pytest.raises(ValidationError, match="anonymised"):
            services.student_export(student)


def test_the_student_export_holds_identity_marks_and_history(db: None) -> None:
    w = _env()
    with college_context(w.college.id):
        student = Student.objects.get(pk=w.env.enrolments_a[0].student_id)
        data = services.student_export(student, w.r.iqac)
        assert data["name"] == student.name and data["identifiers"][0]["value"]
        assert data["batches"][0]["batch"] == "2021-25"
        assert data["enrolments"] and data["marks"]
        cells = [c for row in data["marks"] for c in row["cells"]]
        assert cells and all("history" in c for c in cells)
        assert AuditEvent.objects.filter(action="student.exported").count() == 1
        other = Student.objects.exclude(pk=student.pk)[0]
        assert other.name not in json.dumps(data, default=str)  # nobody else's data


def test_the_command_lists_notifies_and_anonymises_one_college(committed_db: None) -> None:
    w = _env()
    college = str(w.college.id)
    out = io.StringIO()
    call_command("retention", "list", "--college", college, "--today", str(LONG_AFTER), stdout=out)
    assert out.getvalue().count("not notified") == 7
    out = io.StringIO()
    call_command(
        "retention", "notify", "--college", college, "--today", str(LONG_AFTER), stdout=out
    )
    assert "7 student(s) put on notice" in out.getvalue()
    later = str(LONG_AFTER + timedelta(days=30))
    out = io.StringIO()
    call_command("retention", "anonymise", "--all", "--today", later, stdout=out)
    assert "7 anonymised" in out.getvalue()
    with college_context(w.college.id):
        assert RetentionNotice.objects.filter(anonymised_on__isnull=False).count() == 7
    with pytest.raises(CommandError):
        call_command("retention", "list")


def test_the_pages_need_privacy_manage_and_the_export_is_audited(committed_db: None) -> None:
    w = _env()
    admin = make_user(w.college, "a.admin")
    with college_context(w.college.id):
        assign_role(admin, Role.COLLEGE_ADMIN)
        student_id = w.env.enrolments_a[0].student_id
    client = Client()
    client.post("/accounts/login/", {"username": "a.admin", "password": PASSWORD})
    assert client.get("/privacy/retention/").status_code == 200
    response = client.get(f"/privacy/student/{student_id}/export.json")
    assert response.status_code == 200 and json.loads(response.content)["marks"]
    other = Client()
    other.post("/accounts/login/", {"username": "a.iqac", "password": PASSWORD})
    assert other.get("/privacy/retention/").status_code == 403
    assert other.get(f"/privacy/student/{student_id}/export.json").status_code == 403
    with college_context(w.college.id):
        assert AuditEvent.objects.filter(action="student.exported").count() == 1


def test_retention_notices_are_isolated_between_colleges(committed_db: None) -> None:
    a = _env()
    b = make_wf_env("b")
    with college_context(b.college.id):
        for enrolment in b.env.enrolments_a:
            roster.join_batch(enrolment.student, b.env.s.batch)
    with college_context(a.college.id):
        services.notify(LONG_AFTER)
        assert RetentionNotice.objects.count() == 7
    with college_context(b.college.id):
        assert RetentionNotice.objects.count() == 0
        assert services.anonymise_due(LONG_AFTER + timedelta(days=60)) == 0
    with college_context(a.college.id):
        assert Student.objects.exclude(name=roster.ANONYMISED_NAME).count() == 7


def test_the_anonymise_roster_command_replaces_names_and_roll_numbers(tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "real.csv"
    source.write_text(
        "roll_no,name,mark\n21A91,Real Person,7\n21A92,Other Person,9\n21A91,Real Person,8\n",
        encoding="utf-8",
    )
    target = tmp_path / "out.csv"
    call_command("anonymise_roster", str(source), str(target), "--keep-map")
    rows = list(csv.reader(target.read_text(encoding="utf-8").splitlines()))
    assert rows == [
        ["roll_no", "name", "mark"],
        ["S001", "Student 001", "7"],
        ["S002", "Student 002", "9"],
        ["S001", "Student 001", "8"],
    ]
    text = target.read_text(encoding="utf-8")
    assert "21A9" not in text and "Person" not in text
    assert json.loads((tmp_path / "real.map.json").read_text(encoding="utf-8"))["21A91"] == "S001"
    with pytest.raises(CommandError):
        call_command("anonymise_roster", str(source), str(source))
