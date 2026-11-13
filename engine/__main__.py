"""Command line.

python -m engine run   <method.json> <marks.json> [--trace] [--json]   (course or offering)
python -m engine batch <method.json> <batch.json> [--trace] [--json]
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from .batch import BatchResult, batch_output_hash, batch_result_to_dict, run_batch
from .display import display
from .errors import EngineError, MethodConfigError
from .hashing import output_hash, result_to_dict
from .loader import is_offering, load_batch, load_course, load_offering
from .model import CourseResult, CoValue
from .pipeline import run, run_offering
from .precision import decimal_text
from .schema import MethodConfig, load_method
from .trace import Trace

COLUMN = 10


def _row(label: str, cells: list[str]) -> str:
    return f"{label:<18}" + "".join(f"{cell:>{COLUMN}}" for cell in cells)


def _co_text(method: MethodConfig, value: CoValue | None, level: str = "co") -> str:
    if value is None or value.value is None:
        return "blocked" if value is not None and value.status == "blocked" else "-"
    return str(display(method.precision, level, value.value))


def _percent_text(method: MethodConfig, percent: Decimal | None) -> str:
    return "-" if percent is None else str(display(method.precision, "question_pct", percent))


def format_course(method: MethodConfig, result: CourseResult, cos: tuple[str, ...]) -> str:
    lines = [
        f"Method: {method.name}   engine {result.engine_version}   input {result.input_hash[:12]}",
        _row("", list(cos)),
    ]
    for tool, tool_cos in result.tool_values.items():
        lines.append(_row(f"{tool} %", [_percent_text(method, tool_cos[c].percent) for c in cos]))
        levels = [decimal_text(tool_cos[c].level) or tool_cos[c].status for c in cos]
        lines.append(_row(f"{tool} level", levels))
    for name, merged in result.merged.items():
        lines.append(_row(f"{name} merged", [_co_text(method, merged[c]) for c in cos]))
    lines.append(_row("Direct", [_co_text(method, result.direct[c]) for c in cos]))
    entered = [decimal_text(result.indirect.get(c)) or "-" for c in cos]
    lines.append(_row("Indirect (entered)", entered))
    lines.append(_row("Final", [_co_text(method, result.final[c]) for c in cos]))
    if result.course is None:
        lines.append("Course attainment: no value")
    else:
        shown = display(method.precision, "course", result.course)
        status = {True: "Attained", False: "Not attained", None: "no target set"}[result.attained]
        lines.append(
            f"Course attainment: {shown}  (unrounded {decimal_text(result.course)})  {status}"
        )
    if result.po:
        names = list(result.po)
        lines.append(_row("Outcome", names))
        lines.append(_row("Value", [_co_text(method, result.po[p], "po") for p in names]))
    lines.append("Data: " + ("complete" if result.complete else "PROVISIONAL"))
    lines.extend(f"Flag: {flag}" for flag in result.flags)
    return "\n".join(lines)


def format_batch(method: MethodConfig, result: BatchResult) -> str:
    lines = [
        f"Method: {method.name}   engine {result.engine_version}   input {result.input_hash[:12]}",
        _row("Outcome", ["courses", "direct", "total", "target", "status"]),
    ]
    for outcome, v in result.outcomes.items():
        direct = "-" if v.direct is None else str(display(method.precision, "batch", v.direct))
        total = "-" if v.total is None else str(display(method.precision, "batch", v.total))
        status = {True: "Attained", False: "NOT", None: v.status}[v.attained]
        target = decimal_text(v.target) or "-"
        lines.append(_row(outcome, [str(v.courses_with_value), direct, total, target, status]))
    for category, c in result.counts.items():
        lines.append(
            f"{category}: {c.attained} attained, {c.not_attained} not attained, "
            f"{c.no_result} without a result"
        )
    lines.append("Data: " + ("complete" if result.complete else "PROVISIONAL"))
    lines.extend(f"Flag: {flag}" for flag in result.flags)
    return "\n".join(lines)


def _run_command(args: argparse.Namespace) -> tuple[str, Trace]:
    method = load_method(args.method.read_text(encoding="utf-8"))
    text = args.marks.read_text(encoding="utf-8")
    parts: list[str] = []
    if is_offering(text):
        offering = load_offering(text)
        out = run_offering(method, offering)
        result, trace, cos = out.result, out.trace, offering.cos
        body = result_to_dict(result)
        body["sections"] = {s: result_to_dict(o.result) for s, o in out.sections.items()}
        parts.append(
            f"Offering rolled up at stage '{method.rollup.stage}' ({method.rollup.method})"
        )
        for section, section_out in out.sections.items():
            parts.append(f"  section {section}: course {decimal_text(section_out.result.course)}")
    else:
        course = load_course(text)
        single = run(method, course)
        result, trace, cos = single.result, single.trace, course.cos
        body = result_to_dict(result)
    body["output_hash"] = output_hash(result)
    if args.json:
        return json.dumps(body, indent=2, sort_keys=True), trace
    parts.append(format_course(method, result, cos))
    parts.append(f"Output hash: {body['output_hash']}")
    return "\n".join(parts), trace


def _batch_command(args: argparse.Namespace) -> tuple[str, Trace]:
    method = load_method(args.method.read_text(encoding="utf-8"))
    out = run_batch(method, load_batch(args.marks.read_text(encoding="utf-8")))
    if args.json:
        body = batch_result_to_dict(out.result)
        body["output_hash"] = batch_output_hash(out.result)
        return json.dumps(body, indent=2, sort_keys=True), out.trace
    text = format_batch(method, out.result) + f"\nOutput hash: {batch_output_hash(out.result)}"
    return text, out.trace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m engine")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("run", "calculate a course or offering"),
        ("batch", "roll up a batch"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("method", type=Path)
        command.add_argument("marks", type=Path)
        command.add_argument("--trace", action="store_true", help="print the explanation trace")
        command.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)
    try:
        text, trace = _batch_command(args) if args.command == "batch" else _run_command(args)
    except (MethodConfigError, EngineError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(text)
    if args.trace:
        print()
        print(trace.text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
