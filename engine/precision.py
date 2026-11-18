"""Decimal helpers. Every rounding in the engine goes through `quantize` with an explicit mode.

Python's default decimal rounding is half-to-even (2.845 -> 2.84); Excel's ROUND is half away
from zero (2.85). The engine never relies on the default: `truncate` or `round` is always named.
"""

from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal
from typing import Literal

Mode = Literal["truncate", "round", "none"]

# 40 significant digits for every calculation. Intermediate results are never rounded to a
# display precision; the rounding mode below only matters beyond the 40th digit.
CALCULATION_CONTEXT = Context(prec=40, rounding=ROUND_HALF_EVEN)

HUNDRED = Decimal(100)
ZERO = Decimal(0)
ONE = Decimal(1)


def quantize(value: Decimal, places: int, mode: Mode) -> Decimal:
    """Cut or round `value` to `places` decimals. `round` is half away from zero (Excel).

    `none` keeps every digit.
    """
    if mode == "none":
        return value
    exponent = ONE.scaleb(-places, context=CALCULATION_CONTEXT)
    rounding = ROUND_DOWN if mode == "truncate" else ROUND_HALF_UP
    return value.quantize(exponent, rounding=rounding, context=CALCULATION_CONTEXT)


def decimal_text(value: Decimal | None) -> str | None:
    """Stable text form used in traces and hashes."""
    if value is None:
        return None
    text = format(value.normalize(CALCULATION_CONTEXT), "f")
    return text
