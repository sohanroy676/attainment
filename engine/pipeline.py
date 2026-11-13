"""Builds and runs the step graph for a course or an offering (design 6.2).

A course run has two stages that the section roll-up also reuses:
  tool stage     marks -> percentage -> level per tool and CO
  combine stage  merge tools -> direct -> final -> course -> PO/PSO
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext

from .display import compared
from .errors import EngineError
from .hashing import input_hash, offering_input_hash
from .model import (
    AssessmentInput,
    CourseInput,
    CourseResult,
    CoValue,
    OfferingInput,
    ToolValue,
)
from .precision import CALCULATION_CONTEXT, ZERO
from .schema import MethodConfig, PerStudentAverageTool, QuestionWiseTool, SingleTotalTool
from .steps.bands import to_tool_value
from .steps.choice import choice_select
from .steps.combine import (
    average_ignore_blank,
    final_combine,
    merge_tools,
    weighted_combine,
)
from .steps.map_outcomes import map_to_outcomes
from .steps.normalise import normalise_states
from .steps.question import aggregate_to_co, evaluate_parts, student_level_percent
from .steps.student_level import per_student_average, single_total
from .steps.targets import near_target
from .trace import Trace

ENGINE_VERSION = "0.3.0"

ToolValues = dict[str, dict[str, ToolValue]]


@dataclass(frozen=True)
class RunOutput:
    result: CourseResult
    trace: Trace


@dataclass(frozen=True)
class OfferingOutput:
    """The course-level result of an offering, plus each section's own run."""

    result: CourseResult
    sections: Mapping[str, RunOutput]
    trace: Trace


# ---------------------------------------------------------------------------------------------
# one course (or one section)
# ---------------------------------------------------------------------------------------------
def run(method: MethodConfig, course: CourseInput) -> RunOutput:
    """Calculate one course. Pure: the same inputs always give the same output."""
    trace = Trace()
    with localcontext(CALCULATION_CONTEXT):
        tool_values = _tool_stage(method, course, trace)
        result = _combine_stage(
            method,
            _Frame(course.cos, course.indirect, course.target, course.mapping),
            tool_values,
            trace,
            input_hash(course),
        )
    return RunOutput(result, trace)


@dataclass(frozen=True)
class _Frame:
    """What the combine stage needs besides the tool values."""

    cos: tuple[str, ...]
    indirect: Mapping[str, Decimal]
    target: Decimal | None
    mapping: Mapping[str, Mapping[str, Decimal]]


def _tool_stage(method: MethodConfig, course: CourseInput, trace: Trace) -> ToolValues:
    return {
        name: _run_tool(name, config, course, method, trace)
        for name, config in method.tools.items()
    }


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
        if config.aggregate == "student_level":
            return student_level_percent(assessment, cells, config, course.cos, trace)
        return aggregate_to_co(name, parts, course.cos, trace, config.aggregate)
    if isinstance(config, PerStudentAverageTool):
        cells = normalise_states(assessment, config.absent, trace, whole_absent_as_cells=True)
        return _applied(
            per_student_average(assessment, cells, config, trace), config.applies_to, course.cos
        )
    if isinstance(config, SingleTotalTool):
        cells = normalise_states(assessment, config.absent, trace, whole_absent_as_cells=True)
        return _applied(
            single_total(assessment, cells, config, trace), config.applies_to, course.cos
        )
    raise EngineError(f"{name}: unsupported tool behaviour")


def _applied(
    percent: Decimal | None, applies_to: str | list[str], cos: tuple[str, ...]
) -> dict[str, Decimal | None]:
    chosen = cos if applies_to == "all_cos" else tuple(applies_to)
    return dict.fromkeys(chosen, percent)


def _as_co_value(value: ToolValue) -> CoValue:
    return CoValue(value.level, value.status, value.flag)


def _combine_stage(
    method: MethodConfig,
    frame: _Frame,
    tool_values: ToolValues,
    trace: Trace,
    hash_of_input: str,
) -> CourseResult:
    cos = frame.cos
    merged = {
        name: {
            co: merge_tools(
                name,
                co,
                [_as_co_value(tool_values[s][co]) for s in rule.sources],
                rule.method,
                trace,
            )
            for co in cos
        }
        for name, rule in method.merge.items()
    }
    inputs = {
        name: {
            co: merged[name][co] if name in merged else _as_co_value(tool_values[name][co])
            for co in cos
        }
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
        for co in cos
    }
    final = {
        co: final_combine(
            co,
            direct[co],
            frame.indirect.get(co),
            method.final.direct,
            method.final.indirect,
            trace,
        )
        for co in cos
    }
    return _course_result(method, frame, tool_values, merged, direct, final, trace, hash_of_input)


def _course_result(
    method: MethodConfig,
    frame: _Frame,
    tool_values: ToolValues,
    merged: dict[str, dict[str, CoValue]],
    direct: dict[str, CoValue],
    final: dict[str, CoValue],
    trace: Trace,
    hash_of_input: str,
) -> CourseResult:
    cos = frame.cos
    course_value = average_ignore_blank([final[co].value for co in cos])
    trace.add(
        "Average",
        "course",
        f"mean of {sum(1 for v in final.values() if v.value is not None)} of "
        f"{len(cos)} final CO values = {course_value}",
    )
    attained: bool | None = None
    flags = [
        f"{tv.tool}/{tv.co}: {tv.flag}"
        for per_tool in tool_values.values()
        for tv in per_tool.values()
        if tv.flag
    ] + [f"{co}: {v.note}" for co, v in final.items() if v.status == "blocked" and v.note]
    if course_value is not None and frame.target is not None:
        shown = compared(method.precision, "course", course_value)
        attained = shown >= frame.target
        margin = method.targets.near_target_margin
        trace.add(
            "TargetCompare",
            "course",
            f"{shown} {'>=' if attained else '<'} target {frame.target}"
            f" ({method.precision.compare_with})",
        )
        if near_target(shown, frame.target, margin):
            flags.append(f"course: within {margin} of the target ({shown} against {frame.target})")
    po = map_to_outcomes(final, frame.mapping, method.po.all_zero, trace) if frame.mapping else {}
    return CourseResult(
        tool_values=tool_values,
        merged=merged,
        direct=direct,
        final=final,
        course=course_value,
        course_status="ok" if course_value is not None else "no value",
        attained=attained,
        target=frame.target,
        complete=not any(v.status == "blocked" for v in [*final.values(), *po.values()]),
        flags=tuple(flags),
        engine_version=ENGINE_VERSION,
        input_hash=hash_of_input,
        po=po,
        indirect=dict(frame.indirect),
        indirect_source=method.final.indirect_source,
    )


# ---------------------------------------------------------------------------------------------
# sections of one offering into the course (RollUp)
# ---------------------------------------------------------------------------------------------
def run_offering(method: MethodConfig, offering: OfferingInput) -> OfferingOutput:
    """Calculate each section and roll them up into the course at the method's stage.

    stage `pct`        roll the tool percentages, then bands, then everything after
    stage `level`      roll the tool levels, then everything after
    stage `attainment` calculate each section fully, then roll the final CO values (default)
    `mean` is a plain mean over sections; `weighted_by_students` weights by enrolled students.
    """
    if not offering.sections:
        raise EngineError("an offering needs at least one section")
    trace = Trace()
    frame = _Frame(offering.cos, offering.indirect, offering.target, offering.mapping)
    with localcontext(CALCULATION_CONTEXT):
        sections: dict[str, RunOutput] = {}
        section_tools: dict[str, ToolValues] = {}
        for section_id, section in sorted(offering.sections.items()):
            section_trace = Trace()
            tools = _tool_stage(method, section, section_trace)
            section_tools[section_id] = tools
            result = _combine_stage(
                method,
                _Frame(offering.cos, offering.indirect, offering.target, offering.mapping),
                tools,
                section_trace,
                input_hash(section),
            )
            sections[section_id] = RunOutput(result, section_trace)
        weights = _weights(method, offering)
        stage = method.rollup.stage
        trace.add(
            "RollUp",
            "offering",
            f"{len(sections)} sections rolled up at stage '{stage}' ({method.rollup.method})",
        )
        rolled_tools = _roll_tools(method, section_tools, weights, offering.cos, stage, trace)
        hash_of_input = offering_input_hash(offering)
        if stage == "attainment":
            result = _roll_attainment(
                method, frame, sections, rolled_tools, weights, trace, hash_of_input
            )
        else:
            result = _combine_stage(method, frame, rolled_tools, trace, hash_of_input)
    return OfferingOutput(result, sections, trace)


def _weights(method: MethodConfig, offering: OfferingInput) -> dict[str, Decimal]:
    if method.rollup.method == "mean":
        return dict.fromkeys(offering.sections, Decimal(1))
    return {s: Decimal(len(c.students)) for s, c in offering.sections.items()}


def _weighted_mean(pairs: Sequence[tuple[Decimal | None, Decimal]]) -> Decimal | None:
    present = [(v, w) for v, w in pairs if v is not None]
    total = sum((w for _, w in present), ZERO)
    if not present or total == 0:
        return None
    return sum((v * w for v, w in present), ZERO) / total


def _roll_tools(
    method: MethodConfig,
    section_tools: Mapping[str, ToolValues],
    weights: Mapping[str, Decimal],
    cos: tuple[str, ...],
    stage: str,
    trace: Trace,
) -> ToolValues:
    rolled: ToolValues = {}
    for tool in method.tools:
        rolled[tool] = {}
        for co in cos:
            per_section = [(section_tools[s][tool][co], weights[s]) for s in sorted(section_tools)]
            percent = _weighted_mean([(tv.percent, w) for tv, w in per_section])
            if stage == "pct":
                rolled[tool][co] = to_tool_value(tool, co, percent, method.levels, trace)
                continue
            statuses = {tv.status for tv, _ in per_section}
            level = _weighted_mean([(tv.level, w) for tv, w in per_section])
            flag = None
            if "blocked" in statuses:
                status, level = "blocked", None
                flag = next(
                    (tv.flag for tv, _ in per_section if tv.status == "blocked" and tv.flag), None
                )
            else:
                status = "ok" if level is not None else "missing"
            rolled[tool][co] = ToolValue(tool, co, percent, level, status, flag)
    return rolled


def _roll_attainment(
    method: MethodConfig,
    frame: _Frame,
    sections: Mapping[str, RunOutput],
    rolled_tools: ToolValues,
    weights: Mapping[str, Decimal],
    trace: Trace,
    hash_of_input: str,
) -> CourseResult:
    order = sorted(sections)

    def roll(values: Sequence[CoValue], where: str) -> CoValue:
        if any(v.status == "blocked" for v in values):
            trace.add("RollUp", where, "a section is stopped for review: blocked")
            return CoValue(None, "blocked", "a section is stopped for review")
        value = _weighted_mean([(v.value, weights[s]) for v, s in zip(values, order, strict=True)])
        trace.add("RollUp", where, f"rolled over {len(order)} sections = {value}")
        return CoValue(value, "ok" if value is not None else "missing")

    results = [sections[s].result for s in order]
    merged = {
        name: {co: roll([r.merged[name][co] for r in results], f"{name}/{co}") for co in frame.cos}
        for name in method.merge
    }
    direct = {co: roll([r.direct[co] for r in results], f"direct/{co}") for co in frame.cos}
    final = {co: roll([r.final[co] for r in results], f"final/{co}") for co in frame.cos}
    return _course_result(method, frame, rolled_tools, merged, direct, final, trace, hash_of_input)
