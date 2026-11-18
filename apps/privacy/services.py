"""Privacy tools: one student's data export, the retention list, notices and anonymisation.

A student is on the retention list when every batch they belong to ended more than
`RETENTION_YEARS` ago. They are put on notice first; their identity is anonymised only after
`RETENTION_NOTICE_DAYS` have passed. Marks and enrolments stay (results must remain
reproducible); the name and every identifier value are replaced. The audit log never held
either, so its chain stays valid.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academics.models import Section
from apps.accounts.models import User
from apps.audit import services as audit
from apps.imports import services as imports
from apps.marks import services as marks
from apps.roster import services as roster
from apps.roster.models import Student

from .models import RetentionNotice


@dataclass
class RetentionRow:
    student: Student
    batches: list[str]
    eligible_since: int  # the year the retention period ended
    state: str  # "not notified", "waiting" or "ready"
    notified_on: date | None
    ready_on: date | None


def retention_years() -> int:
    return int(settings.RETENTION_YEARS)


def notice_days() -> int:
    return int(settings.RETENTION_NOTICE_DAYS)


def _eligible_since(student: Student) -> tuple[list[str], int] | None:
    """(batch names, year retention ended) from the latest batch end, or None with no batch."""
    batches = roster.student_batch_end_years(student)
    if not batches:
        return None  # no batch on record: never guessed at
    latest_end = max(year for _, year in batches)
    return sorted({name for name, _ in batches}), latest_end + retention_years()


def retention_list(today: date) -> list[RetentionRow]:
    """Students past the retention period who have not been anonymised, with where each stands."""
    notices = {n.student_id: n for n in RetentionNotice.objects.all()}
    rows = []
    for student in Student.objects.order_by("created_at"):
        notice = notices.get(student.pk)
        if notice is not None and notice.anonymised_on is not None:
            continue
        found = _eligible_since(student)
        if found is None or found[1] > today.year:
            continue
        names, since = found
        if notice is None:
            rows.append(RetentionRow(student, names, since, "not notified", None, None))
            continue
        ready_on = notice.notified_on + timedelta(days=notice_days())
        state = "ready" if ready_on <= today else "waiting"
        rows.append(RetentionRow(student, names, since, state, notice.notified_on, ready_on))
    return rows


def notify(today: date, actor: User | None = None) -> int:
    """Put every listed student who has no notice yet on notice today. Returns how many."""
    count = 0
    with transaction.atomic():
        for row in retention_list(today):
            if row.state != "not notified":
                continue
            notice = RetentionNotice.objects.create(
                student=row.student, notified_on=today, notified_by=actor
            )
            audit.record_model(
                "created", notice, actor_id=None if actor is None else actor.pk,
                after=audit.snapshot(notice),
            )  # fmt: skip
            count += 1
    return count


def anonymise_due(today: date, actor: User | None = None) -> int:
    """Anonymise the students whose notice period is over, and purge the stored upload files of
    sections whose batch is past retention. Returns the number of students anonymised."""
    count = 0
    with transaction.atomic():
        for row in retention_list(today):
            if row.state != "ready":
                continue
            roster.anonymise_identity(row.student, actor)
            notice = RetentionNotice.objects.get(student=row.student)
            notice.anonymised_on = today
            notice.save(update_fields=["anonymised_on", "updated_at"])
            audit.record_model(
                "updated", notice, actor_id=None if actor is None else actor.pk,
                after={"anonymised_on": today.isoformat()},
            )  # fmt: skip
            count += 1
        imports.purge_files(_sections_past_retention(today))
    return count


def _sections_past_retention(today: date) -> list[uuid.UUID]:
    return [
        s.pk
        for s in Section.objects.select_related("batch")
        if s.batch.end_year + retention_years() <= today.year
    ]


def is_anonymised(student: Student) -> bool:
    return RetentionNotice.objects.filter(student=student, anonymised_on__isnull=False).exists()


def student_export(student: Student, actor: User | None = None) -> dict[str, Any]:
    """Everything held about one student (a data-access request). Each export is audited."""
    if is_anonymised(student):
        raise ValidationError("This student's identity has been anonymised.")
    data = {
        **roster.student_record(student),
        "marks": marks.student_marks(student.pk),
        "note": "Calculated results are kept per section and course, not per student.",
    }
    audit.record(
        "student.exported", "roster.student", student.pk,
        actor_id=None if actor is None else actor.pk,
    )  # fmt: skip
    return data


def export_json(data: dict[str, Any]) -> bytes:
    return json.dumps(data, default=str, indent=2, sort_keys=True).encode("utf-8")
