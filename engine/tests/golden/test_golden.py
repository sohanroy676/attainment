"""Golden tests R1 and R2 on the anonymised Deep Learning data (DS-A).

These numbers come from ROADMAP section 3.2 and the mentor's workbook. They are never edited to
make a test pass: a change needs a written reason and a MINOR version bump.

The data file `ds_a/course.json` is produced by `scripts/build_ds_a.py` from the real workbook
(kept in gitignored data/private/) and committed only after you have checked it is anonymous.
Until it exists these tests skip, and the skip message says why.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from engine.loader import load_course
from engine.model import CourseInput, CourseResult, Override
from engine.pipeline import run
from engine.precision import quantize
from engine.schema import load_method

pytestmark = pytest.mark.golden

HERE = Path(__file__).resolve().parent
COURSE = HERE / "ds_a" / "course.json"
METHOD = HERE / "method_r1.json"

needs_data = pytest.mark.skipif(
    not COURSE.exists(),
    reason="DS-A not present: run scripts/build_ds_a.py on the workbook in data/private/",
)

COS = ["CO1", "CO2", "CO3", "CO4", "CO5"]


def _d(text: str) -> Decimal:
    return Decimal(text)


def _shown(value: Decimal | None) -> Decimal:
    assert value is not None
    return quantize(value, 2, "truncate")


def _run(overrides: bool) -> tuple[CourseInput, CourseResult]:
    course = load_course(COURSE.read_text(encoding="utf-8"))
    if overrides:
        # R2: the college's typed Internal-II pass mark (2) for each 3.5-mark part
        typed = {
            ("INT2", p.id): Override(_d("2"), "college's typed Internal-II pass mark (R2)")
            for p in course.assessments["INT2"].parts
            if p.max == _d("3.5")
        }
        course = CourseInput(
            cos=course.cos,
            students=course.students,
            assessments=course.assessments,
            overrides=typed,
            indirect=course.indirect,
            target=course.target,
        )
    result = run(load_method(METHOD.read_text(encoding="utf-8")), course).result
    return course, result


def _pct(result: CourseResult, tool: str) -> dict[str, Decimal]:
    return {
        co: _shown(result.tool_values[tool][co].percent)
        for co in COS
        if result.tool_values[tool][co].percent is not None
    }


@needs_data
def test_r1_strict_60_percent_course_2_18_not_attained() -> None:
    _, r = _run(overrides=False)
    assert [r.merged["INTERNAL"][c].value for c in COS] == [3, 3, 2, 3, 1]
    assert [r.tool_values["SEE"][c].level for c in COS] == [2, 2, 2, 1, 1]
    assert [_shown(r.direct[c].value) for c in COS] == [
        _d(x) for x in ("2.40", "2.40", "2.10", "1.80", "1.20")
    ]
    assert [_shown(r.final[c].value) for c in COS] == [
        _d(x) for x in ("2.52", "2.52", "2.28", "2.04", "1.56")
    ]
    assert r.course == _d("2.184")
    assert _shown(r.course) == _d("2.18")
    assert r.attained is False
    assert r.complete is True


@needs_data
def test_r1_percentages_per_tool() -> None:
    _, r = _run(overrides=False)
    assert _pct(r, "INT1") == {"CO1": _d("72.13"), "CO2": _d("78.17")}
    assert _pct(r, "INT2") == {"CO3": _d("57.94"), "CO4": _d("72.19"), "CO5": _d("45.97")}
    assert _pct(r, "SEE") == dict(
        zip(COS, map(_d, ("58.80", "51.06", "57.19", "46.52", "45.57")), strict=True)
    )
    for tool in ("QUIZ", "ASSIGN"):
        assert {r.tool_values[tool][c].level for c in COS} == {_d("3")}  # 67 of 67 pass


@needs_data
def test_r2_typed_internal_ii_pass_marks_course_2_32_attained() -> None:
    _, r = _run(overrides=True)
    assert _pct(r, "INT2") == {"CO3": _d("79.88"), "CO4": _d("86.86"), "CO5": _d("69.49")}
    assert [r.merged["INTERNAL"][c].value for c in COS] == [3, 3, 3, 3, 3]
    assert [_shown(r.direct[c].value) for c in COS] == [
        _d(x) for x in ("2.40", "2.40", "2.40", "1.80", "1.80")
    ]
    assert [_shown(r.final[c].value) for c in COS] == [
        _d(x) for x in ("2.52", "2.52", "2.52", "2.04", "2.04")
    ]
    assert r.course == _d("2.328")
    assert _shown(r.course) == _d("2.32")
    assert r.attained is True


@needs_data
def test_float_trap_co1_is_2_52_in_the_real_data() -> None:
    _, r = _run(overrides=False)
    assert r.final["CO1"].value == _d("2.52")


@needs_data
def test_golden_run_is_repeatable() -> None:
    from engine.hashing import output_hash

    _, first = _run(overrides=False)
    _, second = _run(overrides=False)
    assert output_hash(first) == output_hash(second)


def test_golden_method_file_is_valid_without_the_data() -> None:
    method = load_method(METHOD.read_text(encoding="utf-8"))
    assert method.direct["SEE"] == _d("0.60")
    assert method.tools["SEE"].choice["G"].best_n == 5  # type: ignore[union-attr]
