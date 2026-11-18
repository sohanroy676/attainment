"""Command line: python -m engine run <method.json> <marks.json> [--trace] [--json]."""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from .errors import EngineError, MethodConfigError
from .hashing import output_hash, result_to_dict
from .loader import load_course
from .model import CourseResult, CoValue
from .pipeline import run
from .precision import decimal_text, quantize
from .schema import MethodConfig, PrecisionRule, load_method


def _shown(value: CoValue | None, method: MethodConfig, level: str = "co") -> str:
    if value is None or value.value is None:
        return "blocked" if value is not None and value.status == "blocked" else "-"
    rule = (
        method.precision.co if level == "co" else method.precision.course
    ) or method.precision.default
    return str(quantize(value.value, rule.places, rule.mode))


def _percent_text(percent: Decimal | None, rule: PrecisionRule) -> str:
    if percent is None:
        return "-"
    return str(quantize(percent, rule.places, rule.mode))


def format_tables(method: MethodConfig, result: CourseResult, cos: tuple[str, ...]) -> str:
    rule = method.precision.default
    lines = [
        f"Method: {method.name}   engine {result.engine_version}   input {result.input_hash[:12]}"
    ]
    header = "".join(f"{co:>10}" for co in cos)
    lines.append(f"{'':<14}{header}")
    for tool, tool_cos in result.tool_values.items():
        pct = "".join(f"{_percent_text(tool_cos[c].percent, rule):>10}" for c in cos)
        level = "".join(f"{decimal_text(tool_cos[c].level) or tool_cos[c].status:>10}" for c in cos)
        lines.append(f"{tool + ' %':<14}{pct}")
        lines.append(f"{tool + ' level':<14}{level}")
    for name, merged_cos in result.merged.items():
        lines.append(
            f"{name + ' merged':<14}" + "".join(f"{_shown(merged_cos[c], method):>10}" for c in cos)
        )
    lines.append(
        f"{'Direct':<14}" + "".join(f"{_shown(result.direct[c], method):>10}" for c in cos)
    )
    lines.append(f"{'Final':<14}" + "".join(f"{_shown(result.final[c], method):>10}" for c in cos))
    if result.course is None:
        lines.append("Course attainment: no value")
    else:
        shown = _shown(CoValue(result.course, "ok"), method, "course")
        status = {True: "Attained", False: "Not attained", None: "no target set"}[result.attained]
        lines.append(
            f"Course attainment: {shown}  (unrounded {decimal_text(result.course)})  {status}"
        )
    lines.append("Data: " + ("complete" if result.complete else "PROVISIONAL"))
    lines.extend(f"Flag: {flag}" for flag in result.flags)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m engine")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="calculate one course")
    run_parser.add_argument("method", type=Path)
    run_parser.add_argument("marks", type=Path)
    run_parser.add_argument("--trace", action="store_true", help="print the explanation trace")
    run_parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)
    try:
        method = load_method(args.method.read_text(encoding="utf-8"))
        course = load_course(args.marks.read_text(encoding="utf-8"))
        output = run(method, course)
    except (MethodConfigError, EngineError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        body = result_to_dict(output.result)
        body["output_hash"] = output_hash(output.result)
        print(json.dumps(body, indent=2, sort_keys=True))
    else:
        print(format_tables(method, output.result, course.cos))
        print(f"Output hash: {output_hash(output.result)}")
    if args.trace:
        print()
        print(output.trace.text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
