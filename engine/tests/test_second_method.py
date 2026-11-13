"""A10 (synthetic form): a different method is a different configuration, with no code change.

`docs/examples/method-college-b.json` differs from the Vasavi method in its bands, weights,
boundary, denominator, CO aggregation, rounding and comparison. The expected numbers were worked
out by hand (see the comments). Real published methods from other colleges (DS-E) are still to be
collected; this test shows the mechanism, not a published result.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from engine.model import CourseInput
from engine.pipeline import run
from engine.schema import MethodConfig, load_method

from .builders import assessment, course, parts

pytestmark = pytest.mark.unit

METHOD_FILE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "method-college-b.json"
D = Decimal


def _method(**changes: object) -> MethodConfig:
    method = load_method(METHOD_FILE.read_text(encoding="utf-8"))
    return method.model_copy(update=changes)


def _data(target: str = "2.5") -> CourseInput:
    mid = assessment(
        "MID",
        parts(
            [
                ("m1", "1", 10, "CO1", None),
                ("m2", "2", 20, "CO1", None),
                ("m3", "3", 10, "CO2", None),
            ]
        ),
        {"s1": {"m1": 6, "m2": 11, "m3": 5}, "s2": {"m1": 5, "m2": 12, "m3": 6},
         "s3": {"m1": 9, "m2": 10, "m3": 7}, "s4": {"m1": 4, "m2": 20, "m3": 3}},
    )  # fmt: skip
    end = assessment(
        "END",
        parts(
            [
                ("e1", "1", 10, "CO1", None),
                ("e2", "2", 10, "CO1", None),
                ("e3", "3", 20, "CO2", None),
            ]
        ),
        {"s1": {"e1": 8, "e2": 4, "e3": 10}, "s2": {"e1": 5, "e2": 5, "e3": 9},
         "s3": {"e1": 2, "e2": 1, "e3": 20}, "s4": {"e1": 10, "e2": 0, "e3": None}},
    )  # fmt: skip
    project = assessment(
        "PROJECT",
        parts([("p1", "1", 10, None, None), ("p2", "2", 10, None, None)]),
        {"s1": {"p1": 7, "p2": 5}, "s2": {"p1": 5, "p2": 5}, "s3": {"p1": 4, "p2": 5},
         "s4": {"p1": 8, "p2": 7}},
    )  # fmt: skip
    return course(
        [mid, end, project], cos=("CO1", "CO2"), indirect={"CO1": "2", "CO2": "2"}, target=target
    )


def test_the_file_is_a_valid_method_that_differs_from_vasavi_by_configuration_only() -> None:
    method = _method()
    assert [b.min_pct for b in method.levels.bands] == [70, 50, 30]
    assert method.tools["MID"].behaviour == "question_wise"
    assert method.final.indirect == D("0.1") and method.precision.compare_with == "displayed"


def test_hand_worked_numbers() -> None:
    out = run(_method(), _data())
    r = out.result
    # MID, boundary '>' at 50%: m1 passes s1, s3 = 50%; m2 passes s1, s2, s4 = 75%;
    # m3 passes s2, s3 = 50%. CO1 marks-weighted (50x10 + 75x20)/30 = 66.67 -> level 2;
    # CO2 = 50 -> level 2 (50 sits in the 50 band)
    assert r.tool_values["MID"]["CO1"].percent == (D(50) * 10 + D(75) * 20) / D(30)
    assert [r.tool_values["MID"][c].level for c in ("CO1", "CO2")] == [2, 2]
    # END student level at 50%: CO1 passes s1 (12/20), s2 (10/20), s4 (10/20), not s3 = 75%
    # -> level 3. CO2: s4 did not attempt, so 3 are counted; s1 (50%) and s3 pass, s2 (45%)
    # fails = 66.67% -> level 2
    assert r.tool_values["END"]["CO1"].percent == 75
    assert r.tool_values["END"]["CO2"].percent == D(200) / D(3)
    assert [r.tool_values["END"][c].level for c in ("CO1", "CO2")] == [3, 2]
    # PROJECT: totals 12, 10, 9, 15 against a pass mark of 10 -> 75% -> level 3 for every CO
    assert r.tool_values["PROJECT"]["CO1"].percent == 75
    # direct: CO1 = .25x2 + .5x3 + .25x3 = 2.75; CO2 = .25x2 + .5x2 + .25x3 = 2.25
    assert (r.direct["CO1"].value, r.direct["CO2"].value) == (D("2.75"), D("2.25"))
    # final = .9 x direct + .1 x 2 -> 2.675 and 2.225; course 2.45
    assert (r.final["CO1"].value, r.final["CO2"].value) == (D("2.675"), D("2.225"))
    assert r.course == D("2.45")


def test_comparison_switch_changes_the_status_by_configuration_only() -> None:
    displayed = run(_method(), _data("2.5")).result
    assert displayed.attained is True  # 2.45 shown as 2.5 (round, one place) meets 2.5
    unrounded = _method(
        precision=_method().precision.model_copy(update={"compare_with": "unrounded"})
    )
    assert run(unrounded, _data("2.5")).result.attained is False  # 2.45 < 2.5


def test_the_wider_near_target_margin_of_this_method_is_used() -> None:
    flags = run(_method(), _data("2.5")).result.flags
    assert any("within 0.05 of the target" in f for f in flags)


def test_boundary_difference_matters_between_the_two_methods() -> None:
    ge = _method(
        tools={
            **_method().tools,
            "MID": _method().tools["MID"].model_copy(update={"boundary": ">="}),
        }
    )
    # with '>=' m1 also passes s2 (5 of 10), m3 passes s1 (5 of 10)
    assert run(ge, _data()).result.tool_values["MID"]["CO2"].percent == 75
