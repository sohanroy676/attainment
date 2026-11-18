"""Builds and runs the step graph for one course from a validated method (design 6.2)."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .errors import EngineError
from .hashing import input_hash
from .model import AssessmentInput, CourseInput, CourseResult, CoValue, ToolValue
from .precision import CALCULATION_CONTEXT, quantize
from .schema import MethodConfig, PerStudentAverageTool, QuestionWiseTool, SingleTotalTool
from .steps.bands import to_tool_value
from .steps.choice import choice_select
from .steps.combine import (
    average_ignore_blank,
    final_combine,
    merge_tools,
    weighted_combine,
)
from .steps.normalise import normalise_states
from .steps.question import aggregate_to_co, evaluate_parts
from .steps.student_level import per_student_average, single_total
from .trace import Trace

ENGINE_VERSION = "0.2.0"


@dataclass(frozen=True)
class RunOutput:
    result: CourseResult
    trace: Trace


def run(method: MethodConfig, course: CourseInput) -> RunOutput:
    """Calculate one course. Pure: the same inputs always give the same output."""
    trace = Trace()
    with localcontext(CALCULATION_CONTEXT):
        tool_values = {
            name: _run_tool(name, config, course, method, trace)
            for name, config in method.tools.items()
        }
        merged = {
            name: {
                co: merge_tools(
                    name,
                    co,
                    [_as_co_value(tool_values[s][co]) for s in rule.sources],
                    rule.method,
                    trace,
                )
                for co in course.cos
            }
            for name, rule in method.merge.items()
        }
        inputs = {
            name: {co: _input_value(name, co, tool_values, merged) for co in course.cos}
            for name in method.direct
        }
        direct = {
            co: weighted_combine(
                co,
                method.direct,
                {name: inputs[name][co] for name in method.direct},
                method.missing_data,
                trace,
            )
            for co in course.cos
        }
        final = {
            co: final_combine(
                co,
                direct[co],
                course.indirect.get(co),
                method.final.direct,
                method.final.indirect,
                trace,
            )
            for co in course.cos
        }
        result = _course_result(method, course, tool_values, merged, direct, final, trace)
    return RunOutput(result, trace)


def _run_tool(
    name: str, config: object, course: CourseInput, method: MethodConfig, trace: Trace
) -> dict[str, ToolValue]:
    assessment = course.assessments.get(name)
    if assessment is None:
        trace.add("Input", name, "no marks supplied for this tool")
        return {co: ToolValue(name, co, None, None, "missing") for co in course.cos}
    for part in assessment.parts:
        if part.co is not None and part.co not in course.cos:
            raise EngineError(f"{name}: part {part.id} is tagged to unknown outcome {part.co}")
    percents = _percents(name, config, assessment, course, trace)
    return {
        co: to_tool_value(name, co, percents.get(co), method.levels, trace) for co in course.cos
    }


def _percents(
    name: str, config: object, assessment: AssessmentInput, course: CourseInput, trace: Trace
) -> dict[str, Decimal | None]:
    if isinstance(config, QuestionWiseTool):
        cells = normalise_states(assessment, config.absent, trace, whole_absent_as_cells=False)
        cells = choice_select(assessment, cells, config.choice, trace)
        parts = evaluate_parts(
            assessment, cells, config, dict(course.overrides), len(course.students), trace
        )
        return aggregate_to_co(name, parts, course.cos, trace)
    if isinstance(config, PerStudentAverageTool):
        cells = normalise_states(assessment, config.absent, trace, whole_absent_as_cells=True)
        return _applied(
            per_student_average(assessment, cells, config, trace), config.applies_to, course
        )
    if isinstance(config, SingleTotalTool):
        cells = normalise_states(assessment, config.absent, trace, whole_absent_as_cells=True)
        return _applied(single_total(assessment, cells, config, trace), config.applies_to, course)
    raise EngineError(f"{name}: unsupported tool behaviour")


def _applied(
    percent: Decimal | None, applies_to: str | list[str], course: CourseInput
) -> dict[str, Decimal | None]:
    cos = course.cos if applies_to == "all_cos" else tuple(applies_to)
    return dict.fromkeys(cos, percent)


def _as_co_value(value: ToolValue) -> CoValue:
    return CoValue(value.level, value.status, value.flag)


def _input_value(
    name: str,
    co: str,
    tool_values: dict[str, dict[str, ToolValue]],
    merged: dict[str, dict[str, CoValue]],
) -> CoValue:
    if name in merged:
        return merged[name][co]
    return _as_co_value(tool_values[name][co])


def _course_result(
    method: MethodConfig,
    course: CourseInput,
    tool_values: dict[str, dict[str, ToolValue]],
    merged: dict[str, dict[str, CoValue]],
    direct: dict[str, CoValue],
    final: dict[str, CoValue],
    trace: Trace,
) -> CourseResult:
    course_value = average_ignore_blank([final[co].value for co in course.cos])
    attained: bool | None = None
    if course_value is not None and course.target is not None:
        compared = course_value
        if method.precision.compare_with == "displayed":
            rule = method.precision.course or method.precision.default
            compared = quantize(course_value, rule.places, rule.mode)
        attained = compared >= course.target
    blocked = any(v.status == "blocked" for v in final.values())
    flags = [
        f"{tv.tool}/{tv.co}: {tv.flag}"
        for per_tool in tool_values.values()
        for tv in per_tool.values()
        if tv.flag
    ] + [f"{co}: {v.note}" for co, v in final.items() if v.status == "blocked" and v.note]
    trace.add(
        "Average",
        "course",
        f"mean of {sum(1 for v in final.values() if v.value is not None)} of "
        f"{len(course.cos)} final CO values = {course_value}",
    )
    return CourseResult(
        tool_values=tool_values,
        merged=merged,
        direct=direct,
        final=final,
        course=course_value,
        course_status="ok" if course_value is not None else "no value",
        attained=attained,
        target=course.target,
        complete=not blocked,
        flags=tuple(flags),
        engine_version=ENGINE_VERSION,
        input_hash=input_hash(course),
    )
