"""Roster's public interface: students, identifiers, enrolments. Every change is audited."""

import uuid
from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, QuerySet

from apps.academics.models import Batch, CourseOffering, Section
from apps.accounts.models import User
from apps.audit import services as audit

from .models import BatchMembership, Enrolment, SectionMembership, Student, StudentIdentifier

Kind = StudentIdentifier.Kind


def _actor(actor: User | None) -> uuid.UUID | None:
    return None if actor is None else actor.pk


def _scope(section: Section | None, batch: Batch | None) -> dict[str, object]:
    if section is not None and batch is not None:
        raise ValidationError("An identifier has one scope: a section or a batch, not both.")
    return {"scope_section": section, "scope_batch": batch}


def create_student(name: str, actor: User | None = None) -> Student:
    """A new student. Roll numbers and memberships are added separately."""
    if not name.strip():
        raise ValidationError("A student needs a name.")
    student = Student.objects.create(name=name.strip())
    audit.record_model("created", student, actor_id=_actor(actor), after=audit.snapshot(student))
    return student


def find_by_identifier(
    value: str,
    kind: str = Kind.ROLL_NO,
    section: Section | None = None,
    batch: Batch | None = None,
) -> Student | None:
    """The student who currently holds `value` in the given scope, or None."""
    found = StudentIdentifier.objects.filter(
        kind=kind, value=value, valid_to__isnull=True, **_scope(section, batch)
    ).select_related("student")
    row = found.first()
    return None if row is None else row.student


def add_identifier(
    student: Student,
    value: str,
    kind: str = Kind.ROLL_NO,
    section: Section | None = None,
    batch: Batch | None = None,
    valid_from: date | None = None,
    actor: User | None = None,
) -> StudentIdentifier:
    """Give a student a label. The same current value cannot belong to two students in one scope."""
    value = value.strip()
    if not value:
        raise ValidationError("An identifier cannot be empty.")
    try:
        with transaction.atomic():
            identifier = StudentIdentifier.objects.create(
                student=student, kind=kind, value=value, valid_from=valid_from,
                **_scope(section, batch),
            )  # fmt: skip
    except IntegrityError as error:
        raise ValidationError(f"{kind} {value!r} is already in use in this scope.") from error
    audit.record_model(
        "created", identifier, actor_id=_actor(actor), after=audit.snapshot(identifier)
    )
    return identifier


def change_identifier(
    student: Student,
    kind: str,
    new_value: str,
    on: date,
    section: Section | None = None,
    batch: Batch | None = None,
    actor: User | None = None,
) -> StudentIdentifier:
    """A roll number changes: the old row is closed (history kept) and a new one opened."""
    current = StudentIdentifier.objects.filter(
        student=student, kind=kind, valid_to__isnull=True, **_scope(section, batch)
    ).first()
    with transaction.atomic():
        if current is not None:
            before = audit.snapshot(current)
            current.valid_to = on
            current.save(update_fields=["valid_to", "updated_at"])
            audit.record_model(
                "updated", current, actor_id=_actor(actor), before=before,
                after=audit.snapshot(current), reason="identifier changed",
            )  # fmt: skip
        return add_identifier(student, new_value, kind, section, batch, valid_from=on, actor=actor)


def identifier_history(student: Student, kind: str = Kind.ROLL_NO) -> QuerySet[StudentIdentifier]:
    return StudentIdentifier.objects.filter(student=student, kind=kind).order_by(
        F("valid_from").asc(nulls_first=True), "created_at"
    )


def join_batch(
    student: Student,
    batch: Batch,
    on: date | None = None,
    actor: User | None = None,
    reason: str = "",
) -> BatchMembership:
    membership = BatchMembership.objects.create(
        student=student, batch=batch, valid_from=on, reason=reason
    )
    audit.record_model(
        "created", membership, actor_id=_actor(actor), after=audit.snapshot(membership)
    )
    return membership


def enrol(
    student: Student,
    offering: CourseOffering,
    section: Section,
    on: date | None = None,
    actor: User | None = None,
) -> Enrolment:
    """Put a student on an offering in a section. Also opens their home-section membership."""
    if section.offering_id != offering.pk:
        raise ValidationError("The section belongs to a different offering.")
    enrolment, created = Enrolment.objects.get_or_create(
        student=student, offering=offering, defaults={"section": section, "date_from": on}
    )
    if not created:
        raise ValidationError("The student is already on this offering.")
    audit.record_model(
        "created", enrolment, actor_id=_actor(actor), after=audit.snapshot(enrolment)
    )
    membership = SectionMembership.objects.create(student=student, section=section, valid_from=on)
    audit.record_model(
        "created", membership, actor_id=_actor(actor), after=audit.snapshot(membership)
    )
    return enrolment


def move_section(
    enrolment: Enrolment,
    new_section: Section,
    on: date,
    actor: User | None = None,
    reason: str = "",
) -> Enrolment:
    """Change section. The enrolment now counts in the new section; the old membership is closed
    (not deleted), so the history shows both."""
    if new_section.offering_id != enrolment.offering_id:
        raise ValidationError("The new section belongs to a different offering.")
    if new_section.pk == enrolment.section_id:
        return enrolment
    with transaction.atomic():
        before = audit.snapshot(enrolment)
        for old in SectionMembership.objects.filter(
            student=enrolment.student, section_id=enrolment.section_id, valid_to__isnull=True
        ):
            old.valid_to = on
            old.save(update_fields=["valid_to", "updated_at"])
            audit.record_model(
                "updated", old, actor_id=_actor(actor), reason=reason or "section change"
            )
        enrolment.section = new_section
        enrolment.save(update_fields=["section", "updated_at"])
        audit.record_model(
            "updated", enrolment, actor_id=_actor(actor), before=before,
            after=audit.snapshot(enrolment), reason=reason or "section change",
        )  # fmt: skip
        membership = SectionMembership.objects.create(
            student=enrolment.student, section=new_section, valid_from=on, reason=reason
        )
        audit.record_model(
            "created", membership, actor_id=_actor(actor), after=audit.snapshot(membership)
        )
    return enrolment


def withdraw(
    enrolment: Enrolment, on: date, actor: User | None = None, reason: str = ""
) -> Enrolment:
    """Withdraw from the offering. The row and its history stay; the status changes."""
    before = audit.snapshot(enrolment)
    enrolment.status = Enrolment.Status.WITHDRAWN
    enrolment.date_to = on
    enrolment.save(update_fields=["status", "date_to", "updated_at"])
    audit.record_model(
        "updated", enrolment, actor_id=_actor(actor), before=before,
        after=audit.snapshot(enrolment), reason=reason or "withdrawn",
    )  # fmt: skip
    return enrolment


def enrolled_students(
    offering: CourseOffering, section: Section | None = None
) -> QuerySet[Student]:
    """Students currently enrolled (not withdrawn or exempted), optionally in one section.

    A student with no enrolment at all is simply absent here: 'not enrolled' is different from
    'enrolled with no mark', which is decided later by the marks module.
    """
    rows = Enrolment.objects.filter(offering=offering, status=Enrolment.Status.ENROLLED)
    if section is not None:
        rows = rows.filter(section=section)
    return Student.objects.filter(pk__in=rows.values("student_id"))


def current_identifier(
    student: Student, kind: str = Kind.ROLL_NO, section: Section | None = None
) -> str | None:
    rows = StudentIdentifier.objects.filter(student=student, kind=kind, valid_to__isnull=True)
    if section is not None:
        rows = rows.filter(scope_section=section) | rows.filter(scope_section__isnull=True)
    row = rows.order_by("-created_at").first()
    return None if row is None else row.value
