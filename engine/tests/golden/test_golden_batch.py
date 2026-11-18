"""Golden R3: the CSE 2021-25 batch roll-up on DS-B.

Expected values are the project statement's Appendix B (totals as in the file, unrounded to four
decimals) and the course counts per outcome from the prototype run on the same file. They are
never edited to pass: a change needs a written reason and a MINOR version bump.

`ds_b/batch.json` is produced by `scripts/build_ds_b.py` from the workbook in data/private/.
Until it exists these tests skip.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from engine.batch import run_batch
from engine.loader import load_batch
from engine.precision import quantize
from engine.tests.builders import simple_method

pytestmark = pytest.mark.golden

BATCH = Path(__file__).resolve().parent / "ds_b" / "batch.json"
needs_data = pytest.mark.skipif(
    not BATCH.exists(),
    reason="DS-B not present: run scripts/build_ds_b.py on the batch workbook in data/private/",
)

TOTALS = {
    "PO1": "2.8399", "PO2": "2.8103", "PO3": "2.8118", "PO4": "2.8558", "PO5": "2.8555",
    "PO6": "2.8301", "PO7": "2.7248", "PO8": "2.9088", "PO9": "2.8594", "PO10": "2.8629",
    "PO11": "2.7600", "PO12": "2.7598", "PSO1": "2.8290", "PSO2": "2.8384", "PSO3": "2.8504",
}  # fmt: skip
COURSES_WITH_VALUE = {
    "PO1": 84, "PO2": 83, "PO3": 65, "PO4": 46, "PO5": 38, "PO6": 17, "PO7": 15, "PO8": 10,
    "PO9": 19, "PO10": 21, "PO11": 6, "PO12": 52, "PSO1": 51, "PSO2": 44, "PSO3": 46,
}  # fmt: skip


def _run(compare_with: str, mode: str):  # type: ignore[no-untyped-def]
    method = simple_method(
        {"T": {"behaviour": "question_wise", "pass_pct": 60}},
        {"T": "1"},
        final={"direct": "1", "indirect": "0"},
        precision={"default": {"mode": "truncate", "places": 2},
                   "batch": {"mode": mode, "places": 2}, "compare_with": compare_with},
    )  # fmt: skip
    return run_batch(method, load_batch(BATCH.read_text(encoding="utf-8")))


@needs_data
def test_r3_course_counts_and_totals() -> None:
    result = _run("unrounded", "truncate").result
    assert {o: v.courses_with_value for o, v in result.outcomes.items()} == COURSES_WITH_VALUE
    got = {o: str(quantize(v.total, 4, "round")) for o, v in result.outcomes.items() if v.total}
    assert got == TOTALS
    assert result.complete is True


@needs_data
def test_r3_po9_is_not_attained_when_compared_unrounded() -> None:
    result = _run("unrounded", "truncate").result
    assert result.outcomes["PO9"].attained is False
    assert [o for o, v in result.outcomes.items() if v.attained is False] == ["PO9"]


@needs_data
def test_r3_po9_is_attained_when_the_total_is_rounded_to_2_86_first() -> None:
    result = _run("displayed", "round").result
    assert result.outcomes["PO9"].attained is True
    assert Decimal("2.86") == quantize(result.outcomes["PO9"].total or Decimal(0), 2, "round")
