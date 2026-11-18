"""MergeTools, MissingData, WeightedCombine, final combine, Average and target comparison."""

from collections.abc import Mapping
from decimal import Decimal

from ..model import CoValue
from ..precision import ZERO
from ..trace import Trace


def merge_tools(name: str, co: str, sources: list[CoValue], method: str, trace: Trace) -> CoValue:
    """Average the levels of the tools that cover this CO. A fractional result (2.5) is kept."""
    if any(s.status == "blocked" for s in sources):
        trace.add("MergeTools", f"{name}/{co}", "a source is stopped for review: merge blocked")
        return CoValue(None, "blocked", "a source is stopped for review")
    values = [s.value for s in sources if s.value is not None]
    if not values:
        trace.add("MergeTools", f"{name}/{co}", "no source covers this CO")
        return CoValue(None, "missing")
    merged = sum(values, ZERO) / Decimal(len(values))
    trace.add("MergeTools", f"{name}/{co}", f"{method} of {len(values)} levels = {merged}")
    return CoValue(merged, "ok")


def weighted_combine(
    co: str,
    weights: Mapping[str, Decimal],
    values: Mapping[str, CoValue],
    missing_rule: str,
    trace: Trace,
) -> CoValue:
    """Direct attainment: sum of weight x level. Missing and blocked inputs follow the rules.

    A blocked input always blocks. A missing input follows `missing_rule`: block, renormalise
    the other weights to sum to 1, or count as 0.
    """
    key = f"direct/{co}"
    if any(values[t].status == "blocked" for t in weights):
        trace.add("WeightedCombine", key, "an input is stopped for review: direct blocked")
        return CoValue(None, "blocked", "an input is stopped for review")
    missing = [t for t in weights if values[t].value is None]
    if missing and missing_rule == "block":
        trace.add("MissingData", key, f"no value from {', '.join(missing)}: stopped for review")
        return CoValue(None, "blocked", f"no value from {', '.join(missing)}")
    present = {t: w for t, w in weights.items() if t not in missing}
    if missing and missing_rule == "renormalise":
        total = sum(present.values(), ZERO)
        if total == 0:
            return CoValue(None, "missing", "no tool gives a value")
        present = {t: w / total for t, w in present.items()}
        trace.add("MissingData", key, f"renormalised weights without {', '.join(missing)}")
    elif missing:
        trace.add("MissingData", key, f"{', '.join(missing)} counted as 0")
    total_value = ZERO
    for tool, weight in present.items():
        value = values[tool].value
        assert value is not None  # noqa: S101 - missing ones were removed above
        total_value += weight * value
    trace.add("WeightedCombine", key, f"sum of weight x level = {total_value}")
    return CoValue(total_value, "ok")


def final_combine(
    co: str,
    direct: CoValue,
    indirect: Decimal | None,
    direct_weight: Decimal,
    indirect_weight: Decimal,
    trace: Trace,
) -> CoValue:
    key = f"final/{co}"
    if direct.value is None:
        return CoValue(None, direct.status, direct.note)
    if indirect_weight == 0:
        return CoValue(direct.value, "ok")
    if indirect is None:
        trace.add("MissingData", key, "no indirect value entered: stopped for review")
        return CoValue(None, "blocked", "no indirect value entered")
    value = direct_weight * direct.value + indirect_weight * indirect
    trace.add(
        "WeightedCombine",
        key,
        f"{direct_weight} x direct {direct.value} + {indirect_weight} x indirect {indirect}"
        f" = {value}",
    )
    return CoValue(value, "ok")


def average_ignore_blank(values: list[Decimal | None]) -> Decimal | None:
    present = [v for v in values if v is not None]
    return sum(present, ZERO) / Decimal(len(present)) if present else None
