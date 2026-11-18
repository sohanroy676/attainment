"""Rounding for display and for comparison, per level (design 6.3 Precision)."""

from decimal import Decimal

from .precision import quantize
from .schema import Precision


def display(precision: Precision, level: str, value: Decimal) -> Decimal:
    """The value as the method shows it. `level`: co, course, po, batch or question_pct."""
    rule = precision.rule_for(level)
    return quantize(value, rule.places, rule.mode)


def compared(precision: Precision, level: str, value: Decimal) -> Decimal:
    """The value a target is compared with: unrounded (default) or as displayed."""
    return value if precision.compare_with == "unrounded" else display(precision, level, value)
