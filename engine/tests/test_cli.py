"""The command line runner (M1 in automatic form)."""

import json
from pathlib import Path

import pytest

from engine.__main__ import main

from .builders import BASE_METHOD

pytestmark = pytest.mark.unit


def _marks() -> dict[str, object]:
    def tool(name: str, passed: int) -> dict[str, object]:
        return {
            "parts": [{"id": "p", "question": "1", "max": 10, "co": "CO1"}],
            "marks": {f"s{i}": {"p": 10 if i < passed else 0} for i in range(10)},
        }

    quiz = {
        "parts": [{"id": f"i{k}", "question": str(k), "max": 5} for k in range(3)],
        "marks": {f"s{i}": {f"i{k}": 5 for k in range(3)} for i in range(10)},
    }
    return {
        "cos": ["CO1"],
        "students": [f"s{i}" for i in range(10)],
        "target": 2.2,
        "indirect": {"CO1": 3},
        "assessments": {
            "INT1": tool("INT1", 10),
            "INT2": tool("INT2", 5),
            "SEE": tool("SEE", 5),
            "QUIZ": quiz,
            "ASSIGN": quiz,
        },
    }


def _write(tmp_path: Path, method: object, marks: object) -> tuple[Path, Path]:
    m, d = tmp_path / "method.json", tmp_path / "marks.json"
    m.write_text(json.dumps(method), encoding="utf-8")
    d.write_text(json.dumps(marks), encoding="utf-8")
    return m, d


def test_run_prints_the_tables_and_the_course_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    m, d = _write(tmp_path, BASE_METHOD, _marks())
    assert main(["run", str(m), str(d)]) == 0
    out = capsys.readouterr().out
    assert "SEE level" in out and "INTERNAL merged" in out
    assert "Final" in out and "Course attainment: 2.4" in out
    assert "Attained" in out and "Data: complete" in out and "Output hash:" in out


def test_trace_and_json_flags(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    m, d = _write(tmp_path, BASE_METHOD, _marks())
    assert main(["run", str(m), str(d), "--trace"]) == 0
    assert "[QuestionPass] SEE/p:" in capsys.readouterr().out
    assert main(["run", str(m), str(d), "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["course"] == "2.4" and body["complete"] is True and len(body["output_hash"]) == 64


def test_invalid_method_exits_with_a_message_naming_the_field(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = {**BASE_METHOD, "direct": {**BASE_METHOD["direct"], "SEE": "0.80"}}
    m, d = _write(tmp_path, bad, _marks())
    assert main(["run", str(m), str(d)]) == 2
    assert "direct" in capsys.readouterr().err


def test_override_without_a_reason_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    marks = _marks() | {"overrides": [{"tool": "SEE", "part": "p", "pass_mark": 2, "reason": " "}]}
    m, d = _write(tmp_path, BASE_METHOD, marks)
    assert main(["run", str(m), str(d)]) == 2
    assert "reason" in capsys.readouterr().err


def test_missing_file_is_a_clean_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", str(tmp_path / "nope.json"), str(tmp_path / "nope2.json")]) == 2
    assert "error:" in capsys.readouterr().err
