"""What a report shows: stored results and records laid out for a template.

Nothing is calculated here. Numbers come from `results.present` and the stored runs; counts and
rankings come from the engine through `results.services`. This module only picks and arranges.
"""

import base64
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.academics.models import Batch, CourseOffering, Programme, Section
from apps.assessments import services as papers
from apps.outcomes import services as outcomes
from apps.quality import services as quality
from apps.results import services as results
from apps.results.models import BatchRun, CalculationRun
from apps.results.present import BatchPresented, Presented, present, present_batch
from apps.workflow import services as workflow


@dataclass(frozen=True)
class Footer:
    """The lines every report carries at the bottom of each page (design 11.3)."""

    college: str
    programme: str
    batch: str
    course: str
    term: str
    method_version: str
    engine_version: str
    run_id: str
    data_status: str  # "Complete" or "Provisional"
    content_hash: str
    hash_note: str  # "signed" or "not signed: computed from the current result"
    generated_at: datetime

    @property
    def provisional(self) -> bool:
        return self.data_status != "Complete"


def _footer(
    *,
    college: str,
    programme: str,
    batch: str,
    course: str,
    term: str,
    run: CalculationRun | BatchRun,
    content_hash: str,
) -> Footer:
    return Footer(
        college=college,
        programme=programme,
        batch=batch,
        course=course,
        term=term,
        method_version="" if run.method_version is None else str(run.method_version),
        engine_version=run.engine_version,
        run_id=str(run.pk),
        data_status="Complete" if run.status == "complete" else "Provisional",
        content_hash=content_hash,
        hash_note="signed" if run.signed else "not signed: computed from the current result",
        generated_at=timezone.now(),
    )


def course_label(offering: CourseOffering) -> str:
    code = offering.course.codes.filter(valid_to__isnull=True).order_by("code").first()
    return offering.course.title if code is None else f"{code.code} {offering.course.title}"


def batch_names(offering: CourseOffering, programme: Programme) -> str:
    names = (
        Section.objects.filter(offering=offering, programme=programme)
        .values_list("batch__name", flat=True)
        .distinct()
    )
    return ", ".join(sorted(names))


@dataclass
class Signoff:
    kind: str
    role: str
    name: str
    at: datetime


@dataclass
class CourseReport:
    offering: CourseOffering
    programme: Programme
    run: CalculationRun
    footer: Footer
    p: Presented
    label: str
    kind: str  # theory, lab, project, elective
    sections: list[str]
    signoffs: list[Signoff]
    co_header: list[str] = field(default_factory=list)
    tools: list["ToolSheet"] = field(default_factory=list)
    co_rows: list["CoPoRow"] = field(default_factory=list)
    po_codes: list[str] = field(default_factory=list)
    course_row: list[str] = field(default_factory=list)
    overrides: list[tuple[str, str, str, str]] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    plans: list[str] = field(default_factory=list)
    earlier: list[Any] = field(default_factory=list)
    actions: list[Any] = field(default_factory=list)
    proofs: list["Proof"] = field(default_factory=list)


@dataclass
class Proof:
    name: str
    sha256: str
    image: str  # a data: address for PNG and JPEG, empty for a PDF


@dataclass
class ToolSheet:
    tool: str
    percents: list[str]
    levels: list[str]
    questions: list[results.QuestionRow]


@dataclass
class CoPoRow:
    co: str
    final: str
    strengths: list[str]


def _signoffs(lines: list[workflow.SignatureLine]) -> list[Signoff]:
    return [Signoff(s.kind, s.role, s.name, s.at) for s in lines]


def course_report(offering: CourseOffering, programme: Programme) -> CourseReport | None:
    """The newest run of the offering for the programme, or the signed one when it still matches.

    None when the course has no run yet.
    """
    run = results.latest_run(offering, programme)
    if run is None:
        return None
    return course_report_for(offering, programme, run)


def course_report_for(
    offering: CourseOffering, programme: Programme, run: CalculationRun
) -> CourseReport:
    shown = present(run)
    content_hash = run.content_hash or results.run_content_hash(run)
    footer = _footer(
        college=offering.college.name,
        programme=programme.name,
        batch=batch_names(offering, programme),
        course=course_label(offering),
        term=str(offering.term),
        run=run,
        content_hash=content_hash,
    )
    report = CourseReport(
        offering=offering,
        programme=programme,
        run=run,
        footer=footer,
        p=shown,
        label=course_label(offering),
        kind=offering.course.kind,
        sections=[s.name for s in offering.sections.filter(programme=programme).order_by("name")],
        signoffs=_signoffs(workflow.signatures_of(run)),
    )
    _fill_tools(report)
    _fill_mapping(report)
    report.overrides = [
        (tool, part, str(mark.normalize()), reason)
        for (tool, part), (mark, reason) in sorted(papers.approved_overrides(offering).items())
    ]
    report.observations = [o.text for o in quality.observations_of(offering)]
    report.plans = [p.text for p in quality.plans_of(offering)]
    report.earlier = quality.previous_plans(offering)
    report.actions = quality.actions_taken_on(offering)
    report.proofs = [
        Proof(e.name, e.sha256, _data_uri(e.content_type, bytes(e.content)))
        for a in report.actions
        for e in a.evidence.all()
    ]
    return report


def _data_uri(content_type: str, content: bytes) -> str:
    if content_type not in ("image/png", "image/jpeg"):
        return ""
    return f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}"


def _fill_tools(report: CourseReport) -> None:
    """One sheet per tool: the percent and level per CO (from the presented table) and the
    pass count of every question part (the engine's own count, shown as stored)."""
    gaps = results.course_gaps(report.offering, report.programme, question_limit=100_000)
    by_tool: dict[str, list[results.QuestionRow]] = {}
    if gaps is not None:
        for q in gaps.questions:
            by_tool.setdefault(q.tool, []).append(q)
    tool_table = next((t for t in report.p.tables if t.title == "Tools"), None)
    if tool_table is None:
        return
    rows = dict(tool_table.rows)
    tools = [label[: -len(" %")] for label in rows if label.endswith(" %")]
    for tool in tools:
        report.tools.append(
            ToolSheet(
                tool=tool,
                percents=[c.text for c in rows[f"{tool} %"]],
                levels=[c.text for c in rows[f"{tool} level"]],
                questions=sorted(by_tool.get(tool, []), key=lambda q: q.part),
            )
        )
    report.co_header = tool_table.header


def _fill_mapping(report: CourseReport) -> None:
    definition = results.latest_definition(report.offering)
    final_table = next((t for t in report.p.tables if t.title == "Course outcomes"), None)
    po_table = next((t for t in report.p.tables if t.title == "Programme outcomes"), None)
    if definition is None or final_table is None:
        return
    grid = outcomes.mapping_grid(definition, report.programme)
    final = dict(final_table.rows).get("Final", [])
    cos = final_table.header
    codes = [] if po_table is None else po_table.header
    report.po_codes = codes
    for co, cell in zip(cos, final, strict=False):
        strengths = [str(grid.get(co, {}).get(code, "")) for code in codes]
        report.co_rows.append(CoPoRow(co, cell.text, strengths))
    if po_table is not None and po_table.rows:
        report.course_row = [c.text for c in po_table.rows[0][1]]


# batch --------------------------------------------------------
@dataclass
class BatchCourseRow:
    name: str
    term: str
    category: str
    signed: bool
    course_text: str
    attained: str
    po: list[str]


@dataclass
class BatchReport:
    batch: Batch
    programme: Programme
    run: BatchRun
    footer: Footer
    p: BatchPresented
    codes: list[str]
    courses: list[BatchCourseRow]
    columns: list[results.BatchColumn]
    gaps: list[results.GapRow]
    overrides: list[tuple[str, str, str, str]]
    signoffs: list[Signoff]
    chart: list[tuple[str, list[Decimal | None]]] = field(default_factory=list)
    comparison: list[tuple[str, list[str]]] = field(default_factory=list)


def batch_report(batch: Batch) -> BatchReport | None:
    run = results.latest_batch_run(batch)
    if run is None:
        return None
    shown = present_batch(run)
    footer = _footer(
        college=batch.college.name,
        programme=batch.programme.name,
        batch=batch.name,
        course="All courses of the batch",
        term="All terms",
        run=run,
        content_hash=run.content_hash or results.batch_content_hash(run),
    )
    codes = [r.code for r in shown.rows]
    used = run.courses
    runs = results.runs_by_id([str(c["run"]) for c in used])
    offerings = {
        str(o.pk): o
        for o in CourseOffering.objects.filter(pk__in=[c["offering"] for c in used]).select_related(
            "course", "term__academic_year"
        )
    }
    rows: list[BatchCourseRow] = []
    overrides: list[tuple[str, str, str, str]] = []
    for course in used:
        offering = offerings.get(str(course["offering"]))
        course_run = runs.get(str(course["run"]))
        if offering is None or course_run is None:
            continue
        one = present(course_run)
        po_table = next((t for t in one.tables if t.title == "Programme outcomes"), None)
        po_map = (
            {}
            if po_table is None or not po_table.rows
            else dict(zip(po_table.header, [c.text for c in po_table.rows[0][1]], strict=False))
        )
        rows.append(
            BatchCourseRow(
                name=course["name"],
                term=str(offering.term),
                category=course["category"],
                signed=bool(course["signed"]),
                course_text=one.course_text,
                attained={True: "Attained", False: "Not attained", None: ""}[one.attained],
                po=[po_map.get(code, "-") for code in codes],
            )
        )
        overrides.extend(
            (course["name"], tool, part, f"{mark.normalize()}: {reason}")
            for (tool, part), (mark, reason) in sorted(papers.approved_overrides(offering).items())
        )
    gap_result = results.batch_gaps(batch)
    report = BatchReport(
        batch=batch,
        programme=batch.programme,
        run=run,
        footer=footer,
        p=shown,
        codes=codes,
        courses=rows,
        columns=results.comparison_columns(batch),
        gaps=[] if gap_result is None else gap_result[1],
        overrides=overrides,
        signoffs=_signoffs(workflow.batch_signatures_of(run)),
    )
    report.chart = _chart_series(report)
    report.comparison = [
        (code, [c.values.get(code) or "-" for c in report.columns]) for code in report.codes
    ]
    return report


def _chart_series(report: BatchReport) -> list[tuple[str, list[Decimal | None]]]:
    """Plot values only: the drawing turns stored text into a bar height, nothing is derived."""
    series: list[tuple[str, list[Decimal | None]]] = []
    for column in report.columns:
        points: list[Decimal | None] = []
        for code in report.codes:
            text = column.values.get(code)
            points.append(None if text in (None, "-") else Decimal(str(text)))
        series.append((f"{column.batch.name} ({column.source})", points))
    return series


# college-wide list --------------------------------------------
def nba_rows() -> list[list[str]]:
    """One row per course offering and programme: the signed result, else the newest."""
    rows: list[list[str]] = []
    for offering in (
        CourseOffering.objects.select_related("course", "term__academic_year")
        .order_by("course__title", "term__academic_year__start_date", "term__number")
        .all()
    ):
        for programme in results.programmes_of(offering):
            run = results.signed_run(offering, programme) or results.latest_run(offering, programme)
            shown = None if run is None else present(run)
            rows.append(
                [
                    course_label(offering),
                    offering.course.get_category_display(),
                    offering.course.get_kind_display(),
                    str(offering.term),
                    programme.name,
                    batch_names(offering, programme),
                    "" if run is None or run.method_version is None else str(run.method_version),
                    "No result" if shown is None else ("Signed" if run.signed else "Not signed"),  # type: ignore[union-attr]
                    "" if shown is None else ("Complete" if shown.complete else "Provisional"),
                    "" if shown is None else shown.course_text,
                    "" if shown is None else shown.target,
                    ""
                    if shown is None
                    else {True: "Attained", False: "Not attained", None: ""}[shown.attained],
                    "" if run is None else str(run.pk),
                ]
            )
    return rows


NBA_HEADER = [
    "Course", "Category", "Kind", "Term", "Programme", "Batch", "Method version", "Sign-off",
    "Data status", "Course attainment", "Target", "Attained", "Run id",
]  # fmt: skip
