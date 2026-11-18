"""TargetRevise and the near-target warning (design 6.3, R14 to R15)."""

from decimal import Decimal

from ..schema import ReviseRule
from ..trace import Trace

HUNDRED = Decimal(100)


def revise_target(
    rule: ReviseRule, current: Decimal, met: bool, trace: Trace | None = None
) -> Decimal:
    """The target for next time.

    manual         never changes the target.
    add_points     met: current + value;      not met and `lower`: current - value
    add_percent    met: current x (1 + value/100); not met and `lower`: current x (1 - value/100)
    multiply       met: current x value;      not met and `lower`: current / value
    `if_not_met: keep` leaves an unmet target unchanged. The result is held between floor
    and ceiling when they are set.
    """
    new = current
    value = rule.value
    if rule.rule != "manual" and value is not None and (met or rule.if_not_met == "lower"):
        sign = 1 if met else -1
        if rule.rule == "add_points":
            new = current + sign * value
        elif rule.rule == "add_percent":
            new = current * (1 + sign * value / HUNDRED)
        elif rule.rule == "multiply":
            new = current * value if met else current / value
    if rule.floor is not None and new < rule.floor:
        new = rule.floor
    if rule.ceiling is not None and new > rule.ceiling:
        new = rule.ceiling
    if trace is not None:
        trace.add(
            "TargetRevise",
            "target",
            f"rule {rule.rule}, {'met' if met else 'not met'}: {current} -> {new}",
        )
    return new


def near_target(compared_value: Decimal, target: Decimal, margin: Decimal) -> bool:
    """True when the value is within `margin` of the target on either side."""
    return abs(compared_value - target) <= margin
