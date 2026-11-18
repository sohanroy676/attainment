"""QuestionPass and the per-part percentage, plus AggregateToCO (mean of part percentages)."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from ..model import AssessmentInput, Cell, Override, State
from ..precision import HUNDRED
from ..schema import QuestionWiseTool
from ..trace import Trace
from .denominator import denominator_for
from .normalise import Cells, sat_students


@dataclass(frozen=True)
class PartResult:
    part_id: str
    co: str | None
    threshold: Decimal
    passed: int
    attempted: int
    denominator: int
    percent: Decimal | None
    overridden: bool


def passes(mark: Decimal, threshold: Decimal, boundary: str) -> bool:
    """A mark exactly at the threshold passes with '>=' and fails with '>'."""
    return mark >= threshold if boundary == ">=" else mark > threshold


def evaluate_parts(
    assessment: AssessmentInput,
    cells: Cells,
    config: QuestionWiseTool,
    overrides: dict[tuple[str, str], Override],
    enrolled: int,
    trace: Trace,
) -> list[PartResult]:
    tool = assessment.tool
    sat = sat_students(assessment, cells, config.whole_assessment_absent)
    sat_set = set(sat)
    results = []
    for part in assessment.parts:
        override = overrides.get((tool, part.id))
        threshold = override.pass_mark if override else part.max * config.pass_pct / HUNDRED
        marks = _attempted_marks(cells, sat_set, part.id)
        passed = sum(1 for m in marks if passes(m, threshold, config.boundary))
        den = denominator_for(
            part, config.denominator, len(marks), len(sat), enrolled, config.fixed_n
        )
        percent = Decimal(passed) * HUNDRED / Decimal(den) if den > 0 else None
        results.append(
            PartResult(
                part.id, part.co, threshold, passed, len(marks), den, percent, override is not None
            )
        )
        rate = f"{len(marks)} of {len(sat)} attempted" if len(sat) else "no students"
        note = (
            f" (pass mark overridden to {override.pass_mark}: {override.reason})"
            if override
            else ""
        )
        warning = den < config.small_group_warning
        trace.add(
            "QuestionPass",
            f"{tool}/{part.id}",
            f"{passed}/{den} passed at {threshold} of {part.max} ({rate}){note}"
            + ("; small group" if warning else ""),
            passed=passed,
            denominator=den,
            attempted=len(marks),
            sat=len(sat),
            threshold=threshold,
            small_group=warning,
        )
    return results


def _attempted_marks(cells: Cells, students: set[str], part_id: str) -> list[Decimal]:
    marks = []
    for student, row in cells.items():
        if student not in students:
            continue
        cell: Cell | None = row.get(part_id)
        if cell is not None and cell.state is State.ENTERED and cell.value is not None:
            marks.append(cell.value)
    return marks


def aggregate_to_co(
    tool: str, results: list[PartResult], cos: tuple[str, ...], trace: Trace
) -> dict[str, Decimal | None]:
    """Mean of the part percentages tagged to each CO. None when no part gives a value."""
    by_co: dict[str, list[Decimal]] = defaultdict(list)
    for result in results:
        if result.co is not None and result.percent is not None:
            by_co[result.co].append(result.percent)
    out: dict[str, Decimal | None] = {}
    for co in cos:
        values = by_co.get(co)
        out[co] = sum(values, Decimal(0)) / Decimal(len(values)) if values else None
        trace.add(
            "AggregateToCO",
            f"{tool}/{co}",
            f"mean of {len(values or [])} part percentages = {out[co]}",
            parts=len(values or []),
        )
    return out
