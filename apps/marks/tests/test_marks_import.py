"""A5 to A8: sheets, imports with preview, SEE scripts, and file safety."""

import io
import zipfile
from decimal import Decimal

import openpyxl
import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client

from apps.accounts.tests.helpers import PASSWORD
from apps.assessments import services as papers
from apps.audit.models import AuditEvent
from apps.imports.models import ImportBatch
from apps.imports.parsers import UnreadableFile
from apps.marks import importer, services
from apps.marks.models import MarkCell, ScriptMapping
from apps.tenancy.services import college_context

from .helpers import make_env

pytestmark = [pytest.mark.integration]

D = Decimal


def _csv(*lines: str) -> bytes:
    return ("\n".join(lines) + "\n").encode()


def _cells(env, assessment):  # type: ignore[no-untyped-def]
    return {
        (c.row.enrolment.student_id, c.part.code): (c.state, c.value)
        for c in MarkCell.objects.filter(row__assessment=assessment).select_related(
            "row__enrolment", "part"
        )
    }


# A5 --------------------------------------------------------
def test_a5_template_round_trip_download_fill_upload_marks_equal(db: None) -> None:
    env = make_env()
    with college_context(env.college.id):
        raw = importer.build_template(env.internal, env.s.section_a)
        book = openpyxl.load_workbook(io.BytesIO(raw))
        sheet = book["Marks"]
        header = [c.value for c in sheet[1]]
        assert header == ["roll_no", "1a", "1b"]
        rolls = [sheet.cell(row=r, column=1).value for r in range(2, sheet.max_row + 1)]
        assert rolls == ["1", "2", "3", "4", "5"]
        planned = {
            "1": ("3", "2.5"),
            "2": ("0", "AB"),
            "3": ("4", "-"),
            "4": ("1.25", ""),
            "5": ("", ""),
        }
        for r, roll in enumerate(rolls, start=2):
            for c, text in enumerate(planned[roll], start=2):
                sheet.cell(
                    row=r,
                    column=c,
                    value=text if not text.replace(".", "").isdigit() else float(text),
                )
        filled = io.BytesIO()
        book.save(filled)
        batch = importer.preview_marks(
            env.internal, env.s.section_a, "t.xlsx", filled.getvalue(), env.lecturer_a
        )
        assert batch.status == ImportBatch.Status.PREVIEWED and batch.report["errors"] == 0
        assert MarkCell.objects.count() == 0  # nothing yet
        importer.commit_marks(batch, env.lecturer_a)
        by_roll = {str(e.student_id): roll for e, roll in zip(env.enrolments_a, rolls, strict=True)}
        stored = {
            (by_roll[str(student)], code): (state, value)
            for (student, code), (state, value) in _cells(env, env.internal).items()
        }
        assert stored[("1", "1a")] == ("value", D("3.00")) and stored[("1", "1b")] == (
            "value",
            D("2.50"),
        )
        assert stored[("2", "1a")] == ("value", D("0.00"))  # a zero is a real mark
        assert stored[("2", "1b")] == ("absent", None) and stored[("3", "1b")] == (
            "not_attempted",
            None,
        )
        assert stored[("4", "1a")] == ("value", D("1.25"))
        assert ("5", "1a") not in stored  # blank cells on a blank stay untouched
        # the kept file and the batch are on record
        batch.refresh_from_db()
        assert bytes(batch.file_content) == filled.getvalue() and batch.status == "committed"
        # downloading again gives the marks back (a round trip)
        again = openpyxl.load_workbook(
            io.BytesIO(importer.build_template(env.internal, env.s.section_a))
        )
        assert [c.value for c in again["Marks"][2]] == ["1", 3.0, 2.5]
        assert [c.value for c in again["Marks"][3]][1:] == [0.0, "AB"]


def test_a5_reimporting_changes_only_what_differs_and_keeps_history(db: None) -> None:
    env = make_env()
    with college_context(env.college.id):
        first = importer.preview_marks(
            env.internal,
            env.s.section_a,
            "m.csv",
            _csv("roll_no,1a,1b", "1,3,2", "2,1,1"),
            env.lecturer_a,
        )
        importer.commit_marks(first, env.lecturer_a)
        second = importer.preview_marks(
            env.internal,
            env.s.section_a,
            "m.csv",
            _csv("roll_no,1a,1b", "1,3,4", "2,1,1"),
            env.lecturer_a,
        )
        assert second.report["changed"] == 1
        importer.commit_marks(second, env.lecturer_a)
        cell = MarkCell.objects.get(part__code="1b", row__enrolment=env.enrolments_a[0])
        assert cell.value == D("4.00") and cell.row_version == 2
        reasons = {c.reason for c in services.history(cell)}
        assert reasons == {"marks import"} and services.history(cell).count() == 2


# A6 --------------------------------------------------------
def test_a6_bad_rows_are_reported_by_row_and_nothing_is_saved(db: None) -> None:
    env = make_env()
    content = _csv("roll_no,1a,1b", "1,3,2", "99,1,1", "2,5,1", "1,1,1", "3,x,2", ",1,1")
    with college_context(env.college.id):
        batch = importer.preview_marks(
            env.internal, env.s.section_a, "m.csv", content, env.lecturer_a
        )
        assert batch.status == ImportBatch.Status.REJECTED
        errors = dict(batch.report["error_rows"])
        assert "Roll number 99 is not on this section's roster" in errors[3]
        assert "1a: 5 is above the maximum 4" in errors[4]
        assert "1 appears again (first on row 2)" in errors[5]
        assert "1a: 'x' is not a mark" in errors[6]
        assert "roll_no is empty" in errors[7]
        assert MarkCell.objects.count() == 0  # row 2 was fine, yet nothing is stored
        with pytest.raises(ValidationError, match="rejected"):
            importer.commit_marks(batch, env.lecturer_a)
        assert MarkCell.objects.count() == 0


def test_a6_wrong_sheet_is_refused_before_any_row_is_read(db: None) -> None:
    env = make_env()
    with college_context(env.college.id):
        see_sheet = importer.build_template(env.see, env.s.section_a)
        with pytest.raises(UnreadableFile, match="different assessment"):
            importer.preview_marks(
                env.internal, env.s.section_a, "t.xlsx", see_sheet, env.lecturer_a
            )
        other_section = importer.build_template(env.internal, env.s.section_b)
        with pytest.raises(UnreadableFile, match="different section"):
            importer.preview_marks(
                env.internal, env.s.section_a, "t.xlsx", other_section, env.lecturer_a
            )
        with pytest.raises(UnreadableFile, match="not parts of this paper: Q9"):
            importer.preview_marks(
                env.internal,
                env.s.section_a,
                "m.csv",
                _csv("roll_no,1a,Q9", "1,1,1"),
                env.lecturer_a,
            )
        with pytest.raises(UnreadableFile, match="must be 'roll_no'"):
            importer.preview_marks(
                env.internal, env.s.section_a, "m.csv", _csv("id,1a", "1,1"), env.lecturer_a
            )


def test_a6_a_lecturer_cannot_import_into_another_section_or_a_commit_that_is_not_theirs(
    db: None,
) -> None:
    env = make_env()
    with college_context(env.college.id):
        with pytest.raises(PermissionDenied):
            importer.preview_marks(
                env.internal, env.s.section_b, "m.csv", _csv("roll_no,1a", "1,1"), env.lecturer_a
            )
        with pytest.raises(PermissionDenied):
            importer.preview_marks(
                env.internal, env.s.section_a, "m.csv", _csv("roll_no,1a", "1,1"), env.auditor
            )


def test_a_failure_while_loading_leaves_no_partial_marks(db: None) -> None:
    from unittest import mock

    env = make_env()
    with college_context(env.college.id):
        batch = importer.preview_marks(
            env.internal,
            env.s.section_a,
            "m.csv",
            _csv("roll_no,1a", "1,1", "2,2", "3,3"),
            env.lecturer_a,
        )
        real, calls = services.save_cell, {"n": 0}

        def flaky(*args, **kwargs):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("disk full")
            return real(*args, **kwargs)

        with mock.patch.object(services, "save_cell", flaky), pytest.raises(RuntimeError):
            importer.commit_marks(batch, env.lecturer_a)
        assert MarkCell.objects.count() == 0
        batch.refresh_from_db()
        assert batch.status == ImportBatch.Status.PREVIEWED


# A7 --------------------------------------------------------
def _map_scripts(env, content):  # type: ignore[no-untyped-def]
    batch = importer.preview_scripts(env.see, "scripts.csv", content, env.exam)
    if batch.status == ImportBatch.Status.PREVIEWED:
        importer.commit_scripts(batch, env.exam)
    return batch


def test_a7_script_mapping_reports_unknown_duplicate_and_double_scripts(db: None) -> None:
    env = make_env()
    with college_context(env.college.id):
        bad = importer.preview_scripts(
            env.see, "s.csv",
            _csv(
                "script_no,roll_no,section",
                "S1,1,A", "S1,2,A", "S3,1,A", "S4,77,A", "S5,,A", ",3,A",
            ),
            env.exam,
        )  # fmt: skip
        messages = dict(bad.report["error_rows"])
        assert "Script S1 appears again (first on row 2)" in messages[3]
        assert "Roll number 1 already has a script on row 2" in messages[4]
        assert "Roll number 77 is not on this course's roster" in messages[5]
        assert "needed" in messages[6] and "needed" in messages[7]
        assert ScriptMapping.objects.count() == 0
        # a clean mapping loads; a later file cannot give a mapped script to someone else
        _map_scripts(env, _csv("script_no,roll_no,section", "S1,1,A", "S2,2,A"))
        assert ScriptMapping.objects.count() == 2
        clash = importer.preview_scripts(
            env.see, "s.csv", _csv("script_no,roll_no,section", "S1,3,A", "S9,2,A"), env.exam
        )
        text = " ".join(m for _, m in clash.report["error_rows"])
        assert "Script S1 is already mapped to another student" in text
        assert "Roll number 2 already has another script" in text


def test_a7_only_the_exam_branch_maps_scripts_and_enters_see_marks(db: None) -> None:
    env = make_env()
    with college_context(env.college.id):
        for user in (env.lecturer_a, env.auditor):
            with pytest.raises(PermissionDenied):
                importer.preview_scripts(env.see, "s.csv", _csv("script_no,roll_no", "S1,1"), user)
            with pytest.raises(PermissionDenied):
                importer.preview_see_marks(env.see, "m.csv", _csv("script_no,1", "S1,1"), user)


def test_a7_see_marks_by_script_report_unmapped_scripts_and_warn_about_extra_answers(
    db: None,
) -> None:
    env = make_env()
    with college_context(env.college.id):
        _map_scripts(env, _csv("script_no,roll_no,section", "S1,1,A", "S2,2,A", "S3,3,A"))
        content = _csv(
            "script_no,1,11,12,13",
            "S1,3,4,3,2",
            "S2,2,4,-,-",
            "S9,1,1,1,1",
        )  # S1 answered all three choice questions; S9 has no mapping
        bad = importer.preview_see_marks(env.see, "see.csv", content, env.exam)
        assert bad.status == ImportBatch.Status.REJECTED
        assert any("Script S9 is not mapped to a student" in m for _, m in bad.report["error_rows"])
        assert (
            bad.report["warnings"]
            and "answered 1 more than the best 2" in bad.report["warnings"][0][1]
        )

        good = importer.preview_see_marks(
            env.see, "see.csv", _csv("script_no,1,11,12,13", "S1,3,4,3,2", "S2,2,4,-,-"), env.exam
        )
        assert good.status == ImportBatch.Status.PREVIEWED and len(good.report["warnings"]) == 1
        importer.commit_marks(good, env.exam)
        stored = _cells(env, env.see)
        s1 = env.enrolments_a[0].student_id
        assert stored[(s1, "13")] == (
            "value",
            D("2.00"),
        )  # kept as entered, set aside only in the calculation

        # the best-N rule then sets the extra answer aside: Q13 (lowest, 2) is dropped
        from engine.schema import ChoiceRule
        from engine.steps.choice import choice_select
        from engine.steps.normalise import normalise_states
        from engine.trace import Trace

        data = services.engine_assessment(env.see)
        rules = {
            c: ChoiceRule.model_validate(r) for c, r in papers.engine_choice_rules(env.see).items()
        }
        trace = Trace()
        cells = choice_select(data, normalise_states(data, "exclude", trace, False), rules, trace)
        dropped = {p for p, cell in cells[str(s1)].items() if cell.state.value == "dropped"}
        assert dropped == {"13"} and "Q13" in trace.text()


def test_a7_the_audit_log_records_imports_without_the_marks(db: None) -> None:
    env = make_env()
    with college_context(env.college.id):
        batch = importer.preview_marks(
            env.internal,
            env.s.section_a,
            "secret-marks.csv",
            _csv("roll_no,1a", "1,3"),
            env.lecturer_a,
        )
        importer.commit_marks(batch, env.lecturer_a)
        events = AuditEvent.objects.filter(entity="imports.importbatch")
        blob = " ".join(str(e.after) for e in events)
        assert "secret-marks" not in blob and "committed" in blob and events.count() == 2


# A8 --------------------------------------------------------
def _xlsx(rows) -> bytes:  # type: ignore[no-untyped-def]
    book = openpyxl.Workbook()
    for row in rows:
        book.active.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_a8_a_formula_without_a_stored_result_is_rejected_with_a_clear_message(db: None) -> None:
    env = make_env()
    raw = _xlsx([["roll_no", "1a"], ["1", "=1+2"]])
    with college_context(env.college.id):
        with pytest.raises(UnreadableFile, match="Cell B2 holds a formula with no stored result"):
            importer.preview_marks(env.internal, env.s.section_a, "m.xlsx", raw, env.lecturer_a)
        assert ImportBatch.objects.count() == 0


def test_a8_a_workbook_with_a_chart_is_read_normally(db: None) -> None:
    from openpyxl.chart import BarChart, Reference

    env = make_env()
    book = openpyxl.Workbook()
    sheet = book.active
    for row in [["roll_no", "1a"], ["1", 3], ["2", 2]]:
        sheet.append(row)
    chart = BarChart()
    chart.add_data(Reference(sheet, min_col=2, min_row=1, max_row=3), titles_from_data=True)
    sheet.add_chart(chart, "E2")
    out = io.BytesIO()
    book.save(out)
    with college_context(env.college.id):
        batch = importer.preview_marks(
            env.internal, env.s.section_a, "m.xlsx", out.getvalue(), env.lecturer_a
        )
        assert batch.status == ImportBatch.Status.PREVIEWED and batch.report["rows"] == 2


def test_a8_an_xml_entity_attack_is_rejected(db: None) -> None:
    env = make_env()
    good = io.BytesIO(_xlsx([["roll_no", "1a"], ["1", 3]]))
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>&lol2;</t></is></c></row>'
        "</sheetData></worksheet>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(good) as src, zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            dst.writestr(
                item.filename, bomb if item.filename == "xl/worksheets/sheet1.xml" else data
            )
    with (
        college_context(env.college.id),
        pytest.raises(UnreadableFile, match="not safe to read|could not be opened"),
    ):
        importer.preview_marks(
            env.internal, env.s.section_a, "m.xlsx", out.getvalue(), env.lecturer_a
        )


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("m.csv", b"x" * (10 * 1024 * 1024 + 1), "larger than 10 MB"),
        ("m.xlsx", b"not a zip file", "not a real Excel"),
        ("m.pdf", b"%PDF", "csv or .xlsx"),
        ("m.csv", b"", "empty"),
        ("m.csv", b"\xff\xfe\x00", "UTF-8"),
    ],
)
def test_a8_oversize_wrong_type_and_unreadable_files_are_refused(
    db: None, name: str, content: bytes, message: str
) -> None:
    env = make_env()
    with college_context(env.college.id), pytest.raises(UnreadableFile, match=message):
        importer.preview_marks(env.internal, env.s.section_a, name, content, env.lecturer_a)


# the screens -----------------------------------------------
def _login(username: str) -> Client:
    client = Client()
    assert (
        client.post("/accounts/login/", {"username": username, "password": PASSWORD}).status_code
        == 302
    )
    return client


def test_m3_m4_download_upload_preview_confirm_through_the_screens(committed_db: None) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    env = make_env()
    client = _login("a.lecturer_a")
    base = f"/marks/{env.internal.pk}/{env.s.section_a.pk}/"
    download = client.get(base + "template/")
    assert download.status_code == 200 and download["Content-Type"].endswith("sheet")
    assert "INT1-A.xlsx" in download["Content-Disposition"]
    bad = SimpleUploadedFile("m.csv", _csv("roll_no,1a,1b", "99,1,1", "2,9,1"))
    preview = client.get(client.post(base + "import/", {"file": bad})["Location"])
    assert b"Row 2: Roll number 99 is not on this section" in preview.content
    assert (
        b"Row 3: 1a: 9 is above the maximum 4" in preview.content
        and b"Confirm and load" not in preview.content
    )
    good = SimpleUploadedFile("m.csv", _csv("roll_no,1a,1b", "1,3,2", "2,1,1"))
    location = client.post(base + "import/", {"file": good})["Location"]
    assert b"Confirm and load" in client.get(location).content
    confirmed = client.post(location, {}, follow=True)
    assert b"The file was loaded" in confirmed.content
    with college_context(env.college.id):
        assert MarkCell.objects.count() == 4
    assert client.get(f"/marks/{env.internal.pk}/{env.s.section_b.pk}/import/").status_code == 403
    other = _login("a.lecturer_b")
    assert other.get(location).status_code == 403  # someone else's batch


def test_see_uploads_through_the_screens_are_for_the_exam_branch(committed_db: None) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    env = make_env()
    exam = _login("a.exam")
    scripts = SimpleUploadedFile("s.csv", _csv("script_no,roll_no,section", "S1,1,A", "S2,2,A"))
    location = exam.post(f"/marks/{env.see.pk}/scripts/", {"file": scripts})["Location"]
    exam.post(location, {})
    see = SimpleUploadedFile("see.csv", _csv("script_no,1,11", "S1,3,4", "S2,2,-"))
    location = exam.post(f"/marks/{env.see.pk}/see/", {"file": see})["Location"]
    assert b"Confirm and load" in exam.get(location).content
    exam.post(location, {})
    with college_context(env.college.id):
        assert MarkCell.objects.filter(row__assessment=env.see).count() == 4
    lecturer = _login("a.lecturer_a")
    assert lecturer.get(f"/marks/{env.see.pk}/scripts/").status_code == 403
    assert lecturer.get(f"/marks/{env.internal.pk}/scripts/").status_code == 404  # not the SEE
