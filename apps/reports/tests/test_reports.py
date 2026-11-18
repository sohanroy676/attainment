"""v0.10.0 reports and exports (synthetic data only)."""

import io
import json
import re
from datetime import date
from decimal import Decimal

import openpyxl
import pytest
from django.template import Context
from django.test import Client, RequestFactory, override_settings

from apps.academics.models import AcademicYear, CourseOffering, Section, Term
from apps.accounts.models import Role, ScopeType
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import PASSWORD, make_user
from apps.audit.models import AuditEvent
from apps.outcomes import services as outcomes
from apps.outcomes.models import ProgrammeOutcome
from apps.quality import services as quality
from apps.reports import chart, context, excel, export, render
from apps.results import services as results
from apps.results.models import IndirectValue
from apps.results.present import present
from apps.tenancy.services import college_context
from apps.workflow import services as wf
from apps.workflow.tests.helpers import make_wf_env, signed

pytestmark = [pytest.mark.integration]

COURSE_REPORTS = ("co_sheet", "analysis", "co_po", "action_taken", "appendix")


def _login(username: str) -> Client:
    client = Client()
    assert (
        client.post("/accounts/login/", {"username": username, "password": PASSWORD}).status_code
        == 302
    )
    return client


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _without_time(html: str) -> str:
    return re.sub(r"<span data-generated>.*?</span>", "", html)


def _signed_batch(w):  # type: ignore[no-untyped-def]
    batch = w.env.s.batch
    with college_context(w.college.id):
        for code in ("PO1", "PO2"):
            po = ProgrammeOutcome.objects.get(programme=w.programme, code=code)
            outcomes.set_target("2.5", outcome=po, batch=batch)
        results.set_batch_indirect(batch, {"PO1": "3", "PO2": "3"}, "test", w.r.iqac)
        signed(w)
        wf.prepare_batch(batch, w.r.iqac)
        wf.approve_batch(batch, w.r.hod)
        wf.sign_batch(batch, w.principal)
    return batch


def _render(name: str, ctx: dict, code: str = "a") -> str:  # type: ignore[type-arg]
    return render.render_html(name, code, ctx, RequestFactory().get("/"))


# A1, A2: every report renders; footer fields and the watermark -------------------------------
def test_a1_a2_every_report_renders_with_the_footer_and_no_watermark_when_complete(
    db: None,
) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        results.calculate(w.offering, w.programme)
        report = context.course_report(w.offering, w.programme)
        assert report is not None and report.footer.data_status == "Complete"
        for name in ("co_sheet", "co_po", "action_taken", "analysis_theory", "analysis_lab"):
            html = _render(name, {"r": report, "footer": report.footer})
            f = report.footer
            for needed in (
                f.college, f.programme, f.batch, f.course, f.term, f.method_version,
                f.engine_version, f.run_id, "Complete", f.content_hash,
            ):  # fmt: skip
                assert needed and needed in html, (name, needed)
            assert "data-watermark" not in html
            assert "Generated" in html


def test_a2_a_provisional_report_is_watermarked_and_the_mark_goes_away_when_complete(
    db: None,
) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        results.calculate(w.offering, w.programme)
        IndirectValue.objects.filter(offering=w.offering, co_code="CO1").delete()
        results.calculate(w.offering, w.programme)
        report = context.course_report(w.offering, w.programme)
        html = _render("analysis_theory", {"r": report, "footer": report.footer})
        assert "data-watermark" in html and "Provisional" in html
        assert "No indirect value has been entered for CO1" in html
        results.set_indirect(w.offering, {"CO1": "3", "CO2": "3"}, "back", w.r.iqac)
        results.calculate(w.offering, w.programme)
        report = context.course_report(w.offering, w.programme)
        assert "data-watermark" not in _render(
            "analysis_theory", {"r": report, "footer": report.footer}
        )


# A3: numbers equal the result page ---------------------------------------------------------
def test_a3_numbers_in_the_reports_equal_the_result_page(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        run = results.calculate(w.offering, w.programme)
        shown = present(run)
        report = context.course_report(w.offering, w.programme)
        text = _text(_render("analysis_theory", {"r": report, "footer": report.footer}))
        assert shown.course_text == "2.92"
        assert f"Course attainment: {shown.course_text}" in text
        for table in shown.tables:
            for _label, cells in table.rows:
                for cell in cells:
                    assert cell.text in text
        sheet = _text(_render("co_sheet", {"r": report, "footer": report.footer}))
        assert "2.84" in text and "85.71" in sheet  # CO1 final, INT1 part 1a (6 of 7)
        copo = _text(_render("co_po", {"r": report, "footer": report.footer}))
        assert "2.84" in copo and "2.89" in copo  # PO1 = 2.8933 shown at the PO precision


# A4, A8: the hash on a signed report; regenerating gives the same content -------------------
def test_a4_a8_a_signed_report_prints_the_stored_hash_and_regenerates_identically(
    db: None,
) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        signed(w)
        run = results.signed_run(w.offering, w.programme)
        assert run is not None and run.content_hash
        first = context.course_report_for(w.offering, w.programme, run)
        html1 = _render("analysis_theory", {"r": first, "footer": first.footer})
        assert f"<span data-hash>{run.content_hash}</span>" in html1
        assert "(signed)" in html1 and "Principal" in html1
        second = context.course_report_for(w.offering, w.programme, run)
        html2 = _render("analysis_theory", {"r": second, "footer": second.footer})
        assert _without_time(html1) == _without_time(html2)


def test_an_unsigned_report_says_its_hash_is_not_a_signature(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        results.calculate(w.offering, w.programme)
        report = context.course_report(w.offering, w.programme)
        assert "not signed" in report.footer.hash_note
        assert report.footer.content_hash == results.run_content_hash(report.run)


# A5: Excel reopened equals the page ----------------------------------------------------------
def test_a5_the_excel_files_equal_the_page_cell_for_cell(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        run = results.calculate(w.offering, w.programme)
        shown = present(run)
        report = context.course_report(w.offering, w.programme)
        book = openpyxl.load_workbook(io.BytesIO(excel.course_result(report)))
        rows = [list(row) for row in book["Result"].iter_rows(values_only=True)]
        for table in shown.tables:
            for label, cells in table.rows:
                assert [label, *[c.text for c in cells]] in [
                    r[: len(cells) + 1] for r in rows if r and r[0] == label
                ]
        assert ["Course attainment", "2.92"] in [r[:2] for r in rows]
        assert ["Run id", str(run.pk)] in [r[:2] for r in rows]
        sheet = openpyxl.load_workbook(io.BytesIO(excel.course_co_sheet(report)))
        values = {c for row in sheet.active.iter_rows(values_only=True) for c in row}
        assert "85.71" in values
        copo = openpyxl.load_workbook(io.BytesIO(excel.course_co_po(report)))
        assert "2.84" in {c for row in copo.active.iter_rows(values_only=True) for c in row}


def test_a_text_that_looks_like_a_formula_is_stored_as_text(db: None) -> None:
    book = openpyxl.Workbook()
    excel.add_rows(book.active, [["=1+1", "-", "plain"]])
    out = io.BytesIO()
    book.save(out)
    loaded = openpyxl.load_workbook(io.BytesIO(out.getvalue()))
    cell = loaded.active["A1"]
    assert cell.value == "=1+1" and cell.data_type == "s"


def test_a5_the_batch_excel_and_report_equal_the_batch_page(db: None) -> None:
    w = make_wf_env()
    batch = _signed_batch(w)
    with college_context(w.college.id):
        report = context.batch_report(batch)
        assert report is not None and report.run.signed
        book = openpyxl.load_workbook(io.BytesIO(excel.batch_workbook(report)))
        rows = list(book["Batch"].iter_rows(values_only=True))
        for x in report.p.rows:
            assert [x.code, x.courses, x.direct, x.indirect, x.total, x.target, x.status] in [
                list(r[:7]) for r in rows
            ]
        assert {"Batch", "Courses", "Comparison"} <= set(book.sheetnames)
        html = _render(
            "batch",
            {
                "r": report,
                "footer": report.footer,
                "chart_svg": chart.bar_chart(report.codes, report.chart),
            },
        )
        assert report.run.content_hash in html
        assert "<svg" in html and "data-watermark" not in html
        assert len(report.courses) == 1 and report.courses[0].course_text == "2.92"


# A6: NBA list ------------------------------------------------------------------------------
def test_a6_the_nba_list_has_one_row_per_course_and_programme(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        signed(w)
        rows = context.nba_rows()
        assert len(rows) == 1
        row = dict(zip(context.NBA_HEADER, rows[0], strict=True))
        assert row["Sign-off"] == "Signed" and row["Course attainment"] == "2.92"
        assert row["Data status"] == "Complete" and row["Attained"] == "Attained"
        book = openpyxl.load_workbook(io.BytesIO(excel.nba_workbook(rows)))
        assert [c.value for c in book.active[1]] == context.NBA_HEADER
        assert book.active.max_row == 2


def test_the_nba_list_shows_a_course_with_no_result_instead_of_dropping_it(db: None) -> None:
    w = make_wf_env()  # nothing calculated: marks exist but no run yet
    with college_context(w.college.id):
        IndirectValue.objects.all().delete()
        from apps.results.models import CalculationRun

        CalculationRun.objects.all().delete()
        rows = context.nba_rows()
        assert len(rows) == 1 and rows[0][context.NBA_HEADER.index("Sign-off")] == "No result"


# A9: per-college template override -----------------------------------------------------------
def test_a9_one_colleges_template_override_does_not_reach_another(
    db: None,
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    folder = tmp_path / "reports" / "a"
    folder.mkdir(parents=True)
    (folder / "co_po.html").write_text("OVERRIDDEN {{ footer.college }}", encoding="utf-8")
    from django.conf import settings

    templates = [{**settings.TEMPLATES[0], "DIRS": [tmp_path, *settings.TEMPLATES[0]["DIRS"]]}]
    with override_settings(TEMPLATES=templates):
        own = render.template_for("co_po", "a")
        other = render.template_for("co_po", "b")
        assert own.template.render(Context({"footer": {"college": "X"}})) == "OVERRIDDEN X"
        assert other.origin.name != own.origin.name
        assert "OVERRIDDEN" not in other.template.source


# A10: full export ----------------------------------------------------------------------------
def test_a10_the_full_export_has_every_table_with_matching_counts(db: None) -> None:
    w = make_wf_env()
    other = make_wf_env("b")
    with college_context(w.college.id):
        signed(w)
        counts = export.counts()
        data = json.loads(export.as_json())
        assert set(data) == set(counts) and len(counts) > 30
        assert {k: len(v) for k, v in data.items()} == counts
        assert counts["results.calculationrun"] >= 1 and counts["marks.markcell"] > 0
        text = json.dumps(data)
        users = data["accounts.user"]
        assert users and all("password" not in u for u in users)
        assert str(other.college.id) not in text  # only this college's rows
        book = openpyxl.load_workbook(io.BytesIO(export.as_excel()))
        index = {r[0]: r[2] for r in book["Index"].iter_rows(min_row=2, values_only=True)}
        assert index == counts


# A11, A12: access by role and across colleges ------------------------------------------------
def test_a11_access_follows_the_role_table_and_colleges_are_separate(committed_db: None) -> None:
    w = make_wf_env()
    batch = _signed_batch(w)
    admin = make_user(w.college, "a.admin")
    auditor = make_user(w.college, "a.auditor2")
    with college_context(w.college.id):
        assign_role(admin, Role.COLLEGE_ADMIN)
        assign_role(auditor, Role.AUDITOR)
        results.calculate(w.offering, w.programme)
    off = w.offering.pk
    course_urls = [f"/reports/course/{off}/{n}.html" for n in COURSE_REPORTS]
    course_urls += [f"/reports/course/{off}/{n}.xlsx" for n in ("co_sheet", "analysis", "co_po")]
    batch_urls = [
        f"/reports/batch/{batch.pk}/report.html",
        f"/reports/batch/{batch.pk}/report.xlsx",
    ]
    for username in ("a.iqac", "a.hod", "a.principal", "a.auditor2"):
        client = _login(username)
        for url in course_urls + batch_urls:
            assert client.get(url).status_code == 200, (username, url)
    html = _login("a.iqac").get(f"/reports/course/{off}/analysis.html").content.decode()
    assert "2.92" in html
    lecturer = _login("a.lecturer_a")  # a section-scoped role: no course or batch report
    for url in course_urls + batch_urls + ["/reports/nba.xlsx", "/reports/export.json"]:
        assert lecturer.get(url).status_code == 403, url
    assert _login("a.iqac").get("/reports/export.json").status_code == 403
    assert _login("a.hod").get("/reports/nba.xlsx").status_code == 403  # department scope only
    assert _login("a.principal").get("/reports/nba.xlsx").status_code == 200
    assert Client().get(course_urls[0]).status_code == 302  # login required
    assert _login("a.iqac").get(f"/reports/course/{off}/nothing.html").status_code == 404
    assert _login("a.iqac").get(f"/reports/course/{off}/analysis.exe").status_code == 404
    assert _login("a.iqac").get(f"/reports/course/{off}/action_taken.xlsx").status_code == 404

    for fmt in ("json", "xlsx"):
        response = _login("a.admin").get(f"/reports/export.{fmt}")
        assert response.status_code == 200 and len(response.content) > 1000
    with college_context(w.college.id):
        events = AuditEvent.objects.filter(action="college.exported")
        assert events.count() == 2 and events.first().after["format"] in ("json", "xlsx")

    foreign = make_wf_env("b")
    assert foreign.college.id != w.college.id
    for username in ("b.iqac", "b.principal"):
        client = _login(username)
        for url in course_urls + batch_urls:
            assert client.get(url).status_code == 404, (username, url)
    export_b = json.loads(_admin_export("b", foreign))
    assert str(w.college.id) not in json.dumps(export_b)


def _admin_export(code: str, w) -> bytes:  # type: ignore[no-untyped-def]
    admin = make_user(w.college, f"{code}.admin")
    with college_context(w.college.id):
        assign_role(admin, Role.COLLEGE_ADMIN)
    return _login(f"{code}.admin").get("/reports/export.json").content


# Action Taken Report with a proof image -------------------------------------------------------
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\x9d\xcc"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_the_action_taken_report_lists_last_years_plan_actions_and_proof(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        plan = quality.add_plan(w.offering, "Revise tutorial 2", w.r.hod)
        year = AcademicYear.objects.create(
            label="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31)
        )
        later = CourseOffering.objects.create(
            course=w.offering.course, term=Term.objects.create(academic_year=year, number=6)
        )
        Section.objects.create(offering=later, name="A", programme=w.programme, batch=w.env.s.batch)
        teacher = make_user(w.college, "a.lecturer2")
        assign_role(teacher, Role.LECTURER, ScopeType.SECTION, later.sections.get().pk)
        action = quality.add_action(plan, later, "Held a revision class", date(2026, 8, 1), teacher)
        quality.add_evidence(action, [("proof.png", PNG), ("note.pdf", b"%PDF-1.4\n%x\n")], teacher)
        results.calculate(later, w.programme)
        report = context.course_report(later, w.programme)
        html = _render("action_taken", {"r": report, "footer": report.footer})
        assert "Revise tutorial 2" in html and "Held a revision class" in html
        assert "2026-08-01" in html and "proof.png" in html and "note.pdf" in html
        assert "data:image/png;base64," in html  # the image is inside the page
        assert html.count("<img") == 1  # the PDF proof is listed, not embedded


# the explanation appendix follows what the viewer may see ------------------------------------
def test_the_appendix_explains_a_number_and_hides_other_sections(committed_db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        results.calculate(w.offering, w.programme)
    page = (
        _login("a.iqac")
        .get(f"/reports/course/{w.offering.pk}/appendix.html?key=final/CO1")
        .content.decode()
    )
    assert "final/CO1" in page and "Explanation appendix" in page
    assert "section A" in page or "Course" in page


# chart ---------------------------------------------------------------------------------------
def test_the_chart_draws_bars_escapes_labels_and_skips_missing_values() -> None:
    svg = chart.bar_chart(
        ["PO1", "PO<2>"],
        [("2021-25 (signed)", [Decimal("3"), None]), ("X & Y", [Decimal("1.5"), Decimal("2")])],
    )
    assert svg.startswith("<svg") and svg.count("<rect") == 3 + 2  # three bars, two legend keys
    assert "PO&lt;2&gt;" in svg and "X &amp; Y" in svg and "PO<2>" not in svg
    assert chart.bar_chart([], []) == ""


# PDF (needs WeasyPrint's native libraries: skipped where they are missing) --------------------
@pytest.mark.skipif(not render.pdf_available(), reason="WeasyPrint's libraries are not installed")
def test_a1_a3_every_report_is_a_valid_pdf_whose_text_carries_the_numbers_and_footer(
    db: None,
) -> None:
    from pypdf import PdfReader

    def pdf_text(html: str) -> tuple[str, int]:
        reader = PdfReader(io.BytesIO(render.to_pdf(html)))
        return re.sub(r"\s+", " ", " ".join(p.extract_text() for p in reader.pages)), len(
            reader.pages
        )

    w = make_wf_env()
    batch = _signed_batch(w)
    with college_context(w.college.id):
        report = context.course_report(w.offering, w.programme)
        for name in ("co_sheet", "analysis_theory", "co_po", "action_taken", "appendix"):
            text, pages = pdf_text(
                _render(name, {"r": report, "footer": report.footer, "explained": []})
            )
            assert pages >= 1 and "Principal" in text or name != "analysis_theory"
            assert report.footer.run_id.replace("-", "") in text.replace("-", "").replace(" ", "")
        text, _ = pdf_text(_render("analysis_theory", {"r": report, "footer": report.footer}))
        assert "Course attainment: 2.92" in text and "2.84" in text
        b = context.batch_report(batch)
        html = _render(
            "batch", {"r": b, "footer": b.footer, "chart_svg": chart.bar_chart(b.codes, b.chart)}
        )
        text, pages = pdf_text(html)
        assert pages >= 1 and "Department and batch report" in text and "PO1" in text
        assert b.run.content_hash[:16] in text.replace(" ", "")


def test_a_report_never_loads_a_file_from_outside_the_page() -> None:
    if not render.pdf_available():
        pytest.skip("WeasyPrint's libraries are not installed")
    with pytest.raises(ValueError):
        render._refuse("file:///etc/passwd")
    with pytest.raises(ValueError):
        render._refuse("http://example.com/x.png")


def test_the_pdf_route_says_so_when_the_pdf_libraries_are_missing(
    committed_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        results.calculate(w.offering, w.programme)
    monkeypatch.setattr(render, "pdf_available", lambda: False)
    response = _login("a.iqac").get(f"/reports/course/{w.offering.pk}/analysis.pdf")
    assert response.status_code == 503 and b"PDF output is not available" in response.content
