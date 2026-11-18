"""Step-level tests: boundaries, denominators, states, choice selection, bands, quiz absence."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import pytest

from engine.errors import EngineError
from engine.model import Cell, CourseInput, Override, Part, State
from engine.pipeline import RunOutput, run
from engine.precision import quantize
from engine.schema import ChoiceRule, Levels, MethodConfig
from engine.steps.bands import to_tool_value
from engine.steps.choice import choice_select
from engine.steps.normalise import normalise_states
from engine.trace import Trace

from .builders import BANDS, assessment, cells, course, parts, simple_method

pytestmark = pytest.mark.unit

ONE_TOOL_FINAL = {"direct": "1", "indirect": "0"}


def qw_method(**tool: object) -> MethodConfig:
    cfg = {"behaviour": "question_wise", "pass_pct": 60, "boundary": ">="} | tool
    return simple_method({"T": cfg}, {"T": "1"}, final=ONE_TOOL_FINAL)


def percent(result: RunOutput) -> Decimal:
    value = result.result.tool_values["T"]["CO1"].percent
    assert value is not None
    return value


# A6 ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(("boundary", "expected"), [(">=", 100), (">", 0)])
def test_a6_mark_exactly_at_the_pass_mark(boundary: str, expected: int) -> None:
    paper = parts([("p", "1", 3, "CO1", None)])
    rows = {f"s{i}": {"p": "1.8"} for i in range(3)}  # 1.8 is exactly 60% of 3
    out = run(qw_method(boundary=boundary), course([assessment("T", paper, rows)]))
    assert percent(out) == expected


# A8 ---------------------------------------------------------------------------------------
def _denominator_course() -> CourseInput:
    paper = parts([("c", "1", 4, "CO1", None), ("x", "2", 4, "CO1", "G")])
    rows: dict[str, dict[str, Any]] = {}
    for i in range(10):
        row: dict[str, Any] = {"c": 4, "x": None}
        if i < 4:
            row["x"] = 4  # attempted and passed
        elif i < 6:
            row["x"] = 0  # attempted and failed (0 is an attempt)
        rows[f"s{i}"] = row
    return course([assessment("T", paper, rows, absent_whole=frozenset({"s9"}))])


def test_a8_choice_counts_attempted_compulsory_counts_all_who_sat_absent_excluded() -> None:
    out = run(qw_method(), _denominator_course())
    compulsory = Decimal(100)  # 9 of the 9 who sat; s9 absent for the whole assessment
    choice = Decimal(4) * 100 / Decimal(6)  # 4 passed of 6 who attempted
    assert percent(out) == (compulsory + choice) / 2


def test_a8_whole_assessment_absent_can_count_as_fail() -> None:
    out = run(qw_method(whole_assessment_absent="count_as_fail"), _denominator_course())
    compulsory = Decimal(9) * 100 / Decimal(10)  # s9 still in the denominator, passes nothing
    choice = Decimal(4) * 100 / Decimal(6)
    assert percent(out) == (compulsory + choice) / 2


def test_denominator_modes_enrolled_and_fixed() -> None:
    paper = parts([("p", "1", 4, "CO1", None)])
    rows = {f"s{i}": {"p": 4} for i in range(5)}
    enrolled = course([assessment("T", paper, rows)], students=tuple(f"s{i}" for i in range(10)))
    assert percent(run(qw_method(denominator="enrolled"), enrolled)) == 50
    assert percent(run(qw_method(denominator="fixed", fixed_n=20), enrolled)) == 25


# blank, 0 and absent are different -----------------------------------------------------------
def test_blank_zero_and_absent_are_different_states() -> None:
    paper = parts([("p", "1", 4, "CO1", "G")])
    rows = {"zero": {"p": 0}, "blank": {"p": None}, "gone": {"p": "A"}, "ok": {"p": 4}}
    exclude = run(qw_method(absent="exclude"), course([assessment("T", paper, rows)]))
    assert percent(exclude) == 50  # zero fails, ok passes; blank and absent not attempted
    zero = run(qw_method(absent="zero"), course([assessment("T", paper, rows)]))
    assert percent(zero) == Decimal(1) * 100 / Decimal(3)  # absent now counts as a 0 attempt
    with pytest.raises(EngineError, match="absent"):
        run(qw_method(absent="error"), course([assessment("T", paper, rows)]))


def test_normalise_never_turns_blank_into_zero() -> None:
    paper = parts([("p", "1", 4, "CO1", None)])
    a = assessment("T", paper, {"s": {"p": None}})
    out = normalise_states(a, "zero", Trace(), whole_absent_as_cells=False)
    assert out["s"]["p"].state is State.BLANK


# overrides ----------------------------------------------------------------------------------
def test_per_part_override_changes_the_pass_mark_and_is_traced_with_its_reason() -> None:
    paper = parts([("p", "1", "3.5", "CO1", None)])
    data = course([assessment("T", paper, {f"s{i}": {"p": 2} for i in range(4)})])
    assert percent(run(qw_method(), data)) == 0  # 60% of 3.5 is 2.1: a mark of 2 fails
    overridden = course(
        [assessment("T", paper, {f"s{i}": {"p": 2} for i in range(4)})],
        overrides={("T", "p"): Override(Decimal(2), "college practice")},
    )
    out = run(qw_method(), overridden)
    assert percent(out) == 100
    assert "college practice" in out.trace.text()


# ChoiceSelect (A9, and the analogue of A4/A5) -----------------------------------------------
def _sec_paper(extra_parts_q17: int = 3) -> tuple[Part, ...]:
    spec = [(f"{n}{s}", str(n), 4, "CO1", "G") for n in range(11, 17) for s in "ab"]
    spec += [(f"17{s}", "17", 4, "CO1", "G") for s in "abc"[:extra_parts_q17]]
    return parts(spec)


def _select(row: Mapping[str, Any], rule: ChoiceRule) -> tuple[dict[str, Cell], Trace]:
    paper = _sec_paper()
    full = {p.id: row.get(p.id) for p in paper}
    a = assessment("SEE", paper, {"x": full})
    trace = Trace()
    out = choice_select(a, normalise_states(a, "exclude", trace, False), {"G": rule}, trace)
    return out["x"], trace


def _dropped(row: dict[str, Cell]) -> set[str]:
    return {p for p, c in row.items() if c.state is State.DROPPED}


def test_a9_t1_best_two_of_three_parts_and_best_five_of_six() -> None:
    row = {"11a": 4, "11b": 4, "12a": 3, "12b": 3, "13a": 2, "13b": 2, "14a": 2, "14b": 2,
           "15a": 1, "15b": 1, "17a": 4, "17b": 1, "17c": 3}  # fmt: skip
    out, trace = _select(row, ChoiceRule(best_n=5, best_k_parts={"17": 2}))
    assert _dropped(out) == {"17b", "15a", "15b"}
    assert "Q15" in trace.text() and "17b" in trace.text()


def test_a9_t2_tie_for_the_last_place_goes_to_the_lower_question_number() -> None:
    row = {"11a": 4, "11b": 4, "12a": 4, "12b": 4, "13a": 2, "13b": 2, "14a": 2, "14b": 2,
           "15a": 4, "15b": 4, "16a": 4, "16b": 4}  # fmt: skip
    out, _ = _select(row, ChoiceRule(best_n=5))
    assert _dropped(out) == {"14a", "14b"}  # Q13 and Q14 tie on 4; Q14 is the higher number


def test_a9_t3_four_answers_drop_nothing() -> None:
    out, trace = _select({"11a": 4, "12a": 4, "13a": 4, "14a": 4}, ChoiceRule(best_n=5))
    assert _dropped(out) == set()
    assert trace.entries == [] or all(e.step != "ChoiceSelect" for e in trace.entries)


def test_choice_drop_of_the_weakest_question_is_logged_for_a_seven_question_answer() -> None:
    row = {f"{n}a": 4 for n in range(11, 17)} | {"11b": 4, "17a": 1}
    out, trace = _select(row, ChoiceRule(best_n=5, best_k_parts={"17": 2}))
    assert _dropped(out) == {"16a", "17a"}  # Q16 ties with Q12 to Q15 and is the highest number
    assert "Q17" in trace.text() and "Q16" in trace.text()


def test_best_four_of_six_keeps_four_and_drops_the_lowest_for_a_five_answer_student() -> None:
    spec = [(f"q{n}", str(n), 5, "CO1", "G") for n in range(1, 7)]
    paper = parts(spec)
    rows = {f"s{i}": {f"q{n}": 3 for n in range(1, 5)} for i in range(65)}
    rows["five"] = {"q1": 5, "q2": 4, "q3": 4, "q4": 3, "q5": 2}
    a = assessment("INT2", paper, rows)
    trace = Trace()
    out = choice_select(
        a, normalise_states(a, "exclude", trace, False), {"G": ChoiceRule(best_n=4)}, trace
    )
    assert _dropped(out["five"]) == {"q5"}
    assert all(_dropped(out[f"s{i}"]) == set() for i in range(65))


# A10 ----------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("pct", "level", "status"),
    [("9.99", None, "blocked"), ("10.00", 1, "ok"), ("50.00", 2, "ok"), ("60.00", 3, "ok")],
)
def test_a10_band_edges(pct: str, level: int | None, status: str) -> None:
    levels = Levels.model_validate({"bands": BANDS})
    value = to_tool_value("T", "CO1", Decimal(pct), levels, Trace())
    assert value.status == status
    assert value.level == (None if level is None else Decimal(level))
    assert (value.flag is not None) == (status == "blocked")


def test_a10_below_lowest_band_with_block_makes_the_result_provisional() -> None:
    paper = parts([("p", "1", 10, "CO1", None)])
    rows = {f"s{i}": {"p": 10 if i == 0 else 0} for i in range(20)}  # 5% pass
    out = run(qw_method(), course([assessment("T", paper, rows)], indirect={}))
    assert out.result.tool_values["T"]["CO1"].status == "blocked"
    assert out.result.complete is False
    assert out.result.final["CO1"].value is None


@pytest.mark.parametrize(("use", "expected"), [("zero", Decimal(0)), (Decimal(1), Decimal(1))])
def test_a10_below_lowest_band_can_use_zero_or_a_set_value(use: object, expected: Decimal) -> None:
    levels = Levels.model_validate(
        {"bands": BANDS, "below_lowest": {"flag": True, "value_for_calc": use}}
    )
    value = to_tool_value("T", "CO1", Decimal("5"), levels, Trace())
    assert (value.level, value.status, value.flag is not None) == (expected, "ok", True)


# A13 ----------------------------------------------------------------------------------------
@pytest.mark.parametrize(("rule", "expected"), [("zero", 50), ("skip", 100)])
def test_a13_quiz_absent_handling(rule: str, expected: int) -> None:
    paper = parts([(f"i{k}", str(k), 5, None, None) for k in range(3)])
    rows = {"full": {"i0": 5, "i1": 5, "i2": 5}, "mostly_absent": {"i0": 5, "i1": "A", "i2": "A"}}
    method = simple_method(
        {"T": {"behaviour": "per_student_average", "max": 5, "pass_pct": 60, "absent": rule}},
        {"T": "1"},
        final=ONE_TOOL_FINAL,
    )
    out = run(method, course([assessment("T", paper, rows)]))
    assert (
        percent(out) == expected
    )  # zero: average 1.67 fails; skip: average of the one item passes


def test_quiz_item_with_the_wrong_maximum_is_refused() -> None:
    paper = parts([("i0", "0", 10, None, None)])
    method = simple_method(
        {"T": {"behaviour": "per_student_average", "max": 5, "pass_pct": 60}},
        {"T": "1"},
        final=ONE_TOOL_FINAL,
    )
    with pytest.raises(EngineError, match="max"):
        run(method, course([assessment("T", paper, {"s": {"i0": 5}})]))


def test_single_total_lab_with_a_pass_mark() -> None:
    paper = parts([("a", "1", 15, None, None), ("b", "2", 15, None, None)])
    rows = {"ok": {"a": 9, "b": 9}, "edge": {"a": 9, "b": 8}, "gone": {"a": "A", "b": "A"}}
    method = simple_method(
        {"T": {"behaviour": "single_total", "max": 30, "pass_mark": 18}},
        {"T": "1"},
        final=ONE_TOOL_FINAL,
    )
    out = run(method, course([assessment("T", paper, rows)]))
    assert (
        percent(out) == 50
    )  # ok passes at exactly 18; edge has 17; the absent student is excluded


# precision ------------------------------------------------------------------------------------
def test_t9_rounding_modes_are_explicit_and_match_excel() -> None:
    value = Decimal("2.845")
    assert quantize(value, 2, "truncate") == Decimal("2.84")
    assert quantize(value, 2, "round") == Decimal("2.85")  # half away from zero, like Excel
    assert quantize(Decimal("-2.845"), 2, "round") == Decimal("-2.85")
    assert round(value, 2) == Decimal("2.84")  # Python's own default would be half-to-even


def test_cells_helper_distinguishes_zero_blank_and_absent() -> None:
    built = cells({"a": 0, "b": None, "c": "A"})
    assert [built[k].state for k in "abc"] == [State.ENTERED, State.BLANK, State.ABSENT]
    assert built["a"].value == 0


@pytest.mark.parametrize(("mode", "expected"), [("attempted", 100), ("sat", 50)])
def test_denominator_modes_attempted_and_sat(mode: str, expected: int) -> None:
    paper = parts([("p", "1", 4, "CO1", None)])
    rows = {"a": {"p": 4}, "b": {"p": None}}  # b sat but answered nothing
    out = run(qw_method(denominator=mode), course([assessment("T", paper, rows)]))
    assert percent(out) == expected


def test_student_absent_for_the_whole_quiz_counts_as_zero_when_absent_is_zero() -> None:
    paper = parts([(f"i{k}", str(k), 5, None, None) for k in range(2)])
    rows = {"here": {"i0": 5, "i1": 5}, "gone": {"i0": None, "i1": None}}
    method = simple_method(
        {"T": {"behaviour": "per_student_average", "max": 5, "pass_pct": 60, "absent": "zero"}},
        {"T": "1"},
        final=ONE_TOOL_FINAL,
    )
    out = run(method, course([assessment("T", paper, rows, absent_whole=frozenset({"gone"}))]))
    assert percent(out) == 50  # the absent student is a 0 average and fails; not left out
