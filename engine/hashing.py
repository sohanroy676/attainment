"""Stable hashes of inputs and outputs (design 6.1: same input, same output, byte for byte)."""

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .model import CourseInput, CourseResult
from .precision import decimal_text


def _digest(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def input_hash(course: CourseInput) -> str:
    """Hash of everything that can change a result."""
    assessments = {
        tool: {
            "parts": [
                [p.id, p.question, decimal_text(p.max), p.co, p.choice_group] for p in a.parts
            ],
            "absent_whole": sorted(a.absent_whole),
            "marks": {
                student: {
                    part: [cell.state.value, decimal_text(cell.value)] for part, cell in row.items()
                }
                for student, row in a.marks.items()
            },
        }
        for tool, a in course.assessments.items()
    }
    return _digest(
        {
            "cos": list(course.cos),
            "students": sorted(course.students),
            "assessments": assessments,
            "overrides": {
                f"{tool}/{part}": [decimal_text(o.pass_mark), o.reason]
                for (tool, part), o in course.overrides.items()
            },
            "indirect": {co: decimal_text(v) for co, v in course.indirect.items()},
            "target": decimal_text(course.target),
        }
    )


def result_to_dict(result: CourseResult) -> dict[str, Any]:
    def co_values(values: Mapping[str, Any]) -> dict[str, Any]:
        return {co: [decimal_text(v.value), v.status, v.note] for co, v in sorted(values.items())}

    return {
        "engine_version": result.engine_version,
        "input_hash": result.input_hash,
        "tools": {
            tool: {
                co: [decimal_text(v.percent), decimal_text(v.level), v.status, v.flag]
                for co, v in sorted(per_co.items())
            }
            for tool, per_co in sorted(result.tool_values.items())
        },
        "merged": {name: co_values(per_co) for name, per_co in sorted(result.merged.items())},
        "direct": co_values(result.direct),
        "final": co_values(result.final),
        "course": decimal_text(result.course),
        "attained": result.attained,
        "target": decimal_text(result.target),
        "complete": result.complete,
        "flags": list(result.flags),
    }


def output_hash(result: CourseResult) -> str:
    return _digest(result_to_dict(result))
