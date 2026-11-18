"""Reads marks, offerings and batches from JSON into engine input.

Course format (numbers are read as exact decimals; a mark of 0 is an entered mark):

    {"cos": ["CO1"], "students": ["s1"], "target": 2.2, "indirect": {"CO1": 3},
     "mapping": {"CO1": {"PO1": 2, "PO2": 0}},
     "overrides": [{"tool": "INT2", "part": "3a", "pass_mark": 2, "reason": "..."}],
     "assessments": {"INT1": {
        "parts": [{"id": "1a", "question": "1", "max": 3, "co": "CO1", "choice_group": null}],
        "absent_whole": ["s9"],
        "marks": {"s1": {"1a": 2.5}}}}}

A mark cell is a number (entered), null (blank) or "A" (absent). A part missing from a
student's row is blank. In `mapping`, a missing entry or null means "not mapped"; 0 is a mapping
of strength 0.

Offering format: the same top-level `cos`, `indirect`, `target` and `mapping`, with
`"sections": {"A": {"students": [...], "assessments": {...}, "overrides": [...]}, ...}`.

Batch format:

    {"outcomes": ["PO1"], "targets": {"PO1": 2.55}, "indirect": {"PO1": 3},
     "courses": [{"id": "c1", "name": "Course", "category": "core", "attained": true,
                  "po": {"PO1": 2.8, "PO2": null}}]}
"""

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from .batch import BatchCourse, BatchInput
from .errors import EngineError
from .model import AssessmentInput, Cell, CourseInput, OfferingInput, Override, Part

LOAD_ERRORS = (KeyError, TypeError, ValueError, InvalidOperation, json.JSONDecodeError)


def is_offering(text: str) -> bool:
    try:
        return "sections" in json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError:
        return False


def load_course(text: str) -> CourseInput:
    try:
        raw = json.loads(text, parse_float=Decimal)
        return _course(raw)
    except LOAD_ERRORS as error:
        raise EngineError(f"marks file is not valid: {error!r}") from error


def load_offering(text: str) -> OfferingInput:
    try:
        raw = json.loads(text, parse_float=Decimal)
        cos = tuple(raw["cos"])
        sections = {
            str(name): _course({**body, "cos": raw["cos"]})
            for name, body in raw["sections"].items()
        }
        return OfferingInput(
            cos=cos,
            sections=sections,
            indirect=_decimals(raw.get("indirect", {})),
            target=_optional(raw.get("target")),
            mapping=_mapping(raw.get("mapping", {})),
        )
    except LOAD_ERRORS as error:
        raise EngineError(f"offering file is not valid: {error!r}") from error


def load_batch(text: str) -> BatchInput:
    try:
        raw = json.loads(text, parse_float=Decimal)
        courses = tuple(
            BatchCourse(
                id=str(c["id"]),
                name=str(c.get("name", c["id"])),
                category=str(c.get("category", "")),
                po_values={po: _optional(v) for po, v in c["po"].items()},
                attained=c.get("attained"),
            )
            for c in raw["courses"]
        )
        return BatchInput(
            courses=courses,
            outcomes=tuple(raw["outcomes"]),
            targets=_decimals(raw.get("targets", {})),
            indirect=_decimals(raw.get("indirect", {})),
        )
    except LOAD_ERRORS as error:
        raise EngineError(f"batch file is not valid: {error!r}") from error


def _optional(value: Any) -> Decimal | None:
    return None if value is None or value == "" else Decimal(value)


def _decimals(raw: dict[str, Any]) -> dict[str, Decimal]:
    return {key: Decimal(value) for key, value in raw.items()}


def _mapping(raw: dict[str, dict[str, Any]]) -> dict[str, dict[str, Decimal]]:
    return {
        co: {po: Decimal(v) for po, v in row.items() if v is not None} for co, row in raw.items()
    }


def _course(raw: dict[str, Any]) -> CourseInput:
    assessments = {tool: _assessment(tool, body) for tool, body in raw["assessments"].items()}
    overrides = {}
    for item in raw.get("overrides", []):
        if not str(item.get("reason", "")).strip():
            raise EngineError(f"override for {item['tool']}/{item['part']} needs a reason")
        overrides[(item["tool"], item["part"])] = Override(
            Decimal(item["pass_mark"]), item["reason"]
        )
    return CourseInput(
        cos=tuple(raw["cos"]),
        students=tuple(raw["students"]),
        assessments=assessments,
        overrides=overrides,
        indirect=_decimals(raw.get("indirect", {})),
        target=_optional(raw.get("target")),
        mapping=_mapping(raw.get("mapping", {})),
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
