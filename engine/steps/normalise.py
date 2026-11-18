"""NormaliseStates: decide what an absent mark means for a tool (design 6.3, R24).

`zero` counts the absence as a mark of 0, `exclude` (or `skip`) treats the item as not
attempted, `error` refuses to continue. Blank cells are never changed: blank is not absent.
"""

from collections.abc import Mapping

from ..errors import EngineError
from ..model import AssessmentInput, Cell, State
from ..trace import Trace

Cells = dict[str, dict[str, Cell]]


def normalise_states(
    assessment: AssessmentInput, absent_rule: str, trace: Trace, whole_absent_as_cells: bool
) -> Cells:
    """Return a copy of the marks with absent cells resolved by `absent_rule`.

    With `whole_absent_as_cells`, a student absent for the whole assessment has every cell
    treated as absent first (used by tools that have no separate whole-assessment rule).
    """
    resolved: Cells = {}
    changed = 0
    for student, row in assessment.marks.items():
        new_row: dict[str, Cell] = {}
        is_absent_whole = student in assessment.absent_whole
        whole = whole_absent_as_cells and is_absent_whole
        for part_id, cell in row.items():
            if whole:
                cell = Cell.absent()
            if is_absent_whole and not whole:
                cell = Cell.blank()  # marks of a student absent for everything never count
            if cell.state is State.ABSENT:
                changed += 1
                cell = _resolve_absent(cell, absent_rule, assessment.tool, student, part_id)
            new_row[part_id] = cell
        if whole:
            for part in assessment.parts:
                if part.id not in new_row:
                    new_row[part.id] = _resolve_absent(
                        Cell.absent(), absent_rule, assessment.tool, student, part.id
                    )
                    changed += 1
        resolved[student] = new_row
    trace.add(
        "NormaliseStates",
        assessment.tool,
        f"absent marks resolved with rule '{absent_rule}': {changed} cells",
        rule=absent_rule,
        cells=changed,
    )
    return resolved


def _resolve_absent(cell: Cell, rule: str, tool: str, student: str, part_id: str) -> Cell:
    if rule == "zero":
        return Cell.entered(0)
    if rule in {"exclude", "skip"}:
        return Cell.blank()
    raise EngineError(f"{tool}: student {student} is absent for {part_id} and the rule is 'error'")


def sat_students(
    assessment: AssessmentInput, cells: Mapping[str, Mapping[str, Cell]], whole_rule: str
) -> list[str]:
    """Students who sat the assessment: they have a mark row and are not absent for all of it.

    Under `count_as_fail` an absent student still counts in the denominator (and passes
    nothing); under `exclude` they are left out.
    """
    sat = []
    for student in cells:
        if student in assessment.absent_whole and whole_rule == "exclude":
            continue
        sat.append(student)
    return sat
