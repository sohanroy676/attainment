"""PerStudentAverage (quiz, assignment) and SingleTotal (lab): the pass percentage of the class.

Both give one percentage that applies to the listed COs (all by default).
"""

from decimal import Decimal

from ..errors import EngineError
from ..model import AssessmentInput, State
from ..precision import HUNDRED
from ..schema import PerStudentAverageTool, SingleTotalTool
from ..trace import Trace
from .normalise import Cells
from .question import passes


def per_student_average(
    assessment: AssessmentInput, cells: Cells, config: PerStudentAverageTool, trace: Trace
) -> Decimal | None:
    """Average each student's items, pass if the average reaches pass_pct of `max`."""
    tool = assessment.tool
    for part in assessment.parts:
        if part.max != config.max:
            raise EngineError(
                f"{tool}: item {part.id} has max {part.max}, method says {config.max}"
            )
    threshold = config.max * config.pass_pct / HUNDRED
    passed = counted = 0
    for student in sorted(cells):
        marks = [
            c.value
            for part in assessment.parts
            if (c := cells[student].get(part.id)) is not None
            and c.state is State.ENTERED
            and c.value is not None
        ]
        if not marks:
            continue  # nothing to average (all items skipped or blank): left out
        counted += 1
        if passes(sum(marks, Decimal(0)) / Decimal(len(marks)), threshold, config.boundary):
            passed += 1
    trace.add(
        "PerStudentAverage",
        tool,
        f"{passed} of {counted} students reach an average of {threshold} of {config.max}",
        passed=passed,
        counted=counted,
        threshold=threshold,
    )
    return Decimal(passed) * HUNDRED / Decimal(counted) if counted else None


def single_total(
    assessment: AssessmentInput, cells: Cells, config: SingleTotalTool, trace: Trace
) -> Decimal | None:
    """Add each student's parts, pass if the total reaches the pass mark."""
    tool = assessment.tool
    threshold = (
        config.pass_mark
        if config.pass_mark is not None
        else config.max * (config.pass_pct or Decimal(0)) / HUNDRED
    )
    passed = counted = 0
    for student in sorted(cells):
        entered = [
            c.value
            for part in assessment.parts
            if (c := cells[student].get(part.id)) is not None
            and c.state is State.ENTERED
            and c.value is not None
        ]
        if not entered:
            continue
        counted += 1
        if passes(sum(entered, Decimal(0)), threshold, config.boundary):
            passed += 1
    trace.add(
        "SingleTotal",
        tool,
        f"{passed} of {counted} students reach {threshold} of {config.max}",
        passed=passed,
        counted=counted,
        threshold=threshold,
    )
    return Decimal(passed) * HUNDRED / Decimal(counted) if counted else None
