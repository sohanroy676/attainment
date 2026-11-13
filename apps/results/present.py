"""Turns a stored run into rows a page or an Excel sheet can show. No calculation happens here:
every number was computed by the engine; this only applies the method's display rounding."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from apps.methodology import services as methods
from engine.display import display
from engine.schema import MethodConfig

from .models import CalculationRun


@dataclass
class Cell:
    text: str
    key: str = ""  # explain key, empty when there is nothing to explain
    note: str = ""
    edge: bool = False  # the shown value sits on a band edge the full value does not reach


@dataclass
class Table:
    title: str
    header: list[str]
    rows: list[tuple[str, list[Cell]]] = field(default_factory=list)


@dataclass
class Presented:
    run: CalculationRun
    method_name: str
    status: str
    complete: bool
    checklist: list[str]
    flags: list[str]
    tables: list[Table]
    course_text: str
    course_unrounded: str
    attained: bool | None
    target: str
    indirect_label: str


def _config(run: CalculationRun) -> MethodConfig | None:
    return (
        None if run.method_version is None else methods.parse_config(run.method_version.config_text)
    )


def _shown(config: MethodConfig, level: str, text: str | None) -> str:
    return "-" if text is None else str(display(config.precision, level, Decimal(text)))


def _edge(config: MethodConfig, text: str | None) -> bool:
    if text is None:
        return False
    full = Decimal(text)
    shown = display(config.precision, "question_pct", full)
    return any(full < band.min_pct <= shown for band in config.levels.bands)


def present(run: CalculationRun, section_name: str | None = None) -> Presented:
    """The course result, or one section's result when `section_name` is given."""
    config = _config(run)
    out = run.outputs or {}
    data: dict[str, Any] | None = (
        out.get("course") if section_name is None else out.get("sections", {}).get(section_name)
    )
    base = {
        "run": run,
        "method_name": "" if run.method_version is None else str(run.method_version),
        "status": run.status,
        "complete": run.status == "complete",
        "checklist": list(run.checklist),
    }
    if config is None or data is None:
        return Presented(
            **base, flags=[], tables=[], course_text="-", course_unrounded="",
            attained=None, target="", indirect_label="",
        )  # fmt: skip
    cos: list[str] = out["cos"]
    tables: list[Table] = []
    tool_table = Table("Tools", cos)
    for tool, per_co in data["tools"].items():
        tool_table.rows.append(
            (
                f"{tool} %",
                [
                    Cell(
                        _shown(config, "question_pct", per_co[c][0]),
                        f"{tool}/{c}",
                        edge=_edge(config, per_co[c][0]),
                    )
                    for c in cos
                ],
            )
        )
        tool_table.rows.append(
            (f"{tool} level", [Cell(per_co[c][1] or per_co[c][2], f"{tool}/{c}") for c in cos])
        )
    tables.append(tool_table)
    final_table = Table("Course outcomes", cos)
    for name, per_co in data["merged"].items():
        final_table.rows.append(
            (
                f"{name} (merged)",
                [Cell(_shown(config, "co", per_co[c][0]), f"{name}/{c}") for c in cos],
            )
        )
    final_table.rows.append(
        ("Direct", [Cell(_shown(config, "co", data["direct"][c][0]), f"direct/{c}") for c in cos])
    )
    final_table.rows.append(
        ("Indirect (entered, not measured)", [Cell(data["indirect"].get(c) or "-") for c in cos])
    )
    final_table.rows.append(
        ("Final", [Cell(_shown(config, "co", data["final"][c][0]), f"final/{c}") for c in cos])
    )
    tables.append(final_table)
    if data.get("po"):
        outcomes = list(data["po"])
        po_table = Table("Programme outcomes", outcomes)
        po_table.rows.append(
            ("Value", [Cell(_shown(config, "po", data["po"][p][0]), p) for p in outcomes])
        )
        tables.append(po_table)
    return Presented(
        **base,
        flags=list(data["flags"]),
        tables=tables,
        course_text=_shown(config, "course", data["course"]),
        course_unrounded=data["course"] or "",
        attained=data["attained"],
        target=data["target"] or "",
        indirect_label="entered, not measured; direct-only is shown above",
    )
