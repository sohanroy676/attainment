"""Reads a course's marks from JSON into engine input.

Format (numbers are read as exact decimals; a mark of 0 is an entered mark):

    {"cos": ["CO1"], "students": ["s1"], "target": 2.2, "indirect": {"CO1": 3},
     "overrides": [{"tool": "INT2", "part": "3a", "pass_mark": 2, "reason": "..."}],
     "assessments": {"INT1": {
        "parts": [{"id": "1a", "question": "1", "max": 3, "co": "CO1", "choice_group": null}],
        "absent_whole": ["s9"],
        "marks": {"s1": {"1a": 2.5}}}}}

A mark cell is a number (entered), null (blank) or "A" (absent). A part missing from a
student's row is blank.
"""

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from .errors import EngineError
from .model import AssessmentInput, Cell, CourseInput, Override, Part


def load_course(text: str) -> CourseInput:
    try:
        raw = json.loads(text, parse_float=Decimal)
        return _course(raw)
    except (KeyError, TypeError, ValueError, InvalidOperation, json.JSONDecodeError) as error:
        raise EngineError(f"marks file is not valid: {error!r}") from error


def _course(raw: dict[str, Any]) -> CourseInput:
    assessments = {tool: _assessment(tool, body) for tool, body in raw["assessments"].items()}
    overrides = {}
    for item in raw.get("overrides", []):
        if not str(item.get("reason", "")).strip():
            raise EngineError(f"override for {item['tool']}/{item['part']} needs a reason")
        overrides[(item["tool"], item["part"])] = Override(
            Decimal(item["pass_mark"]), item["reason"]
        )
    target = raw.get("target")
    return CourseInput(
        cos=tuple(raw["cos"]),
        students=tuple(raw["students"]),
        assessments=assessments,
        overrides=overrides,
        indirect={co: Decimal(v) for co, v in raw.get("indirect", {}).items()},
        target=None if target is None else Decimal(target),
    )


def _assessment(tool: str, body: dict[str, Any]) -> AssessmentInput:
    parts = tuple(
        Part(
            id=str(p["id"]),
            question=str(p.get("question", p["id"])),
            max=Decimal(p["max"]),
            co=p.get("co"),
            choice_group=p.get("choice_group"),
        )
        for p in body["parts"]
    )
    marks = {
        str(student): {part.id: _cell(row.get(part.id)) for part in parts}
        for student, row in body["marks"].items()
    }
    return AssessmentInput(tool, parts, marks, frozenset(body.get("absent_whole", [])))


def _cell(value: Any) -> Cell:
    if value is None:
        return Cell.blank()
    if value == "A":
        return Cell.absent()
    if isinstance(value, bool):
        raise EngineError("a mark cannot be true or false")
    return Cell.entered(Decimal(value))
