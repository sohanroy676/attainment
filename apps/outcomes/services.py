"""Outcomes' public interface: definitions, COs, the CO-PO grid, targets."""

import uuid
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academics.models import Batch, Course, CourseOffering, Programme
from apps.accounts.models import User
from apps.audit import services as audit

from .models import (
    COPOMap,
    CourseDefinitionVersion,
    CourseOutcome,
    ProgrammeOutcome,
    Target,
)

ALLOWED_STRENGTHS = (0, 1, 2, 3)


def _actor(actor: User | None) -> uuid.UUID | None:
    return None if actor is None else actor.pk


def create_programme_outcomes(
    programme: Programme, outcomes: Sequence[tuple[str, str, str]], actor: User | None = None
) -> list[ProgrammeOutcome]:
    """Create (kind, code, text) outcomes for a programme at version 1."""
    created = []
    for kind, code, text in outcomes:
        outcome = ProgrammeOutcome.objects.create(
            programme=programme, kind=kind, code=code.strip(), text=text
        )
        audit.record_model(
            "created", outcome, actor_id=_actor(actor), after=audit.snapshot(outcome)
        )
        created.append(outcome)
    return created


def create_definition(
    course: Course, outcomes: Sequence[tuple[str, str]], valid_from: date | None = None,
    actor: User | None = None,
) -> CourseDefinitionVersion:  # fmt: skip
    """The next definition version of a course, with its COs (any number, four is fine)."""
    codes = [code.strip() for code, _ in outcomes]
    if len(set(codes)) != len(codes) or not all(codes):
        raise ValidationError("Course outcome codes must be filled in and different.")
    latest = course.definitions.order_by("-version").first()
    with transaction.atomic():
        definition = CourseDefinitionVersion.objects.create(
            course=course,
            version=1 if latest is None else latest.version + 1,
            valid_from=valid_from,
        )
        audit.record_model(
            "created", definition, actor_id=_actor(actor), after=audit.snapshot(definition)
        )
        for order, (code, text) in enumerate(outcomes, start=1):
            co = CourseOutcome.objects.create(
                definition=definition, code=code.strip(), text=text, order=order
            )
            audit.record_model("created", co, actor_id=_actor(actor), after=audit.snapshot(co))
    return definition


def mapping_grid(
    definition: CourseDefinitionVersion, programme: Programme
) -> dict[str, dict[str, int]]:
    """CO code -> outcome code -> strength. A missing key means not mapped (blank)."""
    grid: dict[str, dict[str, int]] = {co.code: {} for co in definition.outcomes.all()}
    rows = COPOMap.objects.filter(co__definition=definition, outcome__programme=programme)
    for row in rows.select_related("co", "outcome"):
        grid[row.co.code][row.outcome.code] = row.strength
    return grid


def engine_mapping(
    definition: CourseDefinitionVersion, programme: Programme
) -> dict[str, dict[str, Decimal]]:
    """The mapping in the form the engine takes. Blank is absent; 0 is an explicit 0."""
    return {
        co: {po: Decimal(s) for po, s in row.items()}
        for co, row in mapping_grid(definition, programme).items()
    }


def save_mapping_grid(
    definition: CourseDefinitionVersion,
    programme: Programme,
    grid: Mapping[str, Mapping[str, int | None]],
    actor: User | None = None,
) -> int:
    """Save the whole grid or none of it. `None` means blank; 0 to 3 are the only values.

    Returns the number of cells changed. Errors name the cell, for example "CO2 / PO3: 5 ...".
    """
    cos = {co.code: co for co in definition.outcomes.all()}
    outcomes = {o.code: o for o in ProgrammeOutcome.objects.filter(programme=programme)}
    problems = []
    for co_code, row in grid.items():
        if co_code not in cos:
            problems.append(f"{co_code}: not a course outcome of this definition.")
            continue
        for po_code, strength in row.items():
            if po_code not in outcomes:
                problems.append(f"{co_code} / {po_code}: not an outcome of this programme.")
            elif strength is not None and (
                isinstance(strength, bool) or strength not in ALLOWED_STRENGTHS
            ):
                problems.append(
                    f"{co_code} / {po_code}: {strength!r} is not allowed (use blank, 0, 1, 2 or 3)."
                )
    if problems:
        raise ValidationError(problems)
    changed = 0
    with transaction.atomic():
        for co_code, row in grid.items():
            for po_code, strength in row.items():
                existing = COPOMap.objects.filter(
                    co=cos[co_code], outcome=outcomes[po_code]
                ).first()
                if strength is None:
                    if existing is not None:
                        before = audit.snapshot(existing)
                        existing.delete()
                        audit.record_model(
                            "deleted", existing, actor_id=_actor(actor), before=before
                        )
                        changed += 1
                elif existing is None:
                    created = COPOMap.objects.create(
                        co=cos[co_code], outcome=outcomes[po_code], strength=strength
                    )
                    audit.record_model(
                        "created", created, actor_id=_actor(actor), after=audit.snapshot(created)
                    )
                    changed += 1
                elif existing.strength != strength:
                    before = audit.snapshot(existing)
                    existing.strength = strength
                    existing.save(update_fields=["strength", "updated_at"])
                    audit.record_model(
                        "updated", existing, actor_id=_actor(actor), before=before,
                        after=audit.snapshot(existing),
                    )  # fmt: skip
                    changed += 1
    return changed


def set_target(
    value: Decimal | str,
    offering: CourseOffering | None = None,
    outcome: ProgrammeOutcome | None = None,
    batch: Batch | None = None,
    actor: User | None = None,
    source: str = Target.Source.SET,
    rule_used: str = "",
) -> Target:
    """Store a target for a course offering, or for a programme outcome of a batch."""
    if (offering is None) == (outcome is None) or (outcome is None) != (batch is None):
        raise ValidationError(
            "A target is for an offering, or for an outcome together with a batch."
        )
    value = Decimal(value)
    if not 0 <= value <= 10:
        raise ValidationError("A target must be between 0 and 10.")
    lookup = (
        {"offering": offering} if offering is not None else {"outcome": outcome, "batch": batch}
    )
    with transaction.atomic():
        existing = Target.objects.filter(**lookup).first()
        before = None if existing is None else audit.snapshot(existing)
        target, _ = Target.objects.update_or_create(
            defaults={"value": value, "source": source, "rule_used": rule_used}, **lookup
        )
        audit.record_model(
            "created" if existing is None else "updated", target, actor_id=_actor(actor),
            before=before, after=audit.snapshot(target),
        )  # fmt: skip
    return target
