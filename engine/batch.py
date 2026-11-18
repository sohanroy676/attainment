"""Batch roll-up (design 6.2 steps 12 to 15): PO and PSO values over all courses of a batch.

Direct   = simple average of the course values for that outcome (equal weight). A course with
           no value is skipped; a course with 0 counts as 0.
Total    = direct weight x direct + indirect weight x indirect (the indirect value is entered).
Status   = total compared with the outcome's target, unrounded unless the method says displayed.
Counts   = courses attained and not attained, by category (core and non-core).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

from .display import compared
from .hashing import digest_of
from .model import CourseResult
from .pipeline import ENGINE_VERSION
from .precision import CALCULATION_CONTEXT, ZERO, decimal_text
from .schema import MethodConfig
from .steps.targets import near_target
from .trace import Trace


@dataclass(frozen=True)
class BatchCourse:
    """One course's outcome values as they enter the batch."""

    id: str
    name: str
    category: str  # for example "core" or "non_core"
    po_values: Mapping[str, Decimal | None]  # blank (None) is skipped; 0 counts
    attained: bool | None = None


@dataclass(frozen=True)
class BatchInput:
    courses: tuple[BatchCourse, ...]
    outcomes: tuple[str, ...]  # PO1 .. PO12, PSO1 .. PSO3, in report order
    targets: Mapping[str, Decimal]
    indirect: Mapping[str, Decimal]  # entered per outcome


@dataclass(frozen=True)
class OutcomeBatchValue:
    outcome: str
    courses_with_value: int
    direct: Decimal | None
    indirect: Decimal | None
    total: Decimal | None
    target: Decimal | None
    attained: bool | None
    status: str  # "ok", "missing" (no course has a value), "blocked" (no indirect value)
    flag: str | None = None


@dataclass(frozen=True)
class CountStatus:
    category: str
    attained: int
    not_attained: int
    no_result: int


@dataclass(frozen=True)
class BatchResult:
    outcomes: Mapping[str, OutcomeBatchValue]
    counts: Mapping[str, CountStatus]
    complete: bool
    flags: tuple[str, ...]
    engine_version: str
    input_hash: str


@dataclass(frozen=True)
class BatchOutput:
    result: BatchResult
    trace: Trace


def course_for_batch(course_id: str, name: str, category: str, result: CourseResult) -> BatchCourse:
    """Take an engine course result into the batch (its PO and PSO values and its status)."""
    return BatchCourse(
        course_id, name, category, {po: v.value for po, v in result.po.items()}, result.attained
    )


def run_batch(method: MethodConfig, batch: BatchInput) -> BatchOutput:
    trace = Trace()
    flags: list[str] = []
    with localcontext(CALCULATION_CONTEXT):
        outcomes = {
            outcome: _outcome(method, batch, outcome, trace, flags) for outcome in batch.outcomes
        }
        counts = _count_status(batch, trace)
    result = BatchResult(
        outcomes=outcomes,
        counts=counts,
        complete=all(v.status != "blocked" for v in outcomes.values()),
        flags=tuple(flags),
        engine_version=ENGINE_VERSION,
        input_hash=batch_input_hash(batch),
    )
    return BatchOutput(result, trace)


def _outcome(
    method: MethodConfig, batch: BatchInput, outcome: str, trace: Trace, flags: list[str]
) -> OutcomeBatchValue:
    values = [c.po_values[outcome] for c in batch.courses if c.po_values.get(outcome) is not None]
    target = batch.targets.get(outcome)
    indirect = batch.indirect.get(outcome)
    if not values:
        trace.add("BatchRollUp", outcome, "no course has a value for this outcome")
        return OutcomeBatchValue(outcome, 0, None, indirect, None, target, None, "missing")
    direct = sum((v for v in values if v is not None), ZERO) / Decimal(len(values))
    trace.add(
        "BatchRollUp",
        outcome,
        f"simple average of {len(values)} course values = {direct}",
        courses=len(values),
    )
    weights = method.batch
    if weights.indirect != 0 and indirect is None:
        trace.add("BatchRollUp", outcome, "no indirect value entered: stopped for review")
        return OutcomeBatchValue(outcome, len(values), direct, None, None, target, None, "blocked")
    total = weights.direct * direct + weights.indirect * (indirect or ZERO)
    trace.add(
        "BatchTotal",
        outcome,
        f"{weights.direct} x direct {direct} + {weights.indirect} x indirect {indirect} = {total}",
    )
    attained: bool | None = None
    flag = None
    if target is not None:
        shown = compared(method.precision, "batch", total)
        attained = shown >= target
        trace.add(
            "TargetCompare",
            outcome,
            f"{shown} {'>=' if attained else '<'} target {target}"
            f" ({method.precision.compare_with})",
        )
        margin = method.targets.near_target_margin
        if near_target(shown, target, margin):
            flag = f"within {margin} of the target ({shown} against {target})"
            flags.append(f"{outcome}: {flag}")
    return OutcomeBatchValue(
        outcome, len(values), direct, indirect, total, target, attained, "ok", flag
    )


def _count_status(batch: BatchInput, trace: Trace) -> dict[str, CountStatus]:
    tally: dict[str, list[int]] = {}
    for course in batch.courses:
        row = tally.setdefault(course.category, [0, 0, 0])
        row[0 if course.attained is True else 1 if course.attained is False else 2] += 1
    counts = {
        category: CountStatus(category, a, n, x) for category, (a, n, x) in sorted(tally.items())
    }
    for category, c in counts.items():
        trace.add(
            "CountStatus",
            category,
            f"{c.attained} attained, {c.not_attained} not attained, {c.no_result} without a result",
        )
    return counts


def batch_input_hash(batch: BatchInput) -> str:
    return digest_of(
        {
            "courses": [
                [
                    c.id,
                    c.name,
                    c.category,
                    {po: decimal_text(v) for po, v in sorted(c.po_values.items())},
                    c.attained,
                ]
                for c in batch.courses
            ],
            "outcomes": list(batch.outcomes),
            "targets": {k: decimal_text(v) for k, v in sorted(batch.targets.items())},
            "indirect": {k: decimal_text(v) for k, v in sorted(batch.indirect.items())},
        }
    )


def batch_result_to_dict(result: BatchResult) -> dict[str, Any]:
    return {
        "engine_version": result.engine_version,
        "input_hash": result.input_hash,
        "outcomes": {
            o: [
                v.courses_with_value,
                decimal_text(v.direct),
                decimal_text(v.indirect),
                decimal_text(v.total),
                decimal_text(v.target),
                v.attained,
                v.status,
                v.flag,
            ]
            for o, v in result.outcomes.items()
        },
        "counts": {c: [v.attained, v.not_attained, v.no_result] for c, v in result.counts.items()},
        "complete": result.complete,
        "flags": list(result.flags),
    }


def batch_output_hash(result: BatchResult) -> str:
    return digest_of(batch_result_to_dict(result))
