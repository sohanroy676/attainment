"""Make an anonymised copy of a roster or marks file, so it can be committed or demoed.

    python manage.py anonymise_roster real.csv anonymised.csv

Roll numbers and names are replaced by S001, S002... in file order; every other column is kept.
The same real value always gets the same label inside one run, so marks files and roster files
converted with `--keep-map` stay consistent. The map itself is real data: it is written only when
asked for, next to the input, and never to the output.
"""

import csv
import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

ROLL_COLUMNS = {"roll_no", "roll no", "roll number", "rollno", "roll", "roll_number"}
NAME_COLUMNS = {"name", "student name", "student_name", "student"}


class Command(BaseCommand):
    help = "Replace roll numbers and names in a CSV file with S001, S002, ..."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("source")
        parser.add_argument("target")
        parser.add_argument("--keep-map", action="store_true", help="write <source>.map.json")

    def handle(self, *args: Any, **options: Any) -> None:
        source, target = Path(options["source"]), Path(options["target"])
        if source.resolve() == target.resolve():
            raise CommandError("The output must be a different file.")
        with source.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        if not rows:
            raise CommandError("The file is empty.")
        header = [h.strip().lower() for h in rows[0]]
        roll = next((i for i, h in enumerate(header) if h in ROLL_COLUMNS), None)
        name = next((i for i, h in enumerate(header) if h in NAME_COLUMNS), None)
        if roll is None:
            raise CommandError("There is no roll number column.")
        labels: dict[str, str] = {}
        out = [rows[0]]
        for row in rows[1:]:
            row = list(row)
            if len(row) <= roll or not row[roll].strip():
                out.append(row)
                continue
            label = labels.setdefault(row[roll].strip(), f"S{len(labels) + 1:03d}")
            row[roll] = label
            if name is not None and len(row) > name:
                row[name] = f"Student {label[1:]}"
            out.append(row)
        with target.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle, lineterminator="\n").writerows(out)
        if options["keep_map"]:
            source.with_suffix(".map.json").write_text(json.dumps(labels), encoding="utf-8")
        self.stdout.write(f"{len(labels)} students anonymised into {target}")
