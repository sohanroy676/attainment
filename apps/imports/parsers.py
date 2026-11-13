"""Reading uploaded roster files (.csv and .xlsx). Nothing here touches the database.

Excel files are read for cached values only (openpyxl data_only): formulas are never evaluated.
The file's type is checked by its content, not only its name.
"""

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 5000
ROLL_HEADERS = {"roll_no", "roll no", "roll number", "rollno", "roll", "roll_number"}
NAME_HEADERS = {"name", "student name", "student_name", "student"}
ZIP_MAGIC = b"PK\x03\x04"


@dataclass(frozen=True)
class RosterRow:
    row: int  # the row number in the file, header = 1
    roll_no: str
    name: str


@dataclass(frozen=True)
class RowError:
    row: int
    message: str


@dataclass
class ParsedRoster:
    rows: list[RosterRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


class UnreadableFile(Exception):
    """The file is not a roster we can read at all (wrong type, too big, no header)."""


def parse_roster(filename: str, content: bytes) -> ParsedRoster:
    if len(content) > MAX_BYTES:
        raise UnreadableFile("The file is larger than 10 MB.")
    lowered = filename.lower()
    if lowered.endswith(".xlsx"):
        if not content.startswith(ZIP_MAGIC):
            raise UnreadableFile("This is not a real Excel (.xlsx) file.")
        raw_rows = _xlsx_rows(content)
    elif lowered.endswith(".csv"):
        raw_rows = _csv_rows(content)
    else:
        raise UnreadableFile("Please upload a .csv or .xlsx file.")
    return _validate(raw_rows)


def _csv_rows(content: bytes) -> list[list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise UnreadableFile("The file is not UTF-8 text; save it as CSV UTF-8.") from error
    return [list(row) for row in csv.reader(io.StringIO(text))]


def _xlsx_rows(content: bytes) -> list[list[str]]:
    import openpyxl

    try:
        # defusedxml (installed) makes openpyxl refuse entity-expansion and external-entity files
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        sheet = workbook.worksheets[0]
        rows = [[_cell_text(c) for c in row] for row in sheet.iter_rows(values_only=True)]
        workbook.close()
    except Exception as error:  # noqa: BLE001 - an upload may fail in many ways; all mean "unreadable"
        raise UnreadableFile(
            "The Excel file could not be opened or is not safe to read."
        ) from error
    uncached = _uncached_formulas(content)
    if uncached:
        raise UnreadableFile(
            f"Cell {uncached[0]} holds a formula with no stored result. Open the file in Excel, "
            "save it, and upload it again (formulas are never calculated here)."
        )
    return rows


def _uncached_formulas(content: bytes) -> list[str]:
    """Cells that hold a formula whose cached value was never saved (so data_only reads None)."""
    import openpyxl

    try:
        formulas = openpyxl.load_workbook(io.BytesIO(content), data_only=False, read_only=True)
        values = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        found = []
        for f_row, v_row in zip(
            formulas.worksheets[0].iter_rows(), values.worksheets[0].iter_rows(), strict=False
        ):
            for f_cell, v_cell in zip(f_row, v_row, strict=False):
                if (
                    isinstance(f_cell.value, str)
                    and f_cell.value.startswith("=")
                    and v_cell.value is None
                ):
                    found.append(f_cell.coordinate)
        formulas.close()
        values.close()
    except Exception:  # noqa: BLE001 - the first load already vouched for the file
        return []
    return found


def _cell_text(value: object) -> str:
    """A cell as text. Whole numbers typed as 1.0 by Excel become '1'."""
    if value is None:
        return ""
    if isinstance(value, float | Decimal) and value == int(value):
        return str(int(value))
    return str(value).strip()


def _validate(raw_rows: list[list[str]]) -> ParsedRoster:
    if not raw_rows:
        raise UnreadableFile("The file is empty.")
    header = [h.strip().lower() for h in raw_rows[0]]
    roll_col = next((i for i, h in enumerate(header) if h in ROLL_HEADERS), None)
    name_col = next((i for i, h in enumerate(header) if h in NAME_HEADERS), None)
    if roll_col is None or name_col is None:
        raise UnreadableFile(
            "The first row must have the columns 'roll_no' and 'name' (found: "
            + ", ".join(h for h in header if h)
            + ")."
        )
    if len(raw_rows) - 1 > MAX_ROWS:
        raise UnreadableFile(f"More than {MAX_ROWS} rows; split the file by section.")
    parsed = ParsedRoster()
    first_seen: dict[str, int] = {}
    for number, row in enumerate(raw_rows[1:], start=2):
        roll = row[roll_col].strip() if roll_col < len(row) else ""
        name = row[name_col].strip() if name_col < len(row) else ""
        if not roll and not name:
            continue  # a blank line
        if not roll:
            parsed.errors.append(RowError(number, "The roll number is empty."))
        elif not name:
            parsed.errors.append(RowError(number, "The name is empty."))
        elif len(roll) > 60 or len(name) > 200:
            parsed.errors.append(RowError(number, "The roll number or name is too long."))
        elif roll in first_seen:
            parsed.errors.append(
                RowError(
                    number, f"Roll number {roll} appears again (first on row {first_seen[roll]})."
                )
            )
        else:
            first_seen[roll] = number
            parsed.rows.append(RosterRow(number, roll, name))
    return parsed
