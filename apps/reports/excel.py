"""Excel versions of the report tables. Values are written as the pages show them (text), so a
reopened file equals the page cell for cell."""

import io
from typing import Any

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from .context import NBA_HEADER, BatchReport, CourseReport

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CELL_LIMIT = 32000  # Excel refuses a cell longer than 32767 characters


def add_rows(sheet: Worksheet, rows: list[list[Any]]) -> None:
    """Append rows. Text that starts with "=" is stored as plain text, never as a formula."""
    for row in rows:
        sheet.append([v[:CELL_LIMIT] if isinstance(v, str) else v for v in row])
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                cell.data_type = "s"


def footer_rows(report: CourseReport | BatchReport) -> list[list[Any]]:
    f = report.footer
    return [
        ["College", f.college],
        ["Programme", f.programme],
        ["Batch", f.batch],
        ["Course", f.course],
        ["Term", f.term],
        ["Method version", f.method_version],
        ["Engine version", f.engine_version],
        ["Run id", f.run_id],
        ["Data status", f.data_status],
        ["Content hash", f.content_hash],
        ["Hash is", f.hash_note],
        [],
    ]


def _save(book: openpyxl.Workbook) -> bytes:
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _new(title: str) -> tuple[openpyxl.Workbook, Worksheet]:
    book = openpyxl.Workbook()
    sheet = book.active
    if sheet is None:
        raise RuntimeError("A new workbook has no sheet")
    sheet.title = title
    return book, sheet


def course_result(r: CourseReport) -> bytes:
    book, sheet = _new("Result")
    add_rows(sheet, footer_rows(r))
    for table in r.p.tables:
        add_rows(sheet, [[table.title, *table.header]])
        add_rows(sheet, [[label, *[c.text for c in cells]] for label, cells in table.rows])
        sheet.append([])
    add_rows(
        sheet,
        [
            ["Course attainment", r.p.course_text],
            ["Unrounded", r.p.course_unrounded],
            ["Target", r.p.target],
            ["Attained", {True: "Yes", False: "No", None: ""}[r.p.attained]],
        ],
    )
    return _save(book)


def course_co_sheet(r: CourseReport) -> bytes:
    book, sheet = _new("CO by assessment")
    add_rows(sheet, footer_rows(r))
    for t in r.tools:
        add_rows(
            sheet,
            [
                [t.tool, *r.co_header],
                ["Students passing (%)", *t.percents],
                ["Level", *t.levels],
                [],
                ["Part", "CO", "Passed", "Counted", "%"],
                *[[q.part, q.co, q.passed, q.denominator, q.percent] for q in t.questions],
                [],
            ],
        )
    return _save(book)


def course_co_po(r: CourseReport) -> bytes:
    book, sheet = _new("CO-PO")
    add_rows(sheet, footer_rows(r))
    add_rows(sheet, [["CO", "Final attainment", *r.po_codes]])
    add_rows(sheet, [[row.co, row.final, *row.strengths] for row in r.co_rows])
    if r.course_row:
        add_rows(sheet, [["Course", r.p.course_text, *r.course_row]])
    return _save(book)


def batch_workbook(r: BatchReport) -> bytes:
    book, sheet = _new("Batch")
    add_rows(sheet, footer_rows(r))
    add_rows(
        sheet,
        [["Outcome", "Courses", "Direct", "Indirect", "Total", "Target", "Status"]]
        + [
            [x.code, x.courses, x.direct, x.indirect, x.total, x.target, x.status] for x in r.p.rows
        ],
    )
    courses = book.create_sheet("Courses")
    add_rows(
        courses,
        [["Course", "Term", "Category", "Signed", "Course attainment", "Result", *r.codes]]
        + [
            [
                c.name,
                c.term,
                c.category,
                "Yes" if c.signed else "No",
                c.course_text,
                c.attained,
                *c.po,
            ]
            for c in r.courses
        ],
    )
    compare = book.create_sheet("Comparison")
    add_rows(
        compare,
        [["Outcome", *[f"{col.batch.name} ({col.source})" for col in r.columns]]]
        + [[code, *cells] for code, cells in r.comparison],
    )
    return _save(book)


def nba_workbook(rows: list[list[str]]) -> bytes:
    book, sheet = _new("Courses")
    add_rows(sheet, [NBA_HEADER, *rows])
    return _save(book)
