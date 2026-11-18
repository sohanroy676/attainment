"""MapToOutcomes: CO attainment to PO and PSO attainment by weighted mean (design 6.3).

value(PO) = sum(strength x CO) / sum(strength) over the COs mapped to that PO that have a value.
A CO with no mapping entry is not mapped (blank); an explicit strength of 0 is a mapping that
adds nothing. If every usable strength is 0 the PO is blank by default, or 0 by option.
"""

import re
from collections.abc import Mapping
from decimal import Decimal

from ..model import CoValue
from ..precision import ZERO
from ..trace import Trace


def _outcome_order(name: str) -> tuple[int, int, str]:
    match = re.fullmatch(r"(PSO|PO)(\d+)", name)
    if match is None:
        return (2, 0, name)
    return (1 if match.group(1) == "PSO" else 0, int(match.group(2)), name)


def map_to_outcomes(
    final: Mapping[str, CoValue],
    mapping: Mapping[str, Mapping[str, Decimal]],
    all_zero: str,
    trace: Trace,
) -> dict[str, CoValue]:
    outcomes = sorted(
        {po for strengths in mapping.values() for po in strengths}, key=_outcome_order
    )
    result: dict[str, CoValue] = {}
    for outcome in outcomes:
        mapped = [
            (co, strengths[outcome]) for co, strengths in mapping.items() if outcome in strengths
        ]
        if any(final.get(co) is not None and final[co].status == "blocked" for co, _ in mapped):
            trace.add("MapToOutcomes", outcome, "a mapped CO is stopped for review: blocked")
            result[outcome] = CoValue(None, "blocked", "a mapped CO is stopped for review")
            continue
        usable = [
            (co, strength) for co, strength in mapped if co in final and final[co].value is not None
        ]
        total_strength = sum((s for _, s in usable), ZERO)
        if total_strength == 0:
            note = "no mapped CO has a value" if not usable else "every mapped strength is 0"
            if all_zero == "zero" and usable:
                trace.add("MapToOutcomes", outcome, f"{note}: 0 used")
                result[outcome] = CoValue(ZERO, "ok", note)
            else:
                trace.add("MapToOutcomes", outcome, f"{note}: left blank")
                result[outcome] = CoValue(None, "missing", note)
            continue
        weighted = sum((s * (final[co].value or ZERO) for co, s in usable), ZERO)
        value = weighted / total_strength
        parts = ", ".join(f"{co} x{s}" for co, s in usable)
        trace.add("MapToOutcomes", outcome, f"weighted mean of {parts} = {value}")
        result[outcome] = CoValue(value, "ok")
    return result
