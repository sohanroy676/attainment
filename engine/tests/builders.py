"""Helpers that build methods and marks for tests. Synthetic data only."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from decimal import Decimal
from typing import Any

from engine.model import AssessmentInput, Cell, CourseInput, Part
from engine.schema import MethodConfig

BANDS = [
    {"min_pct": 60, "level": 3, "label": "L3"},
    {"min_pct": 50, "level": 2, "label": "L2"},
    {"min_pct": 10, "level": 1, "label": "L1"},
]

BASE_METHOD: dict[str, Any] = {
    "schema": "attainment-method/1",
    "name": "Test method",
    "levels": {"bands": BANDS, "below_lowest": {"flag": True, "value_for_calc": "block"}},
    "missing_data": "block",
    "precision": {"default": {"mode": "truncate", "places": 2}, "compare_with": "unrounded"},
    "tools": {
        "INT1": {"behaviour": "question_wise", "pass_pct": 60, "boundary": ">="},
        "INT2": {"behaviour": "question_wise", "pass_pct": 60, "boundary": ">="},
        "SEE": {"behaviour": "question_wise", "pass_pct": 60, "boundary": ">="},
        "QUIZ": {"behaviour": "per_student_average", "max": 5, "pass_pct": 60, "absent": "zero"},
        "ASSIGN": {"behaviour": "per_student_average", "max": 5, "pass_pct": 60, "absent": "zero"},
    },
    "merge": {"INTERNAL": {"from": ["INT1", "INT2"], "method": "average"}},
    "direct": {"INTERNAL": "0.30", "ASSIGN": "0.05", "QUIZ": "0.05", "SEE": "0.60"},
    "final": {"direct": "0.8", "indirect": "0.2"},
}


def method(**changes: Any) -> MethodConfig:
    """BASE_METHOD with top-level keys replaced; a value of None removes the key."""
    raw = deepcopy(BASE_METHOD)
    for key, value in changes.items():
        if value is None:
            raw.pop(key, None)
        else:
            raw[key] = value
    return MethodConfig.model_validate(raw)


def simple_method(
    tools: Mapping[str, dict[str, Any]], direct: Mapping[str, str], **extra: Any
) -> MethodConfig:
    raw = deepcopy(BASE_METHOD)
    raw["tools"] = dict(tools)
    raw["direct"] = dict(direct)
    raw["merge"] = {}
    raw.update(extra)
    return MethodConfig.model_validate(raw)


def parts(
    spec: Sequence[tuple[str, str, int | str, str | None, str | None]],
) -> tuple[Part, ...]:
    """(id, question, max, co, choice_group) -> Part."""
    return tuple(Part(i, q, Decimal(m), c, g) for i, q, m, c, g in spec)


def cells(row: Mapping[str, Any]) -> dict[str, Cell]:
    """number -> entered, None -> blank, 'A' -> absent."""
    out: dict[str, Cell] = {}
    for part, value in row.items():
        if value is None:
            out[part] = Cell.blank()
        elif value == "A":
            out[part] = Cell.absent()
        else:
            out[part] = Cell.entered(str(value))
    return out


def assessment(
    tool: str,
    part_list: tuple[Part, ...],
    rows: Mapping[str, Any],
    absent_whole: frozenset[str] = frozenset(),
) -> AssessmentInput:
    return AssessmentInput(tool, part_list, {s: cells(r) for s, r in rows.items()}, absent_whole)


def course(
    assessments: list[AssessmentInput],
    cos: tuple[str, ...] = ("CO1",),
    students: tuple[str, ...] | None = None,
    indirect: Mapping[str, str] | None = None,
    target: str | None = None,
    overrides: Mapping[tuple[str, str], Any] | None = None,
) -> CourseInput:
    everyone = students or tuple(sorted({s for a in assessments for s in a.marks}))
    return CourseInput(
        cos=cos,
        students=everyone,
        assessments={a.tool: a for a in assessments},
        overrides=dict(overrides or {}),
        indirect={co: Decimal(v) for co, v in (indirect or {}).items()},
        target=None if target is None else Decimal(target),
    )


def class_with_pass_rate(tool: str, passed: int, total: int, max_mark: int = 10) -> AssessmentInput:
    """One-part assessment where exactly `passed` of `total` students reach 60% of max."""
    rows = {f"s{i}": {"p": max_mark if i < passed else 0} for i in range(total)}
    return assessment(tool, parts([("p", "1", max_mark, "CO1", None)]), rows)
