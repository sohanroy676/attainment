"""v0.10.0 A7: the largest report (a batch of eight semesters) renders within memory and time
limits. The report data is built in memory, so the test measures rendering only."""

import time
import tracemalloc
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from apps.reports import chart, context, render

pytestmark = [pytest.mark.perf]

MAX_SECONDS = 60
MAX_BYTES = 400 * 1024 * 1024  # inside a 512 MB container with room for the app itself


def _large_batch() -> context.BatchReport:
    codes = [f"PO{i}" for i in range(1, 13)] + ["PSO1", "PSO2", "PSO3"]
    courses = [
        context.BatchCourseRow(
            name=f"Course {term}-{n}", term=f"Semester {term}", category="core", signed=True,
            course_text="2.50", attained="Attained", po=["2.40"] * len(codes),
        )
        for term in range(1, 9)
        for n in range(1, 11)
    ]  # fmt: skip
    rows = [SimpleNamespace(code=c, courses=80, direct="2.4", indirect="3", total="2.5",
                            target="2.5", status="Attained", flag="") for c in codes]  # fmt: skip
    columns = [
        SimpleNamespace(
            batch=SimpleNamespace(name=n), source="signed", values=dict.fromkeys(codes, "2.5")
        )
        for n in ("2019-23", "2020-24", "2021-25")
    ]
    footer = context.Footer(
        college="College", programme="B.E.", batch="2021-25", course="All", term="All",
        method_version="m 1", engine_version="0.3.0", run_id="r", data_status="Complete",
        content_hash="h" * 64, hash_note="signed", generated_at=datetime.now(UTC),
    )  # fmt: skip
    shown = SimpleNamespace(
        method_name="m", complete=True, checklist=[], rows=rows, counts=[], excluded=[]
    )
    report = SimpleNamespace(
        programme=SimpleNamespace(name="B.E."), batch=SimpleNamespace(name="2021-25"),
        run=SimpleNamespace(include_unsigned=False), p=shown, codes=codes, courses=courses,
        columns=columns, gaps=[], overrides=[], signoffs=[], footer=footer,
        comparison=[(c, ["2.5", "2.5", "2.5"]) for c in codes],
        chart=[(f"{c.batch.name}", [Decimal("2.5")] * len(codes)) for c in columns],
    )  # fmt: skip
    return report  # type: ignore[return-value]


def test_a7_the_largest_report_renders_within_the_time_and_memory_limits() -> None:
    report = _large_batch()
    ctx = {
        "r": report,
        "footer": report.footer,
        "chart_svg": chart.bar_chart(report.codes, report.chart),
    }
    tracemalloc.start()
    started = time.monotonic()
    html = render.render_html("batch", "a", ctx, RequestFactory().get("/"))
    if render.pdf_available():
        assert render.to_pdf(html).startswith(b"%PDF")
    seconds = time.monotonic() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert html.count("Course ") >= 80
    assert seconds < MAX_SECONDS and peak < MAX_BYTES
