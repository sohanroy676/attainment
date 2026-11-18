"""The gap view (design 8.9): what is below target, and which questions were weakest.

Everything here reads values the engine already produced (final CO values, PO values and the
per-part pass counts in the trace); it adds no new rule, only a comparison and an ordering.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

from .display import compared
from .precision import CALCULATION_CONTEXT, HUNDRED
from .schema import Precision


@dataclass(frozen=True)
class Gap:
    key: str  # CO1, PO3
    value: Decimal
    target: Decimal
    shortfall: Decimal  # target minus value, always above 0


@dataclass(frozen=True)
class QuestionGap:
    tool: str
    part: str
    co: str | None
    passed: int
    denominator: int
    percent: Decimal | None  # None when nobody counted
    small_group: bool


def below_target(
    values: Mapping[str, Decimal | None],
    targets: Mapping[str, Decimal],
    precision: Precision,
    level: str,
) -> list[Gap]:
    """The outcomes whose value is under their target, the biggest shortfall first.

    A value is compared the way the method compares attainment with a target (unrounded by
    default). An outcome with no value or no target is not listed: it is missing, not low.
    """
    found: list[Gap] = []
    with localcontext(CALCULATION_CONTEXT):
        for key, value in values.items():
            target = targets.get(key)
            if value is None or target is None:
                continue
            if compared(precision, level, value) < target:
                found.append(Gap(key, value, target, target - value))
    return sorted(found, key=lambda g: (-g.shortfall, g.key))


def weakest_questions(
    entries: Iterable[Mapping[str, Any]], limit: int | None = None
) -> list[QuestionGap]:
    """Question parts ranked by the share of students who passed them, lowest first.

    `entries` are the QuestionPass trace entries (one per tool, part and section); sections of
    the same part are pooled by adding their pass counts and denominators. A part nobody counted
    for is listed last.
    """
    pooled: dict[tuple[str, str], list[Any]] = {}
    for entry in entries:
        if entry.get("step") != "QuestionPass":
            continue
        tool, _, part = str(entry["key"]).partition("/")
        data = entry["data"]
        row = pooled.setdefault((tool, part), [0, 0, data.get("co"), False])
        row[0] += int(data["passed"])
        row[1] += int(data["denominator"])
        row[3] = row[3] or bool(data.get("small_group"))
    ranked: list[QuestionGap] = []
    with localcontext(CALCULATION_CONTEXT):
        for (tool, part), (passed, denominator, co, small) in pooled.items():
            percent = Decimal(passed) * HUNDRED / Decimal(denominator) if denominator else None
            ranked.append(QuestionGap(tool, part, co, passed, denominator, percent, small))
    ranked.sort(key=lambda q: (q.percent is None, q.percent or Decimal(0), q.tool, q.part))
    return ranked if limit is None else ranked[:limit]
