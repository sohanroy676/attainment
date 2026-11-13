"""Turn the Deep Learning course workbook into the anonymised golden fixture DS-A.

Run this yourself, on your machine. The workbook stays in the gitignored `data/private/`;
only the anonymised JSON it writes may be committed. Nothing here is sent anywhere.

    uv run python scripts/build_ds_a.py data/private/<workbook>.xlsx

Output: engine/tests/golden/ds_a/course.json
- roll numbers become s001, s002, ... in sheet order (no names are read at all)
- marks, maxima, CO tags and choice questions are copied as they are
- the sheet layout is the one used by docs/prototype/run.py (Vasavi Deep Learning, CSE-AIML)

Review the printed summary and the JSON before committing it.
"""

import json
import re
import sys
from decimal import Decimal
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

OUT = (
    Path(__file__).resolve().parent.parent / "engine" / "tests" / "golden" / "ds_a" / "course.json"
)


def columns(first: str, last: str) -> list[str]:
    return [
        get_column_letter(i)
        for i in range(column_index_from_string(first), column_index_from_string(last) + 1)
    ]


def number(value: object) -> str | None:
    """A cell as exact decimal text, so nothing passes through a float."""
    if value is None or value == "":
        return None
    return str(Decimal(str(value)))


def question_sheet(  # type: ignore[no-untyped-def]
    ws, max_row, co_row, rows, cols, question_of, choice_from
):
    parts = []
    for col in cols:
        maximum = ws[f"{col}{max_row}"].value
        co = ws[f"{col}{co_row}"].value
        if maximum is None:
            continue
        question = question_of(col)
        parts.append(
            {
                "id": col,
                "question": str(question),
                "max": str(Decimal(str(maximum))),
                "co": "CO" + re.sub(r"\D", "", str(co)),
                "choice_group": "G" if choice_from(question) else None,
            }
        )
    marks = {}
    for row in rows:
        roll = ws[f"B{row}"].value
        if roll is None:
            continue
        marks[str(roll)] = {p["id"]: number(ws[f"{p['id']}{row}"].value) for p in parts}
    return parts, marks


def main(path: str) -> None:
    wb = openpyxl.load_workbook(path, data_only=True)
    i1_parts, i1 = question_sheet(
        wb["DL-CSE-AIML--VI-Sem-I-internal"], 4, 6, range(8, 75), columns("C", "P"),
        lambda c: c, lambda q: False,
    )  # fmt: skip
    pair = {c: i // 2 + 1 for i, c in enumerate(columns("C", "N"))}  # two columns per question
    i2_parts, i2 = question_sheet(
        wb["DL-CSE-AIML-VI-Sem-II-internal"], 4, 6, range(8, 75), columns("C", "N"),
        lambda c: pair[c], lambda q: True,
    )  # fmt: skip
    see_ws = wb["SEE"]
    see_question = {
        c: int(re.match(r"(\d+)", str(see_ws[f"{c}6"].value)).group(1)) for c in columns("C", "AA")
    }
    see_parts, see = question_sheet(
        see_ws, 4, 3, range(7, 73), columns("C", "AA"),
        lambda c: see_question[c], lambda q: q >= 11,
    )  # fmt: skip
    qa = wb["DL Quiz-Assignment"]
    quiz, assign = {}, {}
    for row in range(6, 73):
        roll = qa[f"B{row}"].value
        if roll is None:
            continue
        quiz[str(roll)] = {f"q{k + 1}": number(qa[f"{c}{row}"].value) for k, c in enumerate("CDE")}
        assign[str(roll)] = {
            f"a{k + 1}": number(qa[f"{c}{row}"].value) for k, c in enumerate("GHI")
        }

    # anonymise: one id per roll number, in the order of the Internal-I sheet, then any others
    ids: dict[str, str] = {}
    for roll in [*i1, *i2, *see, *quiz, *assign]:
        ids.setdefault(roll, f"s{len(ids) + 1:03d}")

    def rekey(marks: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
        return {ids[roll]: row for roll, row in marks.items()}

    def items(prefix: str) -> list[dict[str, object]]:
        return [{"id": f"{prefix}{k}", "question": str(k), "max": "5"} for k in (1, 2, 3)]

    course = {
        "cos": ["CO1", "CO2", "CO3", "CO4", "CO5"],
        "students": sorted(ids[r] for r in i1),
        "target": "2.2",
        "indirect": {f"CO{k}": "3" for k in range(1, 6)},
        "assessments": {
            "INT1": {"parts": i1_parts, "marks": rekey(i1)},
            "INT2": {"parts": i2_parts, "marks": rekey(i2)},
            "SEE": {"parts": see_parts, "marks": rekey(see)},
            "QUIZ": {"parts": items("q"), "marks": rekey(quiz)},
            "ASSIGN": {"parts": items("a"), "marks": rekey(assign)},
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(course, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {OUT}")
    print(
        f"students {len(course['students'])}; parts INT1 {len(i1_parts)}, INT2 {len(i2_parts)}, "
        f"SEE {len(see_parts)}; SEE rows {len(see)}; quiz rows {len(quiz)}"
    )
    print(
        "Expected: 14, 12 and 25 parts; 67 students; 66 SEE rows. Check names and rolls are gone."
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
