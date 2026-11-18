"""Turn the CSE 2021-25 batch workbook into the golden fixture DS-B.

Run this yourself. The workbook stays in the gitignored `data/private/`; only the JSON it writes
may be committed. It reads course names and the per-course PO/PSO values and the targets only: no
student data and no faculty names are read.

    uv run python scripts/build_ds_b.py data/private/<batch workbook>.xlsx

Output: engine/tests/golden/ds_b/batch.json
Layout (from docs/prototype/batch2.py): sheet "CSE_PO_Attainment", header row 7, course rows 8 to
127 (course name in column C), PO and PSO columns recognised by their header, targets in row 131.
Course category (core / non-core) and attained status are not in these columns, so they are left
empty; the counts in R3 are checked by synthetic tests instead.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent.parent / "engine" / "tests" / "golden" / "ds_b" / "batch.json"
SHEET = "CSE_PO_Attainment"


def number(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        return None
    return str(Decimal(str(value)))


def main(path: str) -> None:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[SHEET]
    header = [cell.value for cell in ws[7]]
    po_columns = {str(h): i for i, h in enumerate(header) if h and str(h).startswith(("PO", "PSO"))}
    courses = []
    for row in range(8, 128):
        cells = [c.value for c in ws[row]]
        name = cells[2]
        if name is None or name == "Course Name":
            continue
        values = {po: number(cells[i]) for po, i in po_columns.items()}
        courses.append(
            {"id": f"c{len(courses) + 1:03d}", "name": str(name), "category": "", "po": values}
        )
    targets = {po: number(ws.cell(131, i + 1).value) for po, i in po_columns.items()}
    batch = {
        "outcomes": list(po_columns),
        "targets": targets,
        "indirect": dict.fromkeys(po_columns, "3"),  # entered as 3 in the college's file
        "courses": courses,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(batch, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT}: {len(courses)} course rows, {len(po_columns)} outcomes")
    print("Expected: 15 outcomes. Check that no person's name appears in the file.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
