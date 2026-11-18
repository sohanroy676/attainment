"""Import an earlier batch's PO values from an old workbook (.csv or .xlsx).

Layout: the first row is `Outcome`, then `Direct` and/or `Total`. Each following row is one
PO or PSO code and its value (0 to 10) in those columns; an empty cell is skipped. Everything is
checked before anything is saved, and the uploaded file is kept (design 8.13, F8).
"""

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academics.models import Batch
from apps.accounts.models import User
from apps.audit import services as audit
from apps.results import services as results
from apps.results.models import HistoricResult

from .models import ImportBatch
from .parsers import MAX_BYTES, MAX_ROWS, ZIP_MAGIC, UnreadableFile, _csv_rows, _xlsx_rows

COLUMNS = {"direct": HistoricResult.Kind.PO_DIRECT, "total": HistoricResult.Kind.PO_TOTAL}


@dataclass
class HistoricSheet:
    values: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def parse_historic(filename: str, content: bytes, batch: Batch) -> HistoricSheet:
    if len(content) > MAX_BYTES:
        raise UnreadableFile("The file is larger than 10 MB.")
    lowered = filename.lower()
    if lowered.endswith(".xlsx"):
        if not content.startswith(ZIP_MAGIC):
            raise UnreadableFile("This is not a real Excel (.xlsx) file.")
        rows = _xlsx_rows(content)
    elif lowered.endswith(".csv"):
        rows = _csv_rows(content)
    else:
        raise UnreadableFile("Please upload a .csv or .xlsx file.")
    if not rows:
        raise UnreadableFile("The file is empty.")
    if len(rows) > MAX_ROWS:
        raise UnreadableFile("The file has too many rows.")
    header = [h.strip().lower() for h in rows[0]]
    if not header or header[0] != "outcome":
        raise UnreadableFile("The first cell of the first row must be 'Outcome'.")
    wanted = {col: COLUMNS[name] for col, name in enumerate(header) if name in COLUMNS}
    if not wanted:
        raise UnreadableFile("The first row needs a 'Direct' or a 'Total' column.")
    known = {o.code for o in results.batch_outcomes(batch.programme)}
    sheet = HistoricSheet()
    seen: set[str] = set()
    for number, row in enumerate(rows[1:], start=2):
        code = row[0].strip() if row else ""
        if not code:
            continue
        if code not in known:
            sheet.problems.append(f"Row {number}: {code} is not an outcome of this programme.")
            continue
        if code in seen:
            sheet.problems.append(f"Row {number}: {code} appears again.")
            continue
        seen.add(code)
        for col, kind in wanted.items():
            raw = row[col].strip() if col < len(row) else ""
            if raw == "":
                continue
            try:
                value = Decimal(raw)
            except InvalidOperation:
                sheet.problems.append(f"Row {number}, {header[col]}: {raw!r} is not a number.")
                continue
            if not value.is_finite() or not 0 <= value <= 10:
                sheet.problems.append(f"Row {number}, {header[col]}: {raw} is outside 0 to 10.")
                continue
            sheet.values[(kind, code)] = value
    if not sheet.values and not sheet.problems:
        sheet.problems.append("The sheet has no values.")
    return sheet


def import_historic(
    batch: Batch, filename: str, content: bytes, actor: User | None = None
) -> ImportBatch:
    """Read the file and store its values for the batch. All or nothing; the file is kept."""
    sheet = parse_historic(filename, content, batch)
    if sheet.problems:
        raise ValidationError(sheet.problems)
    with transaction.atomic():
        record = ImportBatch.objects.create(
            kind=ImportBatch.Kind.HISTORIC,
            status=ImportBatch.Status.COMMITTED,
            filename=filename[:200],
            file_sha256=hashlib.sha256(content).hexdigest(),
            uploaded_by=actor,
            file_content=content,
            report={"values": len(sheet.values)},
        )
        results.store_historic(batch, sheet.values, record, actor)
        audit.record_model(
            "created", record, actor_id=None if actor is None else actor.pk,
            after={"status": record.status, "values": len(sheet.values)},
            reason=f"earlier values imported for batch {batch.name}",
        )  # fmt: skip
    return record
