"""A5: sections of one offering rolled into the course, at each stage."""

from decimal import Decimal

import pytest

from engine.errors import EngineError
from engine.model import OfferingInput
from engine.pipeline import run_offering
from engine.schema import MethodConfig

from .builders import class_with_pass_rate, course, simple_method

pytestmark = pytest.mark.unit


def _method(stage: str, how: str = "mean") -> MethodConfig:
    return simple_method(
        {"T": {"behaviour": "question_wise", "pass_pct": 60}},
        {"T": "1"},
        final={"direct": "1", "indirect": "0"},
        rollup={"stage": stage, "method": how},
    )


def _offering(sizes: tuple[int, int] = (10, 10)) -> OfferingInput:
    """Section A passes everyone (level 3); section B passes half (50%, level 2)."""
    a = course([class_with_pass_rate("T", sizes[0], sizes[0])])
    b = course([class_with_pass_rate("T", sizes[1] // 2, sizes[1])])
    return OfferingInput(cos=("CO1",), sections={"A": a, "B": b})


@pytest.mark.parametrize("stage", ["pct", "level", "attainment"])
def test_a5_course_is_the_mean_of_the_sections_and_each_section_stays_visible(stage: str) -> None:
    out = run_offering(_method("attainment" if stage == "attainment" else stage), _offering())
    assert out.sections["A"].result.course == 3
    assert out.sections["B"].result.course == 2
    expected = {"attainment": Decimal("2.5"), "level": Decimal("2.5"), "pct": Decimal(3)}[stage]
    # pct: the mean percentage is 75, which is level 3; the other stages average 3 and 2
    assert out.result.course == expected


def test_a5_percentage_stage_shows_the_rolled_percentage() -> None:
    out = run_offering(_method("pct"), _offering())
    assert out.result.tool_values["T"]["CO1"].percent == 75
    assert "rolled up at stage 'pct'" in out.trace.text()


def test_a5_weighted_by_students_gives_the_larger_section_more_weight() -> None:
    offering = _offering((10, 30))
    plain = run_offering(_method("attainment", "mean"), offering)
    weighted = run_offering(_method("attainment", "weighted_by_students"), offering)
    assert plain.result.course == Decimal("2.5")
    assert weighted.result.course == Decimal("2.25")  # (3 x 10 + 2 x 30) / 40
    pct = run_offering(_method("pct", "weighted_by_students"), offering)
    assert pct.result.tool_values["T"]["CO1"].percent == Decimal("62.5")  # (100x10 + 50x30)/40


def test_a_blocked_section_blocks_the_course_instead_of_being_ignored() -> None:
    good = course([class_with_pass_rate("T", 10, 10)])
    bad = course([class_with_pass_rate("T", 0, 20)])  # 0% is below the lowest band
    offering = OfferingInput(cos=("CO1",), sections={"A": good, "B": bad})
    for stage in ("level", "attainment"):
        out = run_offering(_method(stage), offering)
        assert out.result.complete is False
        assert out.result.final["CO1"].status == "blocked"


def test_a_section_with_no_value_for_a_co_is_skipped_in_the_mean() -> None:
    a = course([class_with_pass_rate("T", 10, 10)])
    empty = course([], students=("x",))
    method = simple_method(
        {"T": {"behaviour": "question_wise", "pass_pct": 60}},
        {"T": "1"},
        final={"direct": "1", "indirect": "0"},
        missing_data="renormalise",
    )
    out = run_offering(method, OfferingInput(cos=("CO1",), sections={"A": a, "B": empty}))
    assert out.result.final["CO1"].value == 3


def test_offering_without_sections_is_refused() -> None:
    with pytest.raises(EngineError, match="at least one section"):
        run_offering(_method("attainment"), OfferingInput(cos=("CO1",), sections={}))


def test_section_order_does_not_matter() -> None:
    forward = _offering()
    backward = OfferingInput(cos=("CO1",), sections=dict(reversed(list(forward.sections.items()))))
    assert run_offering(_method("attainment"), forward).result.input_hash == (
        run_offering(_method("attainment"), backward).result.input_hash
    )
