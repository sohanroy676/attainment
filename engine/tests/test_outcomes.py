"""A6 CO-PO mapping, A7 indirect values, A8 targets."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from engine.loader import load_course
from engine.model import CoValue
from engine.pipeline import run
from engine.schema import ReviseRule
from engine.steps.map_outcomes import map_to_outcomes
from engine.steps.targets import near_target, revise_target
from engine.trace import Trace

from .builders import class_with_pass_rate, course, method, simple_method

pytestmark = pytest.mark.unit

D = Decimal


def _finals(**values: str | None) -> dict[str, CoValue]:
    return {
        co: CoValue(None if v is None else D(v), "missing" if v is None else "ok")
        for co, v in values.items()
    }


def _map(rows: dict[str, dict[str, int | None]]) -> dict[str, dict[str, Decimal]]:
    return {co: {po: D(s) for po, s in row.items() if s is not None} for co, row in rows.items()}


# A6 --------------------------------------------------------
def test_a6_four_of_five_cos_average_four_values() -> None:
    finals = _finals(CO1="3", CO2="2", CO3="1", CO4="2", CO5="3")
    mapping = _map({f"CO{i}": {"PO1": 1} for i in range(1, 5)})  # CO5 is not mapped to PO1
    out = map_to_outcomes(finals, mapping, "blank", Trace())
    assert out["PO1"].value == D(3 + 2 + 1 + 2) / 4


def test_a6_strengths_weight_the_cos() -> None:
    out = map_to_outcomes(
        _finals(CO1="3", CO2="2"), _map({"CO1": {"PO1": 2}, "CO2": {"PO1": 1}}), "blank", Trace()
    )
    assert out["PO1"].value == D(8) / D(3)


def test_a6_blank_stays_blank_and_zero_stays_zero() -> None:
    finals = _finals(CO1="3", CO2="2")
    mapping = _map({"CO1": {"PO1": 0, "PO2": 0}, "CO2": {"PO1": 2, "PO2": None}})
    out = map_to_outcomes(finals, mapping, "blank", Trace())
    assert out["PO1"].value == 2  # CO1 maps with strength 0: adds nothing
    assert "PO2" in out and out["PO2"].value is None  # only a 0 strength: blank by default
    zero = map_to_outcomes(finals, mapping, "zero", Trace())
    assert zero["PO2"].value == 0  # by option an all-zero outcome is 0
    assert "PO3" not in out  # an outcome nobody maps is not invented


def test_a6_a_co_without_a_value_is_left_out_of_the_mean() -> None:
    out = map_to_outcomes(
        _finals(CO1="3", CO2=None), _map({"CO1": {"PO1": 1}, "CO2": {"PO1": 3}}), "blank", Trace()
    )
    assert out["PO1"].value == 3


def test_a6_blocked_co_blocks_the_outcome_and_the_run() -> None:
    finals = {"CO1": CoValue(None, "blocked", "x"), "CO2": CoValue(D(2), "ok")}
    out = map_to_outcomes(finals, _map({"CO1": {"PO1": 1}, "CO2": {"PO1": 1}}), "blank", Trace())
    assert out["PO1"].status == "blocked"


def test_a6_outcomes_are_ordered_po_then_pso_numerically() -> None:
    finals = _finals(CO1="3")
    mapping = _map({"CO1": {"PSO2": 1, "PO10": 1, "PO2": 1, "PSO1": 1}})
    assert list(map_to_outcomes(finals, mapping, "blank", Trace())) == [
        "PO2",
        "PO10",
        "PSO1",
        "PSO2",
    ]


def test_mapping_flows_through_a_course_run_and_the_loader() -> None:
    text = (
        '{"cos": ["CO1", "CO2"], "students": ["s"], "indirect": {"CO1": 3, "CO2": 3},'
        ' "mapping": {"CO1": {"PO1": 2, "PO2": null}, "CO2": {"PO1": 1, "PO2": 0}},'
        ' "assessments": {}}'
    )
    data = load_course(text)
    assert data.mapping["CO1"] == {"PO1": D(2)}  # null is "not mapped"
    assert data.mapping["CO2"]["PO2"] == 0 and "PO2" not in data.mapping["CO1"]
    no_marks = method(
        missing_data="zero",
        tools={"SEE": {"behaviour": "question_wise", "pass_pct": 60}},
        merge={},
        direct={"SEE": "1"},
        final={"direct": "1", "indirect": "0"},
    )
    out = run(no_marks, data)  # no marks: every CO counts as 0 under missing_data "zero"
    assert set(out.result.po) == {"PO1", "PO2"}
    assert out.result.po["PO1"].value == 0
    assert out.result.po["PO2"].value is None  # only a strength-0 mapping: blank


# A7 --------------------------------------------------------
def test_a7_entered_indirect_is_labelled_and_direct_only_is_kept_beside_the_total() -> None:
    m = simple_method(
        {"T": {"behaviour": "question_wise", "pass_pct": 60}}, {"T": "1"},
        final={"direct": "0.8", "indirect": "0.2"},
    )  # fmt: skip
    out = run(
        m, course([class_with_pass_rate("T", 5, 10)], indirect={"CO1": "3"})
    )  # direct level 2
    r = out.result
    assert r.indirect_source == "entered_value" and r.indirect == {"CO1": D(3)}
    assert r.direct["CO1"].value == 2  # direct-only
    assert r.final["CO1"].value == D("2.2")  # 0.8 x 2 + 0.2 x 3: a typed 3 lifts the total


# A8 --------------------------------------------------------
@pytest.mark.parametrize(
    ("course_value", "flagged"),
    [("2.19", True), ("2.20", True), ("2.21", True), ("2.30", False), ("2.00", False)],
)
def test_a8_near_target_warning_within_0_01(course_value: str, flagged: bool) -> None:
    assert near_target(D(course_value), D("2.2"), D("0.01")) is flagged


def test_a8_course_run_adds_the_near_target_flag() -> None:
    m = simple_method(
        {"T": {"behaviour": "question_wise", "pass_pct": 60}}, {"T": "1"},
        final={"direct": "0.9", "indirect": "0.1"},
    )  # fmt: skip
    data = course([class_with_pass_rate("T", 10, 10)], indirect={"CO1": "1.1"}, target="2.81")
    out = run(m, data)  # 0.9 x 3 + 0.1 x 1.1 = 2.81 exactly
    assert out.result.attained is True
    assert any("within 0.01 of the target" in f for f in out.result.flags)


CURRENT = D("2.5")


@pytest.mark.parametrize(
    ("rule", "value", "met", "if_not_met", "expected"),
    [
        ("manual", None, True, "keep", D("2.5")),
        ("manual", None, False, "lower", D("2.5")),
        ("add_points", D("0.1"), True, "keep", D("2.6")),
        ("add_points", D("0.1"), False, "keep", D("2.5")),
        ("add_points", D("0.1"), False, "lower", D("2.4")),
        ("add_percent", D(10), True, "keep", D("2.75")),
        ("add_percent", D(10), False, "keep", D("2.5")),
        ("add_percent", D(10), False, "lower", D("2.25")),
        ("multiply", D("1.1"), True, "keep", D("2.75")),
        ("multiply", D("1.1"), False, "keep", D("2.5")),
        ("multiply", D("1.1"), False, "lower", None),
    ],
)
def test_a8_target_revision_rules(
    rule: str, value: Decimal | None, met: bool, if_not_met: str, expected: Decimal | None
) -> None:
    if expected is None:
        expected = D("2.5") / D("1.1")  # computed at the engine's precision
    revise = ReviseRule(rule=rule, value=value, if_not_met=if_not_met)  # type: ignore[arg-type]
    assert revise_target(revise, CURRENT, met) == expected


def test_a8_floor_and_ceiling_hold_the_revised_target() -> None:
    up = ReviseRule(rule="add_points", value=D(1), ceiling=D(3))
    assert revise_target(up, CURRENT, True) == 3
    down = ReviseRule(rule="add_points", value=D(1), if_not_met="lower", floor=D("2.2"))
    assert revise_target(down, CURRENT, False) == D("2.2")


def test_a8_revision_is_traced() -> None:
    trace = Trace()
    revise_target(ReviseRule(rule="add_points", value=D("0.1")), CURRENT, True, trace)
    assert "2.5 -> 2.6" in trace.text()


@pytest.mark.parametrize(
    "bad",
    [
        {"rule": "add_points"},
        {"rule": "multiply", "value": D(0)},
        {"rule": "manual", "floor": D(3), "ceiling": D(2)},
    ],
)
def test_a8_invalid_revision_rules_are_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReviseRule(**bad)  # type: ignore[arg-type]
