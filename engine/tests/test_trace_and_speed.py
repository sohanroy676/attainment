"""A11 trace completeness and A12 speed."""

import random
import time
from decimal import Decimal

import pytest

from engine.batch import BatchInput, course_for_batch, run_batch
from engine.model import AssessmentInput, CourseInput
from engine.pipeline import run

from .builders import assessment, course, method, parts

D = Decimal


def _marks_tool(
    name: str, n_parts: int, cos: int, choice: bool, rng: random.Random
) -> AssessmentInput:
    spec = [
        (
            f"{name}{i}",
            str(i // 2 + 1),
            4,
            f"CO{i % cos + 1}",
            "G" if choice and i >= n_parts // 2 else None,
        )
        for i in range(n_parts)
    ]
    rows = {
        f"s{s}": {
            f"{name}{i}": (rng.choice([None, 0, 1, 2, 3, 4]) if choice else rng.randint(0, 4))
            for i in range(n_parts)
        }
        for s in range(67)
    }
    return assessment(name, parts(spec), rows)


def _items(name: str, rng: random.Random) -> AssessmentInput:
    spec = [(f"{name}{i}", str(i), 5, None, None) for i in range(3)]
    rows = {f"s{s}": {f"{name}{i}": rng.randint(0, 5) for i in range(3)} for s in range(67)}
    return assessment(name, parts(spec), rows)


def deep_learning_sized_course(seed: int) -> CourseInput:
    """67 students; Internal-I 14 parts, Internal-II 12, SEE 25, quiz and assignment 3 items."""
    rng = random.Random(seed)
    cos = tuple(f"CO{i}" for i in range(1, 6))
    base = course(
        [
            _marks_tool("INT1", 14, 2, False, rng),
            _marks_tool("INT2", 12, 3, False, rng),
            _marks_tool("SEE", 25, 5, True, rng),
            _items("QUIZ", rng),
            _items("ASSIGN", rng),
        ],
        cos=cos,
        indirect=dict.fromkeys(cos, "3"),
        target="2.2",
    )
    mapping = {co: {"PO1": D(2), "PO2": D(1), "PSO1": D(3)} for co in cos}
    return CourseInput(base.cos, base.students, base.assessments, indirect=base.indirect,
                       target=base.target, mapping=mapping)  # fmt: skip


@pytest.mark.unit
def test_a11_every_output_value_has_a_trace_entry() -> None:
    out = run(method(missing_data="renormalise"), deep_learning_sized_course(1))
    r, keys = out.result, {(e.step, e.key) for e in out.trace.entries}
    for tool, per_co in r.tool_values.items():
        for co in per_co:
            assert ("Bands", f"{tool}/{co}") in keys
    for name, merged_cos in r.merged.items():
        for co in merged_cos:
            assert ("MergeTools", f"{name}/{co}") in keys
    for co in r.direct:
        assert ("WeightedCombine", f"direct/{co}") in keys
        assert ("WeightedCombine", f"final/{co}") in keys
    assert ("Average", "course") in keys and ("TargetCompare", "course") in keys
    for outcome in r.po:
        assert ("MapToOutcomes", outcome) in keys


@pytest.mark.unit
def test_a11_each_trace_entry_names_its_inputs_rule_counts_and_output() -> None:
    out = run(method(missing_data="renormalise"), deep_learning_sized_course(1))
    question = next(e for e in out.trace.entries if e.step == "QuestionPass")
    for field in ("passed", "denominator", "attempted", "sat", "threshold"):
        assert field in question.data
    assert "passed at" in question.message
    band = next(e for e in out.trace.entries if e.step == "Bands")
    assert "band from" in band.message or "below" in band.message


@pytest.mark.unit
def test_a11_batch_outcomes_and_counts_are_traced() -> None:
    result = run(method(missing_data="renormalise"), deep_learning_sized_course(2)).result
    batch = BatchInput(
        (course_for_batch("c", "C", "core", result),), tuple(result.po),
        {po: D("2.5") for po in result.po}, {po: D(3) for po in result.po},
    )  # fmt: skip
    keys = {(e.step, e.key) for e in run_batch(method(), batch).trace.entries}
    for outcome in result.po:
        assert ("BatchRollUp", outcome) in keys and ("BatchTotal", outcome) in keys
        assert ("TargetCompare", outcome) in keys
    assert ("CountStatus", "core") in keys


@pytest.mark.perf
def test_a12_one_course_runs_in_under_100_ms() -> None:
    data = deep_learning_sized_course(3)
    m = method(missing_data="renormalise")
    run(m, data)  # warm up imports and caches
    start = time.perf_counter()
    for _ in range(5):
        run(m, data)
    per_run = (time.perf_counter() - start) / 5
    assert per_run < 0.1, f"{per_run * 1000:.1f} ms per course"


@pytest.mark.perf
def test_a12_a_100_course_batch_runs_in_under_2_seconds() -> None:
    m = method(missing_data="renormalise")
    courses = [deep_learning_sized_course(seed) for seed in range(100)]
    start = time.perf_counter()
    entries = [
        course_for_batch(f"c{i}", f"C{i}", "core" if i % 2 else "non_core", run(m, c).result)
        for i, c in enumerate(courses)
    ]
    outcomes = tuple(entries[0].po_values)
    batch = BatchInput(
        tuple(entries), outcomes, {po: D("2.5") for po in outcomes}, {po: D(3) for po in outcomes}
    )
    result = run_batch(m, batch).result
    elapsed = time.perf_counter() - start
    assert result.outcomes["PO1"].courses_with_value == 100
    assert elapsed < 2.0, f"{elapsed:.2f} s for 100 courses and the batch"
