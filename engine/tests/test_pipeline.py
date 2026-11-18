"""Pipeline tests: the float trap, merge, missing data, determinism, the explanation trace."""

from decimal import Decimal

import pytest

from engine.hashing import input_hash, output_hash
from engine.model import CourseInput
from engine.pipeline import run
from engine.precision import quantize
from engine.schema import MethodConfig

from .builders import assessment, class_with_pass_rate, course, method, parts, simple_method

pytestmark = pytest.mark.unit


def _levels_course(levels: dict[str, int], indirect: str = "3") -> CourseInput:
    """Each tool is a one-part paper whose class pass rate gives exactly the wanted level."""
    pass_of_ten = {3: 10, 2: 5}  # 100% -> level 3, 50% -> level 2
    return course(
        [class_with_pass_rate(tool, pass_of_ten[level], 10) for tool, level in levels.items()],
        indirect={"CO1": indirect},
    )


def _single_part_tools() -> dict[str, dict[str, object]]:
    return {
        name: {"behaviour": "question_wise", "pass_pct": 60}
        for name in ("INTERNAL", "ASSIGN", "QUIZ", "SEE")
    }


def _direct_method() -> MethodConfig:
    return simple_method(
        _single_part_tools(), {"INTERNAL": "0.30", "ASSIGN": "0.05", "QUIZ": "0.05", "SEE": "0.60"}
    )


def test_a7_float_trap_final_co_is_2_52_not_2_51() -> None:
    data = _levels_course({"INTERNAL": 3, "SEE": 2, "QUIZ": 3, "ASSIGN": 3})
    out = run(_direct_method(), data)
    assert out.result.direct["CO1"].value == Decimal("2.4")
    final = out.result.final["CO1"].value
    assert final == Decimal("2.52")
    assert quantize(final, 2, "truncate") == Decimal("2.52")
    assert 0.8 * (0.30 * 3 + 0.05 * 3 + 0.05 * 3 + 0.60 * 2) + 0.2 * 3 != 2.52  # float breaks


def test_course_attainment_compares_the_unrounded_value_with_the_target() -> None:
    data = _levels_course({"INTERNAL": 3, "SEE": 2, "QUIZ": 3, "ASSIGN": 3})
    met = run(
        _direct_method(),
        course(list(data.assessments.values()), indirect={"CO1": "3"}, target="2.52"),
    )
    assert met.result.course == Decimal("2.52") and met.result.attained is True
    missed = run(
        _direct_method(),
        course(list(data.assessments.values()), indirect={"CO1": "3"}, target="2.53"),
    )
    assert missed.result.attained is False


def test_compare_with_displayed_uses_the_truncated_value() -> None:
    tools = {"T": {"behaviour": "question_wise", "pass_pct": 60}}
    shown = simple_method(
        tools, {"T": "1"}, final={"direct": "0.9", "indirect": "0.1"},
        precision={"default": {"mode": "truncate", "places": 1}, "compare_with": "displayed"},
    )  # fmt: skip
    data = course([class_with_pass_rate("T", 10, 10)], indirect={"CO1": "2.5"}, target="2.8")
    # unrounded 0.9 x 3 + 0.1 x 2.5 = 2.95, displayed (truncated to 1 place) 2.9; target 2.8 is met
    assert run(shown, data).result.course == Decimal("2.95")
    data_hi = course([class_with_pass_rate("T", 10, 10)], indirect={"CO1": "2.5"}, target="2.95")
    assert run(shown, data_hi).result.attained is False  # displayed 2.9 < 2.95


# A12 -------------------------------------------------------
def test_a12_merge_of_level_3_and_level_2_is_2_5() -> None:
    cfg = {"behaviour": "question_wise", "pass_pct": 60}
    merged = simple_method(
        {"INT1": cfg, "INT2": cfg},
        {"INTERNAL": "1"},
        merge={"INTERNAL": {"from": ["INT1", "INT2"]}},
    )
    data = course([class_with_pass_rate("INT1", 10, 10), class_with_pass_rate("INT2", 5, 10)])
    out = run(merged, data)
    assert out.result.merged["INTERNAL"]["CO1"].value == Decimal("2.5")


def test_merge_uses_the_one_tool_that_covers_the_co() -> None:
    cfg = {"behaviour": "question_wise", "pass_pct": 60}
    merged = simple_method(
        {"INT1": cfg, "INT2": cfg},
        {"INTERNAL": "1"},
        merge={"INTERNAL": {"from": ["INT1", "INT2"]}},
    )
    only_first = assessment("INT1", parts([("a", "1", 10, "CO1", None)]), {"s": {"a": 10}})
    only_second = assessment("INT2", parts([("b", "1", 10, "CO2", None)]), {"s": {"b": 10}})
    out = run(
        merged,
        course([only_first, only_second], cos=("CO1", "CO2"), indirect={"CO1": "3", "CO2": "3"}),
    )
    assert out.result.merged["INTERNAL"]["CO1"].value == 3
    assert out.result.merged["INTERNAL"]["CO2"].value == 3


# A11 -------------------------------------------------------
def _missing_setup(rule: str) -> tuple[MethodConfig, CourseInput]:
    cfg = {"behaviour": "question_wise", "pass_pct": 60}
    m = simple_method({"A": cfg, "B": cfg}, {"A": "0.5", "B": "0.5"}, missing_data=rule)
    a = assessment(
        "A", parts([("a1", "1", 10, "CO1", None), ("a2", "2", 10, "CO2", None)]),
        {"s": {"a1": 10, "a2": 10}},
    )  # fmt: skip
    b = assessment("B", parts([("b1", "1", 10, "CO1", None)]), {"s": {"b1": 10}})
    return m, course([a, b], cos=("CO1", "CO2"), indirect={"CO1": "3", "CO2": "3"})


def test_a11_missing_data_block_is_the_default_and_makes_the_run_provisional() -> None:
    m, data = _missing_setup("block")
    out = run(m, data)
    assert out.result.direct["CO1"].value == 3
    assert out.result.direct["CO2"].status == "blocked"
    assert out.result.complete is False
    assert "no value from B" in out.trace.text()


def test_a11_renormalise_gives_the_remaining_tool_the_whole_weight() -> None:
    m, data = _missing_setup("renormalise")
    out = run(m, data)
    assert out.result.direct["CO2"].value == 3 and out.result.complete is True


def test_a11_zero_counts_the_missing_tool_as_level_zero() -> None:
    m, data = _missing_setup("zero")
    out = run(m, data)
    assert out.result.direct["CO2"].value == Decimal("1.5")


def test_a_tool_with_no_marks_at_all_is_missing_for_every_co() -> None:
    cfg = {"behaviour": "question_wise", "pass_pct": 60}
    m = simple_method({"A": cfg, "B": cfg}, {"A": "0.5", "B": "0.5"}, missing_data="renormalise")
    data = course([class_with_pass_rate("A", 10, 10)], indirect={"CO1": "3"})
    out = run(m, data)
    assert out.result.tool_values["B"]["CO1"].status == "missing"
    assert out.result.direct["CO1"].value == 3  # renormalised onto A


def test_missing_indirect_value_stops_the_final_co_for_review() -> None:
    out = run(
        _direct_method(), _levels_course({"INTERNAL": 3, "SEE": 3, "QUIZ": 3, "ASSIGN": 3}, "3")
    )
    assert out.result.final["CO1"].status == "ok"
    no_indirect = course(
        list(_levels_course({"INTERNAL": 3, "SEE": 3, "QUIZ": 3, "ASSIGN": 3}).assessments.values())
    )
    blocked = run(_direct_method(), no_indirect)
    assert blocked.result.final["CO1"].status == "blocked" and blocked.result.complete is False
    assert blocked.result.direct["CO1"].value == 3  # direct-only is still shown


def test_course_attainment_ignores_cos_with_no_value() -> None:
    cfg = {"behaviour": "question_wise", "pass_pct": 60}
    m = simple_method(
        {"A": cfg}, {"A": "1"}, final={"direct": "1", "indirect": "0"}, missing_data="renormalise"
    )
    a = assessment("A", parts([("p", "1", 10, "CO1", None)]), {"s": {"p": 10}})
    out = run(m, course([a], cos=("CO1", "CO2")))
    assert out.result.final["CO2"].value is None
    assert out.result.course == 3


# A15 -------------------------------------------------------
def test_a15_same_input_twice_gives_identical_output_and_hash() -> None:
    data = _levels_course({"INTERNAL": 3, "SEE": 2, "QUIZ": 3, "ASSIGN": 3})
    first = run(_direct_method(), data)
    second = run(_direct_method(), data)
    assert output_hash(first.result) == output_hash(second.result)
    assert first.result.input_hash == second.result.input_hash == input_hash(data)
    assert first.trace.text() == second.trace.text()


def test_a15_changing_one_mark_changes_the_input_hash() -> None:
    one = course([class_with_pass_rate("T", 5, 10)])
    other = course([class_with_pass_rate("T", 6, 10)])
    assert input_hash(one) != input_hash(other)


def test_a15_student_order_does_not_change_the_result() -> None:
    paper = parts([("p", "1", 10, "CO1", None)])
    rows = {f"s{i}": {"p": 10 if i % 2 else 0} for i in range(8)}
    forward = assessment("T", paper, rows)
    backward = assessment("T", paper, dict(reversed(list(rows.items()))))
    m = simple_method(
        {"T": {"behaviour": "question_wise", "pass_pct": 60}},
        {"T": "1"},
        final={"direct": "1", "indirect": "0"},
    )
    assert output_hash(run(m, course([forward])).result) == output_hash(
        run(m, course([backward])).result
    )


# the trace (M2) --------------------------------------------
def test_trace_explains_a_co_value_part_by_part() -> None:
    paper = parts([("q3", "3", 4, "CO2", None), ("q12a", "12", 4, "CO2", "G")])
    rows = {f"s{i}": {"q3": 4, "q12a": 4 if i < 3 else None} for i in range(10)}
    m = simple_method(
        {"SEE": {"behaviour": "question_wise", "pass_pct": 60}},
        {"SEE": "1"},
        final={"direct": "1", "indirect": "0"},
    )
    out = run(m, course([assessment("SEE", paper, rows)], cos=("CO2",), indirect={}))
    text = out.trace.text()
    assert "SEE/q3: 10/10 passed at 2.4 of 4 (10 of 10 attempted)" in text
    assert "SEE/q12a: 3/3 passed" in text and "(3 of 10 attempted)" in text
    assert "small group" in text  # 3 attempted is below the default warning of 10
    assert "mean of 2 part percentages" in text
    assert out.trace.for_key("SEE/q3")
    assert "level 3" in text


def test_method_with_defaults_loads_and_runs_end_to_end() -> None:
    m = method()
    data = course([class_with_pass_rate("INT1", 10, 10)], indirect={"CO1": "3"})
    out = run(m, data)
    assert out.result.tool_values["SEE"]["CO1"].status == "missing"  # no SEE marks supplied
    assert out.result.complete is False  # default missing_data is block


def test_merge_is_blocked_when_a_source_is_stopped_for_review() -> None:
    cfg = {"behaviour": "question_wise", "pass_pct": 60}
    merged = simple_method(
        {"INT1": cfg, "INT2": cfg},
        {"INTERNAL": "1"},
        merge={"INTERNAL": {"from": ["INT1", "INT2"]}},
    )
    data = course(
        [class_with_pass_rate("INT1", 0, 20), class_with_pass_rate("INT2", 10, 10)],
        indirect={"CO1": "3"},
    )
    out = run(merged, data)
    assert out.result.merged["INTERNAL"]["CO1"].status == "blocked"
    assert out.result.complete is False


def test_merge_with_no_source_is_missing() -> None:
    cfg = {"behaviour": "question_wise", "pass_pct": 60}
    merged = simple_method(
        {"INT1": cfg, "INT2": cfg},
        {"INTERNAL": "1"},
        merge={"INTERNAL": {"from": ["INT1", "INT2"]}},
        missing_data="renormalise",
    )
    out = run(merged, course([], indirect={"CO1": "3"}))
    assert out.result.merged["INTERNAL"]["CO1"].status == "missing"
    assert out.result.direct["CO1"].status == "missing"
    assert out.result.course is None and out.result.course_status == "no value"
