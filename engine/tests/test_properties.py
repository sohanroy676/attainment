"""Property tests: things that must hold for any marks."""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.hashing import output_hash
from engine.pipeline import run

from .builders import assessment, course, parts, simple_method

pytestmark = pytest.mark.property

METHOD = simple_method(
    {"T": {"behaviour": "question_wise", "pass_pct": 60}},
    {"T": "1"},
    final={"direct": "1", "indirect": "0"},
    levels={"bands": [{"min_pct": 0, "level": 1}]},
)
PAPER = parts([("a", "1", 10, "CO1", None), ("b", "2", 10, "CO1", "G")])

mark = st.one_of(st.none(), st.just("A"), st.integers(0, 10))
rows = st.dictionaries(
    st.text("abcdefgh", min_size=1, max_size=3),
    st.fixed_dictionaries({"a": mark, "b": mark}),
    min_size=1,
    max_size=12,
)


@given(rows)
@settings(max_examples=60, deadline=None)
def test_percentages_stay_between_0_and_100_and_runs_are_repeatable(
    data: dict[str, dict[str, object]],
) -> None:
    a = assessment("T", PAPER, data)
    first = run(METHOD, course([a]))
    value = first.result.tool_values["T"]["CO1"].percent
    assert value is None or Decimal(0) <= value <= Decimal(100)
    assert output_hash(first.result) == output_hash(run(METHOD, course([a])).result)


@given(rows, st.data())
@settings(max_examples=60, deadline=None)
def test_a_better_mark_never_lowers_the_class_percentage(
    data: dict[str, dict[str, object]], draw: st.DataObject
) -> None:
    """Raising one entered mark can only add passes. The denominator for a compulsory part is
    unchanged, so the percentage cannot fall."""
    student = draw.draw(st.sampled_from(sorted(data)))
    before = data[student]["a"]
    if not isinstance(before, int):
        return
    better = {
        **data,
        student: {**data[student], "a": min(10, before + draw.draw(st.integers(0, 10)))},
    }
    low = run(METHOD, course([assessment("T", PAPER, data)])).result.tool_values["T"]["CO1"].percent
    high = (
        run(METHOD, course([assessment("T", PAPER, better)])).result.tool_values["T"]["CO1"].percent
    )
    assert low is not None and high is not None
    assert high >= low


@given(st.lists(st.integers(0, 10), min_size=1, max_size=30))
@settings(max_examples=60, deadline=None)
def test_pass_percentage_equals_the_exact_fraction(marks: list[int]) -> None:
    paper = parts([("a", "1", 10, "CO1", None)])
    a = assessment("T", paper, {f"s{i}": {"a": m} for i, m in enumerate(marks)})
    out = run(METHOD, course([a])).result.tool_values["T"]["CO1"].percent
    passed = sum(1 for m in marks if m >= 6)
    assert out == Decimal(passed) * 100 / Decimal(len(marks))
