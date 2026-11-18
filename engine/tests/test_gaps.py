"""The gap view: values below target and the weakest questions."""

from decimal import Decimal

import pytest

from engine.gaps import below_target, weakest_questions
from engine.schema import Precision, PrecisionRule

pytestmark = [pytest.mark.unit]

D = Decimal
UNROUNDED = Precision()
DISPLAYED = Precision(default=PrecisionRule(mode="truncate", places=1), compare_with="displayed")


def _entry(key: str, passed: int, den: int, co: str | None = "CO1", small: bool = False):  # type: ignore[no-untyped-def]
    return {
        "step": "QuestionPass",
        "key": key,
        "message": "",
        "data": {"passed": passed, "denominator": den, "co": co, "small_group": small},
    }


def test_values_under_the_target_are_listed_biggest_shortfall_first() -> None:
    gaps = below_target(
        {"CO1": D("2.84"), "CO2": D("2.0"), "CO3": D("2.5"), "CO4": D("1.2")},
        dict.fromkeys(("CO1", "CO2", "CO3", "CO4"), D("2.2")),
        UNROUNDED,
        "co",
    )
    assert [g.key for g in gaps] == ["CO4", "CO2"]
    assert gaps[0].shortfall == D("1.0") and gaps[0].target == D("2.2")


def test_a_value_exactly_on_the_target_is_not_a_gap() -> None:
    assert below_target({"PO1": D("2.2")}, {"PO1": D("2.2")}, UNROUNDED, "po") == []


def test_a_missing_value_or_target_is_not_listed_as_low() -> None:
    assert below_target({"PO1": None, "PO2": D("1")}, {"PO1": D("2"), "PO3": D("2")},
                        UNROUNDED, "po") == []  # fmt: skip


def test_the_comparison_follows_the_methods_compare_setting() -> None:
    # 2.19 is under 2.2 unrounded, but shown truncated to one place it is 2.1: still under;
    # 2.25 truncates to 2.2 and meets the target when compared as displayed
    assert [g.key for g in below_target({"A": D("2.25")}, {"A": D("2.3")}, DISPLAYED, "co")] == [
        "A"
    ]
    assert below_target({"A": D("2.25")}, {"A": D("2.2")}, DISPLAYED, "co") == []
    assert [g.key for g in below_target({"A": D("2.19")}, {"A": D("2.2")}, UNROUNDED, "co")] == [
        "A"
    ]


def test_questions_are_ranked_by_pass_share_lowest_first() -> None:
    ranked = weakest_questions(
        [_entry("INT1/1a", 3, 10), _entry("INT1/1b", 9, 10), _entry("SEE/12", 1, 4, "CO2")]
    )
    assert [(q.tool, q.part) for q in ranked] == [("SEE", "12"), ("INT1", "1a"), ("INT1", "1b")]
    assert ranked[0].percent == D(25) and ranked[1].percent == D(30) and ranked[0].co == "CO2"


def test_sections_of_the_same_part_are_pooled() -> None:
    ranked = weakest_questions([_entry("INT1/1a", 5, 5), _entry("INT1/1a", 0, 5)])
    assert len(ranked) == 1 and ranked[0].passed == 5 and ranked[0].denominator == 10
    assert ranked[0].percent == D(50)


def test_a_part_nobody_counted_is_last_and_other_steps_are_ignored() -> None:
    ranked = weakest_questions(
        [
            _entry("INT1/1a", 0, 0),
            _entry("INT1/1b", 9, 10),
            {"step": "Bands", "key": "INT1/CO1", "message": "", "data": {}},
        ]
    )
    assert [q.part for q in ranked] == ["1b", "1a"] and ranked[1].percent is None


def test_ties_keep_a_stable_order_and_the_limit_cuts_the_list() -> None:
    entries = [_entry("INT1/1b", 1, 2), _entry("INT1/1a", 1, 2), _entry("INT1/1c", 2, 2)]
    ranked = weakest_questions(entries)
    assert [q.part for q in ranked] == ["1a", "1b", "1c"]
    assert [q.part for q in weakest_questions(entries, limit=2)] == ["1a", "1b"]
    assert weakest_questions(entries, limit=0) == []


def test_a_small_group_flag_survives_pooling() -> None:
    ranked = weakest_questions([_entry("INT1/1a", 1, 2, small=True), _entry("INT1/1a", 3, 30)])
    assert ranked[0].small_group is True


def test_nothing_in_nothing_out() -> None:
    assert weakest_questions([]) == [] and below_target({}, {}, UNROUNDED, "co") == []
