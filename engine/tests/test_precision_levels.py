"""A4: precision per level; and the CO aggregation alternatives."""

from decimal import Decimal

import pytest

from engine.display import compared, display
from engine.pipeline import run
from engine.schema import Precision

from .builders import assessment, course, parts, simple_method

pytestmark = pytest.mark.unit

D = Decimal


def _precision(**rules: dict[str, object]) -> Precision:
    return Precision.model_validate({"default": {"mode": "truncate", "places": 2}, **rules})


def test_a4_truncate_round_and_none() -> None:
    value = D("2.8594")
    assert display(_precision(), "batch", value) == D("2.85")
    assert display(_precision(batch={"mode": "round", "places": 2}), "batch", value) == D("2.86")
    assert display(_precision(batch={"mode": "none", "places": 2}), "batch", value) == value


def test_a4_half_up_not_half_even() -> None:
    assert display(_precision(co={"mode": "round", "places": 2}), "co", D("2.845")) == D("2.85")
    assert display(_precision(co={"mode": "round", "places": 2}), "co", D("2.835")) == D("2.84")


def test_a4_each_level_has_its_own_rule_and_falls_back_to_the_default() -> None:
    p = _precision(co={"mode": "round", "places": 1}, po={"mode": "none", "places": 0})
    value = D("2.8594")
    assert display(p, "co", value) == D("2.9")
    assert display(p, "po", value) == value
    assert display(p, "course", value) == D("2.85")  # no course rule: default
    assert display(p, "question_pct", value) == D("2.85")


def test_a4_comparison_uses_the_unrounded_value_unless_the_method_says_displayed() -> None:
    p_unrounded = _precision(batch={"mode": "round", "places": 2})
    p_displayed = Precision.model_validate(
        {
            "default": {"mode": "truncate", "places": 2},
            "batch": {"mode": "round", "places": 2},
            "compare_with": "displayed",
        }
    )
    value = D("2.8594")
    assert compared(p_unrounded, "batch", value) == value
    assert compared(p_displayed, "batch", value) == D("2.86")


def test_a4_unknown_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="mode"):
        _precision(co={"mode": "ceiling", "places": 2})


# AggregateToCO alternatives ----------------------------------------------------------------------
PAPER = parts([("a", "1", 10, "CO1", None), ("b", "2", 30, "CO1", None)])
ROWS = {
    "s1": {"a": 10, "b": 0},
    "s2": {"a": 10, "b": 0},
    "s3": {"a": 0, "b": 30},
    "s4": {"a": 0, "b": 30},
}


def _co1_percent(aggregate: str) -> Decimal | None:
    m = simple_method(
        {
            "T": {
                "behaviour": "question_wise",
                "pass_pct": 60,
                "aggregate": aggregate,
                "student_level_pct": 60,
            }
        },
        {"T": "1"},
        final={"direct": "1", "indirect": "0"},
        levels={"bands": [{"min_pct": 0, "level": 1}]},
    )
    return run(m, course([assessment("T", PAPER, ROWS)])).result.tool_values["T"]["CO1"].percent


def test_mean_of_part_percentages_is_the_default() -> None:
    assert _co1_percent("mean_of_question_pct") == 50  # a: 50%, b: 50%


def test_marks_weighted_gives_the_bigger_part_more_weight() -> None:
    rows = {
        "s1": {"a": 10, "b": 0},
        "s2": {"a": 10, "b": 0},
        "s3": {"a": 10, "b": 0},
        "s4": {"a": 0, "b": 30},
    }
    m = simple_method(
        {"T": {"behaviour": "question_wise", "pass_pct": 60, "aggregate": "marks_weighted"}},
        {"T": "1"}, final={"direct": "1", "indirect": "0"},
    )  # fmt: skip
    out = run(m, course([assessment("T", PAPER, rows)])).result.tool_values["T"]["CO1"].percent
    assert out == (D(75) * 10 + D(25) * 30) / D(40)  # a passes 3 of 4, b passes 1 of 4


def test_student_level_counts_students_not_parts() -> None:
    # a student earns 10 of 40 (25%), 30 of 40 (75%): s1,s2 fail, s3,s4 pass at 60%
    assert _co1_percent("student_level") == 50
