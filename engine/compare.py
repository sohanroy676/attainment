"""Compare a computed value with one taken from an old workbook (design 8.13).

Two values differ when they differ at the precision the method shows for that level (a computed
2.694 and an old 2.69 agree under truncation to two places). The raw difference is kept too.
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .display import display
from .precision import CALCULATION_CONTEXT
from .schema import Precision


@dataclass(frozen=True)
class ValueComparison:
    computed: Decimal | None
    imported: Decimal | None
    difference: Decimal | None  # computed minus imported, unrounded; None if either is missing
    differs: bool  # at the displayed precision
    note: str  # "", "only computed", "only in the old file"


def compare_values(
    precision: Precision, level: str, computed: Decimal | None, imported: Decimal | None
) -> ValueComparison:
    """Compare at the method's display precision for `level` (co, course, po or batch)."""
    if computed is None and imported is None:
        return ValueComparison(None, None, None, False, "")
    if computed is None:
        return ValueComparison(None, imported, None, True, "only in the old file")
    if imported is None:
        return ValueComparison(computed, None, None, True, "only computed")
    with localcontext(CALCULATION_CONTEXT):
        difference = computed - imported
        differs = display(precision, level, computed) != display(precision, level, imported)
    return ValueComparison(computed, imported, difference, differs, "")
