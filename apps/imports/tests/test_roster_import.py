"""A1, A2, A8 (roster import), the confirm/discard screens, and the isolation sweep (A9)."""

import io

import openpyxl
import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.academics.models import Section
from apps.academics.tests.helpers import make_structure
from apps.accounts.models import Role, ScopeType
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import PASSWORD, make_college, make_user
from apps.audit.models import AuditEvent
from apps.imports import services
from apps.imports.models import ImportBatch
from apps.imports.parsers import UnreadableFile
from apps.roster import services as roster
from apps.roster.models import Enrolment, Student
from apps.tenancy.services import college_context

pytestmark = [pytest.mark.integration]


def _csv(rows: list[tuple[str, str]], header: str = "roll_no,name") -> bytes:
    lines = [header] + [f"{roll},{name}" for roll, name in rows]
    return ("\n".join(lines) + "\n").encode()


def _xlsx(rows: list[list[object]]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def _import(
    section: Section, content: bytes, name: str = "roster.csv", scope: str = "section", **kw
):  # type: ignore[no-untyped-def]
    batch = services.preview_roster(section, name, content, scope=scope)
    if batch.status == ImportBatch.Status.PREVIEWED:
        services.commit_roster(batch, **kw)
    return batch


def _roster_size(section: Section) -> int:
    return roster.enrolled_students(section.offering, section).count()


def test_a1_gap_roster_imports_seven_students_and_none_for_the_gap(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        rows = [(str(n), f"Student {n}") for n in (1, 2, 3, 4, 6, 7, 8)]
        batch = _import(s.section_a, _csv(rows))
        assert batch.status == ImportBatch.Status.COMMITTED
        assert Student.objects.count() == 7 and _roster_size(s.section_a) == 7
        assert roster.find_by_identifier("5", section=s.section_a) is None


def test_a2_ranges_per_section_and_alphanumeric_ids(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        # A 1-100 and B 1-89: the same numbers in both sections
        _import(s.section_a, _csv([(str(n), f"A{n}") for n in range(1, 101)]))
        _import(s.section_b, _csv([(str(n), f"B{n}") for n in range(1, 90)]))
        assert (_roster_size(s.section_a), _roster_size(s.section_b)) == (100, 89)
        assert Student.objects.count() == 189  # roll number 1 is two different students
    other = make_college("b")
    t = make_structure(other)
    with college_context(other.id):
        # A 1-66 and B 67-130 with roll numbers unique across the batch
        _import(t.section_a, _csv([(str(n), f"A{n}") for n in range(1, 67)]), scope="batch")
        _import(t.section_b, _csv([(str(n), f"B{n}") for n in range(67, 131)]), scope="batch")
        assert (_roster_size(t.section_a), _roster_size(t.section_b)) == (66, 64)
        _import(t.section_a, _csv([("1602-23-748-001", "Alpha")]), scope="batch")
        assert roster.find_by_identifier("1602-23-748-001", batch=t.batch) is not None


def test_a8_duplicates_and_bad_rows_are_reported_with_row_numbers_and_nothing_is_saved(
    db: None,
) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        content = _csv([("1", "One"), ("2", "Two"), ("1", "One again"), ("", "No roll"), ("5", "")])
        batch = services.preview_roster(s.section_a, "r.csv", content)
        assert batch.status == ImportBatch.Status.REJECTED
        rows = {r[0]: r[1] for r in batch.report["error_rows"]}
        assert "appears again (first on row 2)" in rows[4]
        assert "roll number is empty" in rows[5] and "name is empty" in rows[6]
        assert Student.objects.count() == 0  # nothing saved
        with pytest.raises(ValidationError):
            services.commit_roster(batch)  # a rejected file cannot be confirmed
        assert Student.objects.count() == 0


def test_a8_preview_changes_nothing_until_confirmed(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        batch = services.preview_roster(s.section_a, "r.csv", _csv([("1", "One"), ("2", "Two")]))
        assert batch.status == ImportBatch.Status.PREVIEWED and batch.report["new"] == 2
        assert Student.objects.count() == 0
        services.commit_roster(batch)
        assert Student.objects.count() == 2
        with pytest.raises(ValidationError, match="committed"):
            services.commit_roster(batch)  # no second confirm


def test_m3_reimport_lists_exactly_the_differences(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        _import(s.section_a, _csv([(str(n), f"Student {n}") for n in range(1, 11)]))
        # students 9 and 10 left the file, one new student 11 arrived, student 3 was renamed
        rows = [(str(n), f"Student {n}") for n in range(1, 9)] + [("11", "Student 11")]
        rows[2] = ("3", "Student Three")
        batch = services.preview_roster(s.section_a, "r.csv", _csv(rows))
        r = batch.report
        assert (r["new"], r["renamed"], r["unchanged"], r["missing"], r["errors"]) == (
            1,
            1,
            7,
            2,
            0,
        )
        services.commit_roster(batch)
        assert _roster_size(s.section_a) == 11  # missing students are left alone by default
        batch2 = services.preview_roster(s.section_a, "r.csv", _csv(rows))
        assert batch2.report["new"] == 0 and batch2.report["missing"] == 2
        services.commit_roster(batch2, withdraw_missing=True)
        assert _roster_size(s.section_a) == 9
        assert Enrolment.objects.filter(status="withdrawn").count() == 2  # kept, not deleted


def test_a_known_student_not_on_the_offering_is_enrolled_not_duplicated(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        known = roster.create_student("Known Student")
        roster.add_identifier(known, "7", section=s.section_a)
        batch = _import(s.section_a, _csv([("7", "Known Student"), ("8", "New Student")]))
        assert batch.report["enrol"] == 1 and batch.report["new"] == 1
        assert Student.objects.count() == 2 and _roster_size(s.section_a) == 2


def test_a_roll_number_enrolled_in_another_section_of_the_offering_is_an_error(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        _import(s.section_a, _csv([("1", "Student One")]), scope="batch")
        batch = services.preview_roster(
            s.section_b, "r.csv", _csv([("1", "Student One")]), scope="batch"
        )
        assert batch.status == ImportBatch.Status.REJECTED
        assert "enrolled in another section" in batch.report["error_rows"][0][1]


def test_commit_is_all_or_nothing_when_the_roster_changed_after_the_preview(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        batch = services.preview_roster(s.section_a, "r.csv", _csv([("1", "One"), ("2", "Two")]))
        _import(s.section_a, _csv([("1", "One")]))  # someone else imports in between
        with pytest.raises(ValidationError, match="changed since the preview"):
            services.commit_roster(batch)
        assert Student.objects.count() == 1  # only the other import's student
        batch.refresh_from_db()
        assert batch.status == ImportBatch.Status.PREVIEWED


def test_a_failure_halfway_leaves_no_partial_roster(db: None) -> None:
    from unittest import mock

    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        batch = services.preview_roster(
            s.section_a, "r.csv", _csv([(str(n), f"Student {n}") for n in range(1, 6)])
        )
        real = roster.enrol
        calls = {"n": 0}

        def flaky(*args, **kwargs):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("disk full")
            return real(*args, **kwargs)

        with mock.patch.object(roster, "enrol", flaky), pytest.raises(RuntimeError):
            services.commit_roster(batch)
        assert Student.objects.count() == 0  # the two students created before the failure are gone
        batch.refresh_from_db()
        assert batch.status == ImportBatch.Status.PREVIEWED


# parsing ---------------------------------------------------
def test_excel_files_are_read_and_whole_numbers_typed_as_floats_become_text(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        content = _xlsx([["Roll No", "Student Name"], [1.0, "One"], [2, "Two"], ["B-3", "Three"]])
        _import(s.section_a, content, name="roster.xlsx")
        assert {
            roster.find_by_identifier(r, section=s.section_a) is not None for r in ("1", "2", "B-3")
        } == {True}


def test_excel_formulas_are_never_evaluated(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        content = _xlsx([["roll_no", "name"], ["=1+1", "Formula Student"]])
        batch = services.preview_roster(s.section_a, "roster.xlsx", content)
        # an uncomputed formula has no cached value, so the roll number reads as empty
        assert batch.status == ImportBatch.Status.REJECTED
        assert "roll number is empty" in batch.report["error_rows"][0][1]


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("r.txt", b"roll_no,name\n1,A", "csv or .xlsx"),
        ("r.xlsx", b"not a zip", "not a real Excel"),
        ("r.csv", b"", "empty"),
        ("r.csv", b"id,student\n1,A\n", "roll_no"),
        ("r.csv", b"\xff\xfe\x00bad", "UTF-8"),
    ],
)
def test_unreadable_files_are_refused_with_a_plain_message(
    db: None, name: str, content: bytes, message: str
) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id), pytest.raises(UnreadableFile, match=message):
        services.preview_roster(s.section_a, name, content)


def test_csv_with_a_byte_order_mark_and_other_header_spellings(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        content = "﻿Roll Number,Student Name\n1,One\n\n2,Two\n".encode()
        batch = _import(s.section_a, content)
        assert batch.report["new"] == 2


def test_the_audit_log_records_the_import_by_counts_not_by_rows(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    actor = make_user(college, "a.admin")
    with college_context(college.id):
        batch = services.preview_roster(
            s.section_a, "secret-names.csv", _csv([("77", "Distinctive Pupil")]), actor=actor
        )
        services.commit_roster(batch, actor=actor)
        blob = " ".join(
            str(e.after) + str(e.before)
            for e in AuditEvent.objects.filter(action__startswith="imports.")
        )
        assert "Distinctive" not in blob and "secret-names" not in blob and "77" not in blob
        assert "committed" in blob


# screens ---------------------------------------------------
def _login(username: str) -> Client:
    client = Client()
    assert (
        client.post("/accounts/login/", {"username": username, "password": PASSWORD}).status_code
        == 302
    )
    return client


def test_m2_upload_preview_confirm_through_the_screens(committed_db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    admin_user = make_user(college, "a.admin")
    with college_context(college.id):
        assign_role(admin_user, Role.COLLEGE_ADMIN)
    client = _login("a.admin")
    assert b"section A" in client.get("/imports/").content
    page = client.get(f"/imports/roster/{s.section_a.pk}/")
    assert page.status_code == 200 and b"roll_no" in page.content
    upload = SimpleUploadedFile("roster.csv", _csv([("1", "One"), ("2", "Two")]))
    response = client.post(
        f"/imports/roster/{s.section_a.pk}/", {"file": upload, "scope": "section"}
    )
    assert response.status_code == 302
    preview = client.get(response["Location"])
    assert b"New students" in preview.content and b"Confirm and save" in preview.content
    with college_context(college.id):
        assert Student.objects.count() == 0  # still nothing saved
    confirmed = client.post(response["Location"], {}, follow=True)
    assert b"The roster was updated" in confirmed.content
    with college_context(college.id):
        assert _roster_size(s.section_a) == 2


def test_screens_show_row_errors_in_plain_words_and_refuse_bad_uploads(committed_db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    admin_user = make_user(college, "a.admin")
    with college_context(college.id):
        assign_role(admin_user, Role.COLLEGE_ADMIN)
    client = _login("a.admin")
    bad = SimpleUploadedFile("roster.csv", _csv([("1", "One"), ("1", "Dup"), ("", "Nobody")]))
    url = f"/imports/roster/{s.section_a.pk}/"
    response = client.post(url, {"file": bad, "scope": "section"})
    page = client.get(response["Location"])
    assert b"Row 3: Roll number 1 appears again" in page.content
    assert b"Row 4: The roll number is empty" in page.content
    assert b"Nothing was saved" in page.content and b"Confirm and save" not in page.content
    wrong = client.post(url, {"file": SimpleUploadedFile("x.pdf", b"%PDF"), "scope": "section"})
    assert wrong.status_code == 200 and b"csv or .xlsx" in wrong.content
    assert client.post(url, {"scope": "section"}).status_code == 200  # no file chosen


def test_discarding_a_preview_changes_nothing(committed_db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    admin_user = make_user(college, "a.admin")
    with college_context(college.id):
        assign_role(admin_user, Role.COLLEGE_ADMIN)
    client = _login("a.admin")
    upload = SimpleUploadedFile("roster.csv", _csv([("1", "One")]))
    response = client.post(
        f"/imports/roster/{s.section_a.pk}/", {"file": upload, "scope": "section"}
    )
    client.post(response["Location"], {"discard": "1"})
    with college_context(college.id):
        assert Student.objects.count() == 0
        assert ImportBatch.objects.get().status == ImportBatch.Status.REJECTED


def test_lecturers_cannot_import_rosters(committed_db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    lecturer = make_user(college, "a.lecturer")
    with college_context(college.id):
        assign_role(lecturer, Role.LECTURER, ScopeType.SECTION, s.section_a.pk)
    client = _login("a.lecturer")
    assert client.get(f"/imports/roster/{s.section_a.pk}/").status_code == 403
    assert b"section A" not in client.get("/imports/").content
    assert Client().get(f"/imports/roster/{s.section_a.pk}/").status_code == 302


def test_a9_isolation_sweep_no_page_or_admin_screen_leaks_another_colleges_records(
    committed_db: None,
) -> None:
    a, b = make_college("a"), make_college("b")
    sa, sb = make_structure(a, "AAA"), make_structure(b, "BBB")
    admin_a = make_user(a, "a.admin")
    with college_context(a.id):
        assign_role(admin_a, Role.COLLEGE_ADMIN)
    with college_context(b.id):
        student = roster.create_student("Hidden Student")
        roster.add_identifier(student, "HIDDEN-ROLL", section=sb.section_a)
        roster.enrol(student, sb.offering, sb.section_a)
        batch_b = services.preview_roster(sb.section_a, "b.csv", _csv([("9", "Hidden Too")]))
        secrets_b = [b"BBB", b"Hidden", b"HIDDEN-ROLL", b"b.csv"]
        object_ids = {
            model: [str(o.pk) for o in model._default_manager.all()]
            for model in admin.site._registry
        }
    client = _login("a.admin")
    paths = [
        f"/imports/roster/{sb.section_a.pk}/",
        f"/imports/{batch_b.pk}/",
        "/imports/",
    ]
    for model, ids in object_ids.items():
        opts = model._meta
        paths.append(f"/admin/{opts.app_label}/{opts.model_name}/")
        paths += [f"/admin/{opts.app_label}/{opts.model_name}/{pk}/change/" for pk in ids]
    assert len(paths) > 20
    for path in paths:
        response = client.get(path, follow=True)
        assert response.status_code in (200, 403, 404), path
        for secret in secrets_b:
            assert secret not in response.content, f"{path} leaked {secret!r}"
    with college_context(a.id):
        assert Section.objects.filter(pk=sb.section_a.pk).count() == 0
        assert sa.section_a.pk is not None
