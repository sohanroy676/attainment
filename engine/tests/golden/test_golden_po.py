"""Golden tests that need no private data: PO/PSO values and the batch status rule.

R1 and R2 PO/PSO values come from ROADMAP section 3.2 (they equal the college's report). The
CO values are the final CO values of R1 and R2. The batch numbers come from R3: the direct values
as printed there are rolled up as one course each, so these tests check the total, the target
comparison and the rounding switch, not the 84-course average (that needs DS-B).

These expectations are never edited to pass; a change needs a written reason and a MINOR bump.
"""

from decimal import Decimal

import pytest

from engine.batch import BatchCourse, BatchInput, run_batch
from engine.model import CoValue
from engine.precision import quantize
from engine.steps.map_outcomes import map_to_outcomes
from engine.tests.builders import simple_method
from engine.trace import Trace

pytestmark = pytest.mark.golden

# CO-PO map of Deep Learning (project statement, Appendix A)
DL_MAP: dict[str, dict[str, int]] = {
    "CO1": {"PO1": 2, "PO3": 2, "PO4": 1, "PSO1": 1, "PSO2": 3, "PSO3": 3},
    "CO2": {"PO1": 2, "PO2": 2, "PO3": 2, "PO4": 2, "PO5": 2, "PSO1": 1, "PSO2": 3, "PSO3": 3},
    "CO3": {"PO1": 3, "PO2": 2, "PO3": 3, "PO4": 2, "PO5": 2, "PSO1": 2, "PSO2": 3, "PSO3": 3},
    "CO4": {"PO1": 3, "PO2": 2, "PO3": 2, "PO4": 2, "PO5": 1, "PSO1": 2, "PSO2": 3, "PSO3": 3},
    "CO5": {"PO1": 3, "PO2": 2, "PO5": 2, "PSO1": 2, "PSO2": 3, "PSO3": 3},
}
MAPPING = {co: {po: Decimal(s) for po, s in row.items()} for co, row in DL_MAP.items()}

R1_FINAL = ["2.52", "2.52", "2.28", "2.04", "1.56"]
R2_FINAL = ["2.52", "2.52", "2.52", "2.04", "2.04"]
R1_PO = {"PO1": "2.13", "PO2": "2.10", "PO3": "2.33", "PO4": "2.31", "PO5": "2.10",
         "PSO1": "2.10", "PSO2": "2.18", "PSO3": "2.18"}  # fmt: skip
R2_PO = {"PO1": "2.29", "PO2": "2.28", "PO3": "2.41", "PO4": "2.38", "PO5": "2.31",
         "PSO1": "2.28", "PSO2": "2.32", "PSO3": "2.32"}  # fmt: skip


def _po(final: list[str]) -> dict[str, str]:
    values = {f"CO{i + 1}": CoValue(Decimal(v), "ok") for i, v in enumerate(final)}
    out = map_to_outcomes(values, MAPPING, "blank", Trace())
    return {po: str(quantize(v.value, 2, "truncate")) for po, v in out.items() if v.value}


def test_r1_po_and_pso_values() -> None:
    assert _po(R1_FINAL) == R1_PO


def test_r2_po_and_pso_values_equal_the_colleges_report() -> None:
    assert _po(R2_FINAL) == R2_PO


# R3 batch: direct values as printed, one course carrying them all ------------------------------
R3_DIRECT = {"PO1": "2.7999", "PO9": "2.8242", "PO11": "2.7000"}
R3_TARGET = {"PO1": "2.55", "PO9": "2.86", "PO11": "2.75"}
R3_TOTAL_4DP = {"PO1": "2.8399", "PO9": "2.8594", "PO11": "2.7600"}


def _batch(compare_with: str, batch_rule: dict[str, object]):  # type: ignore[no-untyped-def]
    method = simple_method(
        {"T": {"behaviour": "question_wise", "pass_pct": 60}},
        {"T": "1"},
        final={"direct": "1", "indirect": "0"},
        precision={"default": {"mode": "truncate", "places": 2}, "batch": batch_rule,
                   "compare_with": compare_with},
    )  # fmt: skip
    course = BatchCourse("c", "synthetic carrier of R3 direct values", "core",
                         {po: Decimal(v) for po, v in R3_DIRECT.items()})  # fmt: skip
    batch = BatchInput(
        (course,),
        tuple(R3_DIRECT),
        {po: Decimal(v) for po, v in R3_TARGET.items()},
        {po: Decimal(3) for po in R3_DIRECT},
    )
    return run_batch(method, batch)


def test_r3_totals_and_unrounded_comparison_po9_is_not_attained() -> None:
    out = _batch("unrounded", {"mode": "truncate", "places": 2})
    totals = {
        po: str(quantize(v.total, 4, "round")) for po, v in out.result.outcomes.items() if v.total
    }
    assert totals == R3_TOTAL_4DP
    assert out.result.outcomes["PO1"].attained is True
    assert out.result.outcomes["PO11"].attained is True
    assert out.result.outcomes["PO9"].attained is False  # 2.85936 < 2.86
    assert "2.85936" in out.trace.text()


def test_r3_po9_is_attained_only_if_the_total_is_rounded_to_2_86_first() -> None:
    rounded = _batch("displayed", {"mode": "round", "places": 2})
    assert rounded.result.outcomes["PO9"].attained is True  # switch is configuration only
    truncated = _batch("displayed", {"mode": "truncate", "places": 2})
    assert truncated.result.outcomes["PO9"].attained is False  # 2.85 < 2.86
