"""Roster import: upload, preview, confirm. Nothing changes until the confirm step succeeds.

Preview reconciles the file with the current roster of one section:
  new        roll number not known in the scope: a student will be created and enrolled
  unchanged  already enrolled in this section with the same name
  renamed    already enrolled, but the name in the file differs
  enrol      the student exists in the scope but is not on this offering yet
  missing    enrolled now, absent from the file (left alone unless the person ticks withdraw)
  errors     malformed or duplicate rows, or a roll number held by someone enrolled in another
             section of the same offering. Any error rejects the whole file.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academics.models import Section
from apps.accounts.models import User
from apps.audit import services as audit
from apps.roster import services as roster
from apps.roster.models import Enrolment, Student, StudentIdentifier

from .models import ImportBatch
from .parsers import RosterRow, RowError, UnreadableFile, parse_roster

SCOPES = ("section", "batch", "college")


@dataclass
class RosterPlan:
    new: list[RosterRow] = field(default_factory=list)
    unchanged: list[RosterRow] = field(default_factory=list)
    renamed: list[tuple[Student, RosterRow]] = field(default_factory=list)
    enrol: list[tuple[Student, RosterRow]] = field(default_factory=list)
    missing: list[Student] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "new": len(self.new),
            "unchanged": len(self.unchanged),
            "renamed": len(self.renamed),
            "enrol": len(self.enrol),
            "missing": len(self.missing),
            "errors": len(self.errors),
        }


def _scope_args(section: Section, scope: str) -> dict[str, Any]:
    if scope == "section":
        return {"section": section}
    if scope == "batch":
        return {"batch": section.batch}
    if scope == "college":
        return {}
    raise ValidationError(f"Unknown roll-number scope {scope!r}.")


def plan_roster(section: Section, rows: list[RosterRow], scope: str) -> RosterPlan:
    """Compare the file's rows with what the system holds. Reads only."""
    plan = RosterPlan()
    scope_args = _scope_args(section, scope)
    seen: set[uuid.UUID] = set()
    for row in rows:
        student = roster.find_by_identifier(row.roll_no, **scope_args)
        if student is None:
            plan.new.append(row)
            continue
        seen.add(student.pk)
        enrolment = Enrolment.objects.filter(student=student, offering=section.offering).first()
        if enrolment is not None and enrolment.section_id != section.pk:
            plan.errors.append(
                RowError(row.row, f"Roll number {row.roll_no} is enrolled in another section.")
            )
        elif enrolment is None or enrolment.status != Enrolment.Status.ENROLLED:
            plan.enrol.append((student, row))
        elif student.name != row.name:
            plan.renamed.append((student, row))
        else:
            plan.unchanged.append(row)
    in_section = roster.enrolled_students(section.offering, section)
    plan.missing = [s for s in in_section if s.pk not in seen]
    return plan


def _plan_fingerprint(plan: RosterPlan) -> str:
    """Identifies the plan so confirm can tell if the roster moved since the preview."""
    parts = [
        ["new", [r.row for r in plan.new]],
        ["unchanged", [r.row for r in plan.unchanged]],
        ["renamed", [(str(s.pk), r.row) for s, r in plan.renamed]],
        ["enrol", [(str(s.pk), r.row) for s, r in plan.enrol]],
        ["missing", sorted(str(s.pk) for s in plan.missing)],
    ]
    return hashlib.sha256(repr(parts).encode()).hexdigest()


def preview_roster(
    section: Section,
    filename: str,
    content: bytes,
    scope: str = "section",
    actor: User | None = None,
) -> ImportBatch:
    """Read the file, reconcile it, and store the result. The roster itself is not touched.

    Raises UnreadableFile when the file cannot be read at all (nothing is stored).
    """
    parsed = parse_roster(filename, content)
    plan = plan_roster(section, parsed.rows, scope)
    errors = parsed.errors + plan.errors
    errors.sort(key=lambda e: e.row)
    batch = ImportBatch.objects.create(
        status=ImportBatch.Status.REJECTED if errors else ImportBatch.Status.PREVIEWED,
        filename=filename[:200],
        file_sha256=hashlib.sha256(content).hexdigest(),
        uploaded_by=actor,
        section=section,
        scope=scope,
        payload={"rows": [[r.row, r.roll_no, r.name] for r in parsed.rows]},
        report={
            **plan.counts(),
            "errors": len(errors),
            "error_rows": [[e.row, e.message] for e in errors],
            "fingerprint": _plan_fingerprint(plan),
        },
    )
    audit.record_model(
        "created",
        batch,
        actor_id=None if actor is None else actor.pk,
        after={
            "status": batch.status,
            **{k: v for k, v in batch.report.items() if k != "error_rows"},
        },
    )
    return batch


def rows_of(batch: ImportBatch) -> list[RosterRow]:
    return [RosterRow(r[0], r[1], r[2]) for r in batch.payload["rows"]]


def commit_roster(
    batch: ImportBatch,
    actor: User | None = None,
    withdraw_missing: bool = False,
    on: date | None = None,
) -> ImportBatch:
    """Apply a previewed file. All or nothing: any failure undoes every change."""
    if batch.status != ImportBatch.Status.PREVIEWED:
        raise ValidationError(f"This import is {batch.status} and cannot be confirmed.")
    section = batch.section
    with transaction.atomic():
        plan = plan_roster(section, rows_of(batch), batch.scope)
        if plan.errors or _plan_fingerprint(plan) != batch.report["fingerprint"]:
            raise ValidationError("The roster changed since the preview. Please upload again.")
        scope_args = _scope_args(section, batch.scope)
        for row in plan.new:
            student = roster.create_student(row.name, actor=actor)
            roster.add_identifier(student, row.roll_no, valid_from=on, actor=actor, **scope_args)
            roster.join_batch(student, section.batch, on=on, actor=actor)
            roster.enrol(student, section.offering, section, on=on, actor=actor)
        for student, row in plan.renamed:
            roster.rename_student(student, row.name, actor=actor)
        for student, row in plan.enrol:
            roster.rename_student(student, row.name, actor=actor)
            _enrol_again(student, section, on, actor)
        withdrawn = 0
        if withdraw_missing:
            for student in plan.missing:
                enrolment = Enrolment.objects.get(student=student, offering=section.offering)
                roster.withdraw(
                    enrolment, on=on or date.today(), actor=actor, reason="not in roster file"
                )
                withdrawn += 1
        batch.status = ImportBatch.Status.COMMITTED
        batch.save(update_fields=["status", "updated_at"])
        audit.record_model(
            "updated",
            batch,
            actor_id=None if actor is None else actor.pk,
            after={"status": "committed", "withdrawn": withdrawn, **plan.counts()},
            reason="roster import confirmed",
        )
    return batch


def _enrol_again(student: Student, section: Section, on: date | None, actor: User | None) -> None:
    """Enrol a known student; a withdrawn enrolment on this offering is reactivated."""
    existing = Enrolment.objects.filter(student=student, offering=section.offering).first()
    if existing is None:
        roster.enrol(student, section.offering, section, on=on, actor=actor)
        return
    before = audit.snapshot(existing)
    existing.status = Enrolment.Status.ENROLLED
    existing.date_to = None
    existing.save(update_fields=["status", "date_to", "updated_at"])
    audit.record_model(
        "updated", existing, actor_id=None if actor is None else actor.pk, before=before,
        after=audit.snapshot(existing), reason="re-enrolled by roster import",
    )  # fmt: skip


def reject_roster(batch: ImportBatch, actor: User | None = None) -> ImportBatch:
    """Discard a previewed file. The roster stays as it was."""
    if batch.status == ImportBatch.Status.COMMITTED:
        raise ValidationError("A committed import cannot be rejected.")
    batch.status = ImportBatch.Status.REJECTED
    batch.save(update_fields=["status", "updated_at"])
    return batch


__all__ = [
    "SCOPES",
    "RosterPlan",
    "StudentIdentifier",
    "UnreadableFile",
    "commit_roster",
    "plan_roster",
    "preview_roster",
    "reject_roster",
    "rows_of",
]
