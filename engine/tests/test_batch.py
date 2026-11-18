"""Batch roll-up, count status, and the batch and offering command lines."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from engine.__main__ import main
from engine.batch import (
    BatchCourse,
    BatchInput,
    batch_output_hash,
    course_for_batch,
    run_batch,
)
from engine.model import CourseResult, CoValue
from engine.pipeline import run

from .builders import BASE_METHOD, class_with_pass_rate, course, method, simple_method

pytestmark = pytest.mark.unit

D = Decimal
OUTCOMES = ("PO1", "PO2")


def _batch(courses: list[BatchCourse], indirect: dict[str, str] | None = None) -> BatchInput:
    return BatchInput(
        tuple(courses),
        OUTCOMES,
        {"PO1": D("2.5"), "PO2": D("2.5")},
        {po: D(v) for po, v in (indirect or {"PO1": "3", "PO2": "3"}).items()},
    )


def _course(
    cid: str, category: str, po1: str | None, po2: str | None, attained: bool | None = True
) -> BatchCourse:
    values = {"PO1": None if po1 is None else D(po1), "PO2": None if po2 is None else D(po2)}
    return BatchCourse(cid, cid, category, values, attained)


def test_direct_is_the_simple_average_and_total_adds_the_entered_indirect() -> None:
    out = run_batch(
        method(), _batch([_course("a", "core", "2", "3"), _course("b", "core", "3", "3")])
    )
    po1 = out.result.outcomes["PO1"]
    assert (po1.courses_with_value, po1.direct, po1.indirect) == (2, D("2.5"), D(3))
    assert po1.total == D("0.8") * D("2.5") + D("0.2") * 3  # 2.6
    assert po1.attained is True and po1.status == "ok"


def test_a_blank_course_value_is_skipped_but_a_zero_counts() -> None:
    courses = [
        _course("a", "core", "3", None),
        _course("b", "core", "0", "3"),
        _course("c", "core", None, "3"),
    ]
    out = run_batch(method(), _batch(courses))
    assert out.result.outcomes["PO1"].courses_with_value == 2
    assert out.result.outcomes["PO1"].direct == D("1.5")  # (3 + 0) / 2: the zero is a value
    assert out.result.outcomes["PO2"].courses_with_value == 2
    assert out.result.outcomes["PO2"].direct == 3


def test_outcome_with_no_course_value_is_missing_not_zero() -> None:
    out = run_batch(method(), _batch([_course("a", "core", None, "3")]))
    po1 = out.result.outcomes["PO1"]
    assert (po1.status, po1.direct, po1.total, po1.attained) == ("missing", None, None, None)
    assert "no course has a value" in out.trace.text()


def test_missing_indirect_value_stops_the_outcome_for_review() -> None:
    out = run_batch(method(), _batch([_course("a", "core", "3", "3")], indirect={"PO2": "3"}))
    assert out.result.outcomes["PO1"].status == "blocked"
    assert out.result.complete is False and out.result.outcomes["PO1"].direct == 3


def test_count_status_by_category() -> None:
    courses = [
        _course("a", "core", "3", "3", True),
        _course("b", "core", "3", "3", False),
        _course("c", "core", "3", "3", True),
        _course("d", "non_core", "3", "3", True),
        _course("e", "non_core", "3", "3", None),
    ]
    counts = run_batch(method(), _batch(courses)).result.counts
    assert (counts["core"].attained, counts["core"].not_attained, counts["core"].no_result) == (
        2,
        1,
        0,
    )
    assert (
        counts["non_core"].attained,
        counts["non_core"].not_attained,
        counts["non_core"].no_result,
    ) == (1, 0, 1)


def test_batch_weights_come_from_the_method() -> None:
    m = simple_method(
        {"T": {"behaviour": "question_wise", "pass_pct": 60}}, {"T": "1"},
        final={"direct": "1", "indirect": "0"}, batch={"direct": "0.5", "indirect": "0.5"},
    )  # fmt: skip
    out = run_batch(m, _batch([_course("a", "core", "2", "2")], {"PO1": "3", "PO2": "3"}))
    assert out.result.outcomes["PO1"].total == D("2.5")


def test_batch_near_target_flag_and_repeatable_hash() -> None:
    batch = _batch([_course("a", "core", "2.4", "2.4")], {"PO1": "3.05", "PO2": "3.05"})
    # total = 0.8 x 2.4 + 0.2 x 3.05 = 2.53; target 2.5 is within 0.05? margin default 0.01: no flag
    first = run_batch(method(), batch)
    assert first.result.flags == ()
    close = BatchInput(
        batch.courses, batch.outcomes, {"PO1": D("2.52"), "PO2": D("2.52")}, batch.indirect
    )
    flagged = run_batch(method(), close)
    assert any("within 0.01" in f for f in flagged.result.flags)  # 2.53 against 2.52
    assert batch_output_hash(first.result) == batch_output_hash(run_batch(method(), batch).result)


def test_a_course_result_feeds_the_batch() -> None:
    from engine.model import CourseInput  # noqa: F401  (documented type of the source)

    m = simple_method(
        {"T": {"behaviour": "question_wise", "pass_pct": 60}}, {"T": "1"},
        final={"direct": "1", "indirect": "0"},
    )  # fmt: skip
    data = course([class_with_pass_rate("T", 10, 10)], target="2")
    data = CourseInput(
        data.cos, data.students, data.assessments, mapping={"CO1": {"PO1": D(2)}}, target=D(2)
    )
    result = run(m, data).result
    entry = course_for_batch("c1", "Course 1", "core", result)
    assert entry.po_values == {"PO1": D(3)} and entry.attained is True
    assert isinstance(result, CourseResult) and isinstance(result.po["PO1"], CoValue)


# command line ----------------------------------------------
def _write(tmp_path: Path, name: str, body: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_batch_command_prints_the_table_and_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch = {
        "outcomes": ["PO1"], "targets": {"PO1": 2.5}, "indirect": {"PO1": 3},
        "courses": [{"id": "a", "category": "core", "attained": True, "po": {"PO1": 2.5}}],
    }  # fmt: skip
    m, b = _write(tmp_path, "m.json", BASE_METHOD), _write(tmp_path, "b.json", batch)
    assert main(["batch", str(m), str(b), "--trace"]) == 0
    out = capsys.readouterr().out
    assert "PO1" in out and "Attained" in out and "core: 1 attained" in out
    assert "[BatchRollUp] PO1" in out
    assert main(["batch", str(m), str(b), "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["outcomes"]["PO1"][3] == "2.6" and len(body["output_hash"]) == 64


def test_run_command_handles_an_offering_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def section(passed: int) -> dict[str, object]:
        return {
            "students": [f"s{i}" for i in range(10)],
            "assessments": {"T": {
                "parts": [{"id": "p", "question": "1", "max": 10, "co": "CO1"}],
                "marks": {f"s{i}": {"p": 10 if i < passed else 0} for i in range(10)},
            }},
        }  # fmt: skip

    offering = {"cos": ["CO1"], "indirect": {}, "sections": {"A": section(10), "B": section(5)}}
    method_json = {
        **BASE_METHOD, "tools": {"T": {"behaviour": "question_wise", "pass_pct": 60}}, "merge": {},
        "direct": {"T": "1"}, "final": {"direct": "1", "indirect": "0"},
    }  # fmt: skip
    m, o = _write(tmp_path, "m.json", method_json), _write(tmp_path, "o.json", offering)
    assert main(["run", str(m), str(o)]) == 0
    out = capsys.readouterr().out
    assert "Offering rolled up at stage 'attainment'" in out
    assert "section A: course 3" in out and "section B: course 2" in out
    assert "Course attainment: 2.5" in out


def test_batch_file_errors_are_reported_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    m, b = _write(tmp_path, "m.json", BASE_METHOD), _write(tmp_path, "b.json", {"outcomes": []})
    assert main(["batch", str(m), str(b)]) == 2
    assert "batch file is not valid" in capsys.readouterr().err
