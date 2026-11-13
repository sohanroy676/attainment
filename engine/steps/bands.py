"""Bands: turn an unrounded percentage into a level, and flag a result below the lowest band."""

from decimal import Decimal

from ..model import ToolValue
from ..precision import ZERO
from ..schema import Levels
from ..trace import Trace


def to_tool_value(
    tool: str, co: str, percent: Decimal | None, levels: Levels, trace: Trace
) -> ToolValue:
    """Level for `percent`. No percent means the tool says nothing about this CO ("missing")."""
    key = f"{tool}/{co}"
    if percent is None:
        trace.add("Bands", key, "no value for this CO (no part tagged, or nobody attempted)")
        return ToolValue(tool, co, None, None, "missing")
    for band in levels.bands:
        if percent >= band.min_pct:
            trace.add(
                "Bands", key, f"{percent}% is in band from {band.min_pct}%: level {band.level}"
            )
            return ToolValue(tool, co, percent, band.level, "ok")
    lowest = levels.bands[-1].min_pct
    flag = f"below the lowest band ({lowest}%)" if levels.below_lowest.flag else None
    use = levels.below_lowest.value_for_calc
    if use == "block":
        trace.add("Bands", key, f"{percent}% is below {lowest}%: stopped for review")
        return ToolValue(tool, co, percent, None, "blocked", flag or "below lowest band")
    level = ZERO if use == "zero" else use
    trace.add("Bands", key, f"{percent}% is below {lowest}%: level {level} used, flagged")
    return ToolValue(tool, co, percent, level, "ok", flag)
