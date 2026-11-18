from collections.abc import Iterator
from decimal import getcontext, setcontext

import pytest

from engine.precision import CALCULATION_CONTEXT


@pytest.fixture(autouse=True)
def _calculation_precision() -> Iterator[None]:
    """Expected values in tests are computed at the same 40 digits as the engine."""
    previous = getcontext().copy()
    setcontext(CALCULATION_CONTEXT.copy())
    yield
    setcontext(previous)
