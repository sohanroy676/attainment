"""Comparing computed values with an old workbook's values at the displayed precision."""

from decimal import Decimal

import pytest

from engine.compare import compare_values
from engine.schema import Precision, PrecisionRule

pytestmark = [pytest.mark.unit]

D = Decimal
TRUNCATE_2 = Precision(batch=PrecisionRule(mode="truncate", places=2))
ROUND_2 = Precision(batch=PrecisionRule(mode="round", places=2))


def test_values_that_agree_at_the_shown_precision_do_not_differ() -> None:
    result = compare_values(TRUNCATE_2, "batch", D("2.694"), D("2.69"))
    assert result.differs is False and result.difference == D("0.004")


def test_the_same_pair_differs_when_the_method_rounds() -> None:
    assert compare_values(ROUND_2, "batch", D("2.696"), D("2.69")).differs is True
    assert compare_values(TRUNCATE_2, "batch", D("2.696"), D("2.69")).differs is False


def test_a_one_digit_difference_is_found_and_signed() -> None:
    result = compare_values(TRUNCATE_2, "batch", D("2.50"), D("2.51"))
    assert result.differs is True and result.difference == D("-0.01")


def test_a_missing_side_is_a_difference_with_a_note() -> None:
    only_computed = compare_values(TRUNCATE_2, "batch", D("3"), None)
    only_old = compare_values(TRUNCATE_2, "batch", None, D("3"))
    assert (only_computed.differs, only_computed.note, only_computed.difference) == (
        True, "only computed", None,
    )  # fmt: skip
    assert (only_old.differs, only_old.note) == (True, "only in the old file")


def test_two_missing_values_agree() -> None:
    result = compare_values(TRUNCATE_2, "batch", None, None)
    assert result.differs is False and result.note == ""


def test_zero_is_a_value_not_a_gap() -> None:
    assert compare_values(TRUNCATE_2, "batch", D("0"), None).differs is True
    assert compare_values(TRUNCATE_2, "batch", D("0"), D("0.00")).differs is False


def test_the_level_picks_its_own_rule() -> None:
    mixed = Precision(
        default=PrecisionRule(mode="truncate", places=2),
        po=PrecisionRule(mode="truncate", places=1),
    )
    assert compare_values(mixed, "po", D("2.64"), D("2.60")).differs is False
    assert compare_values(mixed, "batch", D("2.64"), D("2.60")).differs is True
