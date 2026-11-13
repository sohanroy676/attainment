"""Marks' public interface: save cells safely, read history, hand marks to the engine."""

import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.academics.models import Section
from apps.accounts.models import User
from apps.accounts.services import has_permission
from apps.assessments.models import Assessment, QuestionPart
from apps.audit import services as audit
from apps.roster.models import Enrolment
from engine.model import AssessmentInput, Cell, Part

from .models import MarkCell, MarkChange, MarkSheetRow

State = MarkCell.State

# What a person types in the grid or a sheet. "-" means a choice question that was not attempted.
STATE_CODES = {
    "": State.BLANK,
    "-": State.NOT_ATTEMPTED,
    "AB": State.ABSENT,
    "A": State.ABSENT,
    "WH": State.WITHHELD,
    "EX": State.EXEMPTED,
    "NA": State.NOT_APPLICABLE,
}
STATE_TEXT = {
    State.BLANK: "",
    State.NOT_ATTEMPTED: "-",
    State.ABSENT: "AB",
    State.WITHHELD: "WH",
    State.EXEMPTED: "EX",
    State.NOT_APPLICABLE: "NA",
}
LOCKED = (Assessment.Status.APPROVED, Assessment.Status.LOCKED)


class StaleCell(ValidationError):
    """Someone else changed the cell after it was loaded."""


def parse_mark_text(text: str, part_max: Decimal | None = None) -> tuple[str, Decimal | None]:
    """Turn typed text into (state, value). Raises ValidationError with a plain message."""
    raw = text.strip()
    code = raw.upper()
    if code in STATE_CODES:
        return STATE_CODES[code].value, None
    try:
        value = Decimal(raw.replace(",", "."))
    except InvalidOperation as error:
        raise ValidationError(
            f"'{raw}' is not a mark. Use a number, or AB, WH, EX, NA or - for a state."
        ) from error
    if not value.is_finite():
        raise ValidationError(f"'{raw}' is not a mark.")
    if value < 0:
        raise ValidationError(f"{raw} is below 0.")
    if part_max is not None and value > part_max:
        raise ValidationError(f"{raw} is above the maximum {part_max.normalize():f}.")
    if value != value.quantize(Decimal("0.01")):
        raise ValidationError(f"{raw} has more than two decimal places.")
    return State.VALUE.value, value


def cell_text(cell: MarkCell | None) -> str:
    """How a cell is shown and written back to a sheet."""
    if cell is None:
        return ""
    if cell.state == State.VALUE:
        return f"{cell.value.normalize():f}" if cell.value is not None else ""
    return STATE_TEXT.get(State(cell.state), "")


# permissions -----------------------------------------------
def write_permission(assessment: Assessment) -> str:
    return "marks.enter_see" if assessment.tool == "SEE" else "marks.enter_internal"


def can_write(user: User, assessment: Assessment, section: Section) -> bool:
    return has_permission(user, write_permission(assessment), "section", section.pk)


def can_read(user: User, assessment: Assessment, section: Section) -> bool:
    """Writers can read; so can anyone with the reports view right over the section (a lecturer
    for their own section, the auditor read-only). The exam branch reads only the SEE."""
    return can_write(user, assessment, section) or has_permission(
        user, "reports.view", "section", section.pk
    )


# rows and cells --------------------------------------------
def get_row(
    enrolment: Enrolment, assessment: Assessment, attempt: str = "regular", create: bool = False
) -> MarkSheetRow | None:
    row = MarkSheetRow.objects.filter(
        enrolment=enrolment, assessment=assessment, attempt=attempt
    ).first()
    if row is None and create:
        row = MarkSheetRow.objects.create(
            enrolment=enrolment, assessment=assessment, attempt=attempt
        )
    return row


def save_cell(
    row: MarkSheetRow,
    part: QuestionPart,
    state: str,
    value: Decimal | None,
    actor: User,
    expected_version: int | None = None,
    reason: str = "",
    source: str = "manual",
    import_batch: uuid.UUID | None = None,
) -> MarkCell:
    """Write one cell. Checks the right, the value, the lock and the version; writes history.

    `expected_version` is the version the person saw (0 for "no value yet"). If the cell has
    moved on, the save is refused with a message naming who changed it. Returns the cell.
    """
    assessment, section = row.assessment, row.enrolment.section
    if not can_write(actor, assessment, section):
        raise PermissionDenied("You may not enter these marks.")
    if part.assessment_id != row.assessment_id:
        raise ValidationError("That part is not on this assessment.")
    if assessment.status in LOCKED:
        raise ValidationError("These marks are locked.")
    if state not in State.values:
        raise ValidationError(f"Unknown mark state {state!r}.")
    if (state == State.VALUE) != (value is not None):
        raise ValidationError("A mark needs a value; a state such as absent has none.")
    if value is not None and not (0 <= value <= part.max):
        raise ValidationError(f"{value} is outside 0 to {part.max.normalize():f}.")
    if row.status == MarkSheetRow.Status.SUBMITTED and not reason.strip():
        raise ValidationError("These marks were submitted: a reason is required for a change.")
    with transaction.atomic():
        cell = (
            MarkCell.objects.select_related("entered_by")
            .select_for_update(of=("self",))
            .filter(row=row, part=part)
            .first()
        )
        if expected_version is not None:
            seen = 0 if cell is None else cell.row_version
            if seen != expected_version:
                who = (
                    "someone"
                    if cell is None or cell.entered_by is None
                    else cell.entered_by.username
                )
                raise StaleCell(f"This mark was changed by {who}. Reload and try again.")
        if cell is not None and cell.state == state and cell.value == value:
            return cell  # nothing changed: no new version, no history
        now = timezone.now()
        old_state, old_value = ("", None) if cell is None else (cell.state, cell.value)
        if cell is None:
            cell = MarkCell(row=row, part=part)
        else:
            cell.row_version += 1
        cell.state, cell.value = state, value
        cell.entered_by, cell.entered_at = actor, now
        cell.source, cell.import_batch = source, import_batch
        cell.save()
        MarkChange.objects.create(
            cell_id_value=cell.pk, row_id_value=row.pk, part_code=part.code,
            old_state=old_state, old_value=old_value, new_state=state, new_value=value,
            by=actor, at=now, reason=reason.strip(), import_batch=import_batch,
        )  # fmt: skip
        if row.status == MarkSheetRow.Status.NOT_STARTED:
            row.status = MarkSheetRow.Status.ENTERED
            row.save(update_fields=["status", "updated_at"])
    return cell


def submit_row(row: MarkSheetRow, actor: User) -> MarkSheetRow:
    if not can_write(actor, row.assessment, row.enrolment.section):
        raise PermissionDenied("You may not submit these marks.")
    if row.status == MarkSheetRow.Status.NOT_STARTED:
        raise ValidationError("Nothing has been entered for this student.")
    before = audit.snapshot(row)
    row.status = MarkSheetRow.Status.SUBMITTED
    row.save(update_fields=["status", "updated_at"])
    audit.record_model(
        "updated", row, actor_id=actor.pk, before=before, after=audit.snapshot(row),
        reason="marks submitted",
    )  # fmt: skip
    return row


def set_rows_status(
    assessment: Assessment, section: Section, status: str, actor: User, reason: str = ""
) -> int:
    """Move every started mark row of a section to `status` (submitted, or back to entered).

    Used by the workflow when a lecturer submits or a coordinator returns a section's marks.
    Returns the number of rows changed. Rows nobody has started stay as they are.
    """
    if status not in (MarkSheetRow.Status.SUBMITTED, MarkSheetRow.Status.ENTERED):
        raise ValidationError("Rows can only be submitted or returned to entered.")
    if assessment.status in LOCKED:
        raise ValidationError("These marks are locked.")
    rows = list(
        MarkSheetRow.objects.filter(assessment=assessment, enrolment__section=section)
        .exclude(status__in=[MarkSheetRow.Status.NOT_STARTED, status])
    )  # fmt: skip
    for row in rows:
        before = audit.snapshot(row)
        row.status = status
        row.save(update_fields=["status", "updated_at"])
        audit.record_model(
            "updated", row, actor_id=actor.pk, before=before, after=audit.snapshot(row),
            reason=reason or f"marks {status}",
        )  # fmt: skip
    return len(rows)


def started_rows(assessment: Assessment, section: Section) -> int:
    """How many students of the section have any marks started for this assessment."""
    return (
        MarkSheetRow.objects.filter(assessment=assessment, enrolment__section=section)
        .exclude(status=MarkSheetRow.Status.NOT_STARTED)
        .count()
    )


def history(cell: MarkCell) -> QuerySet[MarkChange]:
    return MarkChange.objects.filter(cell_id_value=cell.pk).order_by("at", "created_at")


# the engine's view -----------------------------------------
DEFAULT_STATE_MAP = {
    State.VALUE: "entered",
    State.ABSENT: "absent",
    State.BLANK: "blank",
    State.NOT_ATTEMPTED: "blank",
    State.WITHHELD: "blank",
    State.EXEMPTED: "blank",
    State.NOT_APPLICABLE: "blank",
}


def engine_assessment(
    assessment: Assessment,
    sections: list[Section] | None = None,
    state_map: dict[str, str] | None = None,
    attempt: str = "regular",
) -> AssessmentInput:
    """The stored marks as engine input. Students are the enrolled ones who have a mark row; a
    student whose every cell is absent is absent for the whole assessment. `state_map` says how
    each stored state is treated (entered, absent or blank); the default is in DEFAULT_STATE_MAP.
    """
    mapping = {**{str(k): v for k, v in DEFAULT_STATE_MAP.items()}, **(state_map or {})}
    parts = list(assessment.parts.select_related("question__choice_group", "co"))
    engine_parts = tuple(
        Part(
            id=p.code,
            question=p.question.number,
            max=p.max,
            co=None if p.co is None else p.co.code,
            choice_group=None if p.question.choice_group is None else p.question.choice_group.code,
        )
        for p in parts
    )
    rows = MarkSheetRow.objects.filter(
        assessment=assessment, attempt=attempt, enrolment__status=Enrolment.Status.ENROLLED
    ).select_related("enrolment")
    if sections is not None:
        rows = rows.filter(enrolment__section__in=sections)
    marks: dict[str, dict[str, Cell]] = {}
    absent_whole: set[str] = set()
    for row in rows:
        stored = {c.part.code: c for c in row.cells.select_related("part")}
        cells = {}
        for part in parts:
            cell = stored.get(part.code)
            kind = "blank" if cell is None else mapping[cell.state]
            if kind == "entered" and cell is not None and cell.value is not None:
                cells[part.code] = Cell.entered(cell.value)
            elif kind == "absent":
                cells[part.code] = Cell.absent()
            else:
                cells[part.code] = Cell.blank()
        student = str(row.enrolment.student_id)
        marks[student] = cells
        if cells and all(c.state.value == "absent" for c in cells.values()):
            absent_whole.add(student)
    return AssessmentInput(assessment.tool, engine_parts, marks, frozenset(absent_whole))


def student_ids(assessment: Assessment, sections: list[Section] | None = None) -> list[str]:
    """Internal ids of the students with a mark row (for the course's enrolled list)."""
    return sorted(engine_assessment(assessment, sections).marks)
