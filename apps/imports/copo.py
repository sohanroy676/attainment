"""Import a course's outcomes and its CO-PO map from a sheet (.csv or .xlsx).

Layout: the first row is `CO`, optionally `Text`, then the programme outcome codes (PO1, PSO2 ...).
Each following row is one CO: its code, its text, then one cell per outcome. A cell is empty
(not mapped), 0, 1, 2 or 3. Everything is checked before anything is saved.
"""

from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academics.models import Course, Programme
from apps.accounts.models import User
from apps.outcomes import services as outcomes
from apps.outcomes.models import CourseDefinitionVersion, ProgrammeOutcome

from .parsers import UnreadableFile, _csv_rows, _xlsx_rows


@dataclass
class CopoSheet:
    cos: list[tuple[str, str]] = field(default_factory=list)  # (code, text)
    grid: dict[str, dict[str, int | None]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def parse_copo(filename: str, content: bytes, programme: Programme) -> CopoSheet:
    lowered = filename.lower()
    if lowered.endswith(".xlsx"):
        rows = _xlsx_rows(content)
    elif lowered.endswith(".csv"):
        rows = _csv_rows(content)
    else:
        raise UnreadableFile("Please upload a .csv or .xlsx file.")
    if not rows:
        raise UnreadableFile("The file is empty.")
    header = [h.strip() for h in rows[0]]
    if not header or header[0].lower() != "co":
        raise UnreadableFile("The first cell of the first row must be 'CO'.")
    text_col = 1 if len(header) > 1 and header[1].lower() == "text" else None
    first_outcome = 2 if text_col is not None else 1
    known = {o.code for o in ProgrammeOutcome.objects.filter(programme=programme)}
    sheet = CopoSheet()
    for col in range(first_outcome, len(header)):
        if header[col] and header[col] not in known:
            sheet.problems.append(
                f"Column {col + 1}: {header[col]} is not an outcome of this programme."
            )
    for number, row in enumerate(rows[1:], start=2):
        code = row[0].strip() if row else ""
        if not code:
            continue
        if code in sheet.grid:
            sheet.problems.append(f"Row {number}: {code} appears again.")
            continue
        sheet.cos.append(
            (code, row[text_col].strip() if text_col is not None and text_col < len(row) else "")
        )
        sheet.grid[code] = {}
        for col in range(first_outcome, len(header)):
            if not header[col] or header[col] not in known:
                continue
            raw = row[col].strip() if col < len(row) else ""
            if raw == "":
                sheet.grid[code][header[col]] = None
            elif raw in {"0", "1", "2", "3"}:
                sheet.grid[code][header[col]] = int(raw)
            else:
                sheet.problems.append(
                    f"Row {number}, {header[col]}: {raw!r} is not allowed "
                    "(use blank, 0, 1, 2 or 3)."
                )
    if not sheet.cos:
        sheet.problems.append("The sheet has no course outcomes.")
    return sheet


def import_copo(
    course: Course, programme: Programme, filename: str, content: bytes, actor: User | None = None
) -> CourseDefinitionVersion:
    """Create the course's next definition with the sheet's COs and save the map. All or nothing."""
    sheet = parse_copo(filename, content, programme)
    if sheet.problems:
        raise ValidationError(sheet.problems)
    with transaction.atomic():
        definition = outcomes.create_definition(course, sheet.cos, actor=actor)
        outcomes.save_mapping_grid(definition, programme, sheet.grid, actor=actor)
    return definition
