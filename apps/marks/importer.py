"""Pre-filled sheets, marks import and SEE script mapping, all with preview and confirm.

Nothing is saved at preview. Any error rejects the whole file, so a bad row can never leave
the marks half loaded. The uploaded file is kept on the import batch.
"""

import hashlib
import io
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import openpyxl
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.academics.models import Section
from apps.accounts.models import User
from apps.accounts.services import has_permission
from apps.assessments.models import Assessment
from apps.audit import services as audit
from apps.imports.models import ImportBatch
from apps.imports.parsers import MAX_BYTES, UnreadableFile, _csv_rows, _xlsx_rows
from apps.roster.models import Enrolment, Student, StudentIdentifier

from . import services
from .models import MarkCell, ScriptMapping

TEMPLATE_MARKER = "attainment-marks-template"


@dataclass
class Plan:
    cells: list[list[Any]] = field(default_factory=list)  # [enrolment id, part code, state, value]
    errors: list[tuple[int, str]] = field(default_factory=list)
    warnings: list[tuple[int, str]] = field(default_factory=list)
    changed: int = 0
    rows: int = 0


def _current_rolls(section: Section) -> dict[str, Enrolment]:
    """roll number -> the enrolment of a student currently enrolled in the section."""
    enrolments = {
        e.student_id: e
        for e in Enrolment.objects.filter(
            section=section, status=Enrolment.Status.ENROLLED
        ).select_related("student")
    }
    rolls: dict[str, Enrolment] = {}
    identifiers = StudentIdentifier.objects.filter(
        student_id__in=list(enrolments), kind="roll_no", valid_to__isnull=True
    )
    for identifier in identifiers:
        rolls[identifier.value] = enrolments[identifier.student_id]
    return rolls


# the pre-filled sheet --------------------------------------
def build_template(assessment: Assessment, section: Section) -> bytes:
    """An Excel sheet with the roll numbers and part codes filled in, and any marks already
    entered. A second sheet lists the paper; a third identifies the assessment and section."""
    parts = list(assessment.parts.select_related("co"))
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Marks"
    sheet.append(["roll_no", *[p.code for p in parts]])
    rolls = _current_rolls(section)
    for roll in sorted(rolls, key=lambda r: (len(r), r)):
        enrolment = rolls[roll]
        row = services.get_row(enrolment, assessment)
        stored = {} if row is None else {c.part_id: c for c in row.cells.all()}
        line: list[Any] = [roll]
        for part in parts:
            cell = stored.get(part.pk)
            text = services.cell_text(cell)
            line.append(
                float(cell.value) if cell is not None and cell.value is not None else text or None
            )
        sheet.append(line)
    paper = book.create_sheet("Paper")
    paper.append(["part", "max", "co"])
    for p in parts:
        paper.append([p.code, float(p.max), "" if p.co is None else p.co.code])
    meta = book.create_sheet("meta")
    for line in (TEMPLATE_MARKER, str(assessment.pk), str(section.pk)):
        meta.append([line])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _check_meta(content: bytes, assessment: Assessment, section: Section | None) -> None:
    try:
        book = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as error:  # noqa: BLE001 - already vetted by the row reader
        raise UnreadableFile("The Excel file could not be opened.") from error
    if "meta" not in book.sheetnames:
        return
    values = [r[0] for r in book["meta"].iter_rows(values_only=True)]
    book.close()
    if values[:1] != [TEMPLATE_MARKER] or str(assessment.pk) != str(values[1]):
        raise UnreadableFile("This sheet was made for a different assessment.")
    if section is not None and str(section.pk) != str(values[2]):
        raise UnreadableFile("This sheet was made for a different section.")


# reading ---------------------------------------------------
def _read_rows(filename: str, content: bytes) -> list[list[str]]:
    if len(content) > MAX_BYTES:
        raise UnreadableFile("The file is larger than 10 MB.")
    lowered = filename.lower()
    if lowered.endswith(".xlsx"):
        if not content.startswith(b"PK\x03\x04"):
            raise UnreadableFile("This is not a real Excel (.xlsx) file.")
        return _xlsx_rows(content)
    if lowered.endswith(".csv"):
        return _csv_rows(content)
    raise UnreadableFile("Please upload a .csv or .xlsx file.")


def _plan(assessment: Assessment, rows: list[list[str]], key_name: str, resolve: Any) -> Plan:
    """Check every row against the paper. `resolve(key)` returns an enrolment or an error text."""
    if not rows:
        raise UnreadableFile("The file is empty.")
    header = [h.strip() for h in rows[0]]
    if not header or header[0].lower() != key_name:
        raise UnreadableFile(f"The first column must be '{key_name}'.")
    parts = {p.code: p for p in assessment.parts.select_related("question__choice_group")}
    unknown = [h for h in header[1:] if h and h not in parts]
    if unknown:
        raise UnreadableFile(
            "These columns are not parts of this paper: "
            + ", ".join(unknown)
            + ". Is this the right sheet?"
        )
    plan = Plan()
    seen: dict[str, int] = {}
    existing: dict[tuple[Any, str], MarkCell] = {
        (c.row.enrolment_id, c.part.code): c
        for c in MarkCell.objects.filter(row__assessment=assessment).select_related("row", "part")
    }
    for number, row in enumerate(rows[1:], start=2):
        key = row[0].strip() if row else ""
        if not key and not any(c.strip() for c in row):
            continue
        if not key:
            plan.errors.append((number, f"The {key_name} is empty."))
            continue
        if key in seen:
            plan.errors.append((number, f"{key} appears again (first on row {seen[key]})."))
            continue
        seen[key] = number
        target = resolve(key)
        if isinstance(target, str):
            plan.errors.append((number, target))
            continue
        plan.rows += 1
        answered: dict[str, set[str]] = {}
        for col, code in enumerate(header[1:], start=1):
            if not code:
                continue
            text = row[col] if col < len(row) else ""
            try:
                state, value = services.parse_mark_text(text, parts[code].max)
            except ValidationError as error:
                plan.errors.append((number, f"{code}: {error.messages[0]}"))
                continue
            plan.cells.append([str(target.pk), code, state, None if value is None else str(value)])
            old = existing.get((target.pk, code))
            if (
                old is None
                and state != "blank"
                or old is not None
                and (old.state != state or old.value != value)
            ):
                plan.changed += 1
            group = parts[code].question.choice_group
            if state == "value" and group is not None:
                answered.setdefault(group.code, set()).add(parts[code].question.number)
        for group in assessment.groups.all():
            extra = len(answered.get(group.code, set())) - group.best_n
            if extra > 0:
                plan.warnings.append(
                    (number, f"{key} answered {extra} more than the best {group.best_n}; "
                     "the extra answers will be set aside by the best-N rule.")
                )  # fmt: skip
    return plan


def _store(
    kind: str, assessment: Assessment, section: Section | None, filename: str, content: bytes,
    plan: Plan, actor: User | None,
) -> ImportBatch:  # fmt: skip
    batch = ImportBatch.objects.create(
        kind=kind,
        status=ImportBatch.Status.REJECTED if plan.errors else ImportBatch.Status.PREVIEWED,
        filename=filename[:200],
        file_sha256=hashlib.sha256(content).hexdigest(),
        file_content=content,
        uploaded_by=actor,
        section=section,
        assessment=assessment,
        payload={"cells": plan.cells},
        report={
            "rows": plan.rows,
            "cells": len(plan.cells),
            "changed": plan.changed,
            "errors": len(plan.errors),
            "error_rows": [list(e) for e in sorted(plan.errors)],
            "warnings": [list(w) for w in sorted(plan.warnings)],
        },
    )
    audit.record_model(
        "created", batch, actor_id=None if actor is None else actor.pk,
        after={"kind": kind, "status": batch.status, "rows": plan.rows, "errors": len(plan.errors)},
    )  # fmt: skip
    return batch


def preview_marks(
    assessment: Assessment, section: Section, filename: str, content: bytes, actor: User
) -> ImportBatch:
    """Preview a marks sheet keyed by roll number for one section."""
    if not services.can_write(actor, assessment, section):
        raise PermissionDenied("You may not enter these marks.")
    rows = _read_rows(filename, content)
    if filename.lower().endswith(".xlsx"):
        _check_meta(content, assessment, section)
    rolls = _current_rolls(section)

    def resolve(roll: str) -> Enrolment | str:
        return rolls.get(roll) or f"Roll number {roll} is not on this section's roster."

    plan = _plan(assessment, rows, "roll_no", resolve)
    return _store(ImportBatch.Kind.MARKS, assessment, section, filename, content, plan, actor)


def commit_marks(batch: ImportBatch, actor: User) -> ImportBatch:
    """Apply a previewed marks file. All or nothing."""
    if batch.status != ImportBatch.Status.PREVIEWED:
        raise ValidationError(f"This import is {batch.status} and cannot be confirmed.")
    assessment = batch.assessment
    parts = {p.code: p for p in assessment.parts.all()}
    enrolments = {str(e.pk): e for e in Enrolment.objects.filter(offering=assessment.offering)}
    with transaction.atomic():
        for enrolment_id, code, state, value in batch.payload["cells"]:
            row = services.get_row(enrolments[enrolment_id], assessment, create=True)
            assert row is not None  # noqa: S101 - created just above
            if state == "blank" and not row.cells.filter(part=parts[code]).exists():
                continue  # an empty cell on a blank stays untouched: no cell, no history
            services.save_cell(
                row, parts[code], state, None if value is None else Decimal(value),
                actor, source="import", import_batch=batch.pk, reason="marks import",
            )  # fmt: skip
        batch.status = ImportBatch.Status.COMMITTED
        batch.save(update_fields=["status", "updated_at"])
        audit.record_model(
            "updated", batch, actor_id=actor.pk,
            after={"status": "committed", "cells": len(batch.payload["cells"])},
            reason="marks import confirmed",
        )  # fmt: skip
    return batch


# SEE: script mapping and marks by script number ------------
def preview_scripts(
    assessment: Assessment, filename: str, content: bytes, actor: User
) -> ImportBatch:
    """Preview a script mapping (columns script_no, roll_no and, where roll numbers repeat
    across sections, a third column `section`) for the whole offering."""
    if not has_permission(actor, "marks.enter_see"):
        raise PermissionDenied("Only the exam branch maps SEE scripts.")
    rows = _read_rows(filename, content)
    if not rows or [h.strip().lower() for h in rows[0][:2]] != ["script_no", "roll_no"]:
        raise UnreadableFile("The first two columns must be 'script_no' and 'roll_no'.")
    has_section = len(rows[0]) > 2 and rows[0][2].strip().lower() == "section"
    offering_rolls: dict[str, list[tuple[Student, str]]] = {}
    enrolments = Enrolment.objects.filter(
        offering=assessment.offering, status=Enrolment.Status.ENROLLED
    )
    by_student = {e.student_id: e for e in enrolments.select_related("student", "section")}
    for identifier in StudentIdentifier.objects.filter(
        student_id__in=list(by_student), kind="roll_no", valid_to__isnull=True
    ):
        enrolment = by_student[identifier.student_id]
        offering_rolls.setdefault(identifier.value, []).append(
            (enrolment.student, enrolment.section.name)
        )
    mapped_scripts = {m.script_no: m.student_id for m in assessment.scripts.all()}
    mapped_students = {m.student_id: m.script_no for m in assessment.scripts.all()}
    errors: list[tuple[int, str]] = []
    pairs: list[list[str]] = []
    seen_scripts: dict[str, int] = {}
    seen_students: dict[Any, int] = {}
    for number, row in enumerate(rows[1:], start=2):
        script, roll = (row[0].strip() if row else ""), (row[1].strip() if len(row) > 1 else "")
        if not script and not roll:
            continue
        section_name = row[2].strip() if has_section and len(row) > 2 else None
        candidates = [
            s for s, name in offering_rolls.get(roll, []) if section_name in (None, "", name)
        ]
        students = candidates
        student = students[0] if len(students) == 1 else None
        if not script or not roll:
            errors.append((number, "Both the script number and the roll number are needed."))
        elif student is None:
            if students:
                message = (
                    f"Roll number {roll} is in more than one section; "
                    "add a 'section' column to say which."
                )
            else:
                message = f"Roll number {roll} is not on this course's roster."
            errors.append((number, message))
        elif script in seen_scripts:
            first = seen_scripts[script]
            errors.append((number, f"Script {script} appears again (first on row {first})."))
        elif student.pk in seen_students:
            first = seen_students[student.pk]
            errors.append((number, f"Roll number {roll} already has a script on row {first}."))
        elif mapped_scripts.get(script, student.pk) != student.pk:
            errors.append((number, f"Script {script} is already mapped to another student."))
        elif mapped_students.get(student.pk, script) != script:
            errors.append((number, f"Roll number {roll} already has another script."))
        else:
            seen_scripts[script], seen_students[student.pk] = number, number
            pairs.append([script, str(student.pk)])
    plan = Plan(errors=errors, rows=len(pairs))
    batch = _store(ImportBatch.Kind.SCRIPTS, assessment, None, filename, content, plan, actor)
    batch.payload = {"pairs": pairs}
    batch.save(update_fields=["payload", "updated_at"])
    return batch


def commit_scripts(batch: ImportBatch, actor: User) -> ImportBatch:
    if batch.status != ImportBatch.Status.PREVIEWED:
        raise ValidationError(f"This import is {batch.status} and cannot be confirmed.")
    with transaction.atomic():
        for script, student_id in batch.payload["pairs"]:
            mapping, created = ScriptMapping.objects.get_or_create(
                assessment=batch.assessment, script_no=script,
                defaults={"student_id": student_id, "imported_by": actor},
            )  # fmt: skip
            if created:
                audit.record_model(
                    "created", mapping, actor_id=actor.pk, after=audit.snapshot(mapping)
                )
        batch.status = ImportBatch.Status.COMMITTED
        batch.save(update_fields=["status", "updated_at"])
    return batch


def preview_see_marks(
    assessment: Assessment, filename: str, content: bytes, actor: User
) -> ImportBatch:
    """Preview SEE marks keyed by script number; scripts are joined to students by the mapping."""
    if not has_permission(actor, "marks.enter_see"):
        raise PermissionDenied("Only the exam branch enters SEE marks.")
    rows = _read_rows(filename, content)
    scripts = {m.script_no: m.student_id for m in assessment.scripts.all()}
    enrolments = {
        e.student_id: e
        for e in Enrolment.objects.filter(
            offering=assessment.offering, status=Enrolment.Status.ENROLLED
        )
    }

    def resolve(script: str) -> Enrolment | str:
        student_id = scripts.get(script)
        if student_id is None:
            return f"Script {script} is not mapped to a student."
        return enrolments.get(student_id) or f"The student of script {script} is not enrolled."

    plan = _plan(assessment, rows, "script_no", resolve)
    return _store(ImportBatch.Kind.MARKS, assessment, None, filename, content, plan, actor)
