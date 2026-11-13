"""Methodology's public interface: method versions, assignment with inheritance, templates."""

import hashlib
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academics.models import CourseOffering, University
from apps.accounts.models import User
from apps.audit import services as audit
from engine.errors import MethodConfigError
from engine.schema import MethodConfig, load_method

from .models import Method, MethodAssignment, MethodVersion

TEMPLATE_DIR = Path(__file__).resolve().parent / "method_templates"
TEMPLATES = {"vasavi_theory": "Vasavi OBE (theory)", "vasavi_lab": "Vasavi OBE (lab)"}
MAX_CONFIG_BYTES = 200_000
Scope = MethodAssignment.Scope


def _actor(actor: User | None) -> uuid.UUID | None:
    return None if actor is None else actor.pk


def parse_config(text: str) -> MethodConfig:
    """Validate with the engine's schema. The error names each field and the problem."""
    if len(text.encode()) > MAX_CONFIG_BYTES:
        raise ValidationError("The method is too large.")
    try:
        return load_method(text)
    except MethodConfigError as error:
        raise ValidationError(str(error).split("; ")) from error


def config_hash(text: str) -> str:
    """SHA-256 of the canonical form of the configuration (sorted keys, exact decimals)."""
    canonical = json.dumps(
        json.loads(text, parse_float=Decimal), sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def create_method(name: str, kind: str = Method.Kind.THEORY, actor: User | None = None) -> Method:
    method = Method.objects.create(name=name.strip(), kind=kind)
    audit.record_model("created", method, actor_id=_actor(actor), after=audit.snapshot(method))
    return method


def create_draft(method: Method, config_text: str, actor: User | None = None) -> MethodVersion:
    """A new draft version. The configuration must already be valid."""
    parse_config(config_text)
    latest = method.versions.order_by("-number").first()
    version = MethodVersion.objects.create(
        method=method, number=1 if latest is None else latest.number + 1, config_text=config_text
    )
    audit.record_model("created", version, actor_id=_actor(actor), after=audit.snapshot(version))
    return version


def create_from_template(
    key: str, name: str | None = None, actor: User | None = None
) -> MethodVersion:
    """A new method with a first draft taken from a platform template (theory or lab)."""
    if key not in TEMPLATES:
        raise ValidationError(f"Unknown template {key!r}.")
    text = (TEMPLATE_DIR / f"{key}.json").read_text(encoding="utf-8")
    kind = Method.Kind.LAB if key.endswith("lab") else Method.Kind.THEORY
    method = create_method(name or TEMPLATES[key], kind=kind, actor=actor)
    return create_draft(method, text, actor=actor)


def update_draft(
    version: MethodVersion, config_text: str, actor: User | None = None
) -> MethodVersion:
    """Edit a draft. Active and retired versions cannot be edited: make a new draft instead."""
    if version.status != MethodVersion.Status.DRAFT:
        raise ValidationError(
            f"Version {version.number} is {version.status} and cannot be edited. "
            "Create a new draft from it instead."
        )
    parse_config(config_text)
    before = audit.snapshot(version)
    version.config_text = config_text
    version.save(update_fields=["config_text", "updated_at"])
    audit.record_model(
        "updated", version, actor_id=_actor(actor), before=before, after=audit.snapshot(version)
    )
    return version


def new_draft_from(version: MethodVersion, actor: User | None = None) -> MethodVersion:
    return create_draft(version.method, version.config_text, actor=actor)


def activate(
    version: MethodVersion, effective_from: date, actor: User | None = None
) -> MethodVersion:
    """Publish a draft: fix its hash, make it immutable, and retire the version it replaces."""
    if version.status != MethodVersion.Status.DRAFT:
        raise ValidationError("Only a draft can be activated.")
    parse_config(version.config_text)
    with transaction.atomic():
        current = version.method.versions.filter(status=MethodVersion.Status.ACTIVE).first()
        if current is not None:
            if current.effective_from is not None and effective_from <= current.effective_from:
                raise ValidationError(
                    f"The new version must start after {current.effective_from} "
                    f"(when version {current.number} began)."
                )
            before = audit.snapshot(current)
            current.status = MethodVersion.Status.RETIRED
            current.effective_to = effective_from - timedelta(days=1)
            current.save(update_fields=["status", "effective_to", "updated_at"])
            audit.record_model(
                "updated", current, actor_id=_actor(actor), before=before,
                after=audit.snapshot(current), reason="replaced by a newer version",
            )  # fmt: skip
        before = audit.snapshot(version)
        version.status = MethodVersion.Status.ACTIVE
        version.effective_from = effective_from
        version.content_hash = config_hash(version.config_text)
        version.approved_by = actor
        version.save(
            update_fields=["status", "effective_from", "content_hash", "approved_by", "updated_at"]
        )
        audit.record_model(
            "updated", version, actor_id=_actor(actor), before=before,
            after=audit.snapshot(version), reason="method version activated",
        )  # fmt: skip
    return version


def version_in_force(method: Method, on: date) -> MethodVersion | None:
    """The version that applied on a date: an earlier term keeps its version, a later one gets
    the newer."""
    candidates = [
        v
        for v in method.versions.exclude(status=MethodVersion.Status.DRAFT)
        if v.effective_from is not None
        and v.effective_from <= on
        and (v.effective_to is None or on <= v.effective_to)
    ]
    return max(candidates, key=lambda v: v.effective_from, default=None)  # type: ignore[arg-type,return-value]


# assignment with inheritance and locks ---------------------
def _applies(assignment: MethodAssignment, on: date) -> bool:
    return (assignment.valid_from is None or assignment.valid_from <= on) and (
        assignment.valid_to is None or on <= assignment.valid_to
    )


def _wider_scopes(scope_type: str) -> list[str]:
    order = [Scope.UNIVERSITY, Scope.COLLEGE, Scope.PROGRAMME, Scope.COURSE]
    return [str(s) for s in order[: order.index(scope_type)]]  # type: ignore[arg-type]


def assign_method(
    scope_type: str,
    method: Method,
    scope_id: uuid.UUID | None = None,
    valid_from: date | None = None,
    valid_to: date | None = None,
    locked: bool = False,
    actor: User | None = None,
) -> MethodAssignment:
    """Choose a method for a level. Refused where a wider level has locked its choice."""
    for wider in MethodAssignment.objects.filter(
        scope_type__in=_wider_scopes(scope_type), locked=True
    ):
        if _overlaps(wider, valid_from, valid_to):
            raise ValidationError(
                f"The {wider.scope_type} level has locked its method ({wider.method}); "
                f"a {scope_type} cannot choose another."
            )
    assignment = MethodAssignment.objects.create(
        scope_type=scope_type, scope_id=scope_id, method=method,
        valid_from=valid_from, valid_to=valid_to, locked=locked,
    )  # fmt: skip
    audit.record_model(
        "created", assignment, actor_id=_actor(actor), after=audit.snapshot(assignment)
    )
    return assignment


def _overlaps(assignment: MethodAssignment, start: date | None, end: date | None) -> bool:
    a_start, a_end = assignment.valid_from, assignment.valid_to
    return (a_end is None or start is None or start <= a_end) and (
        end is None or a_start is None or a_start <= end
    )


def method_for_offering(
    offering: CourseOffering, on: date | None = None, programme_id: uuid.UUID | None = None
) -> tuple[MethodVersion, MethodAssignment] | None:
    """The method version that applies to an offering on a date (default: its term's start).

    Levels, most general first: university, college, programme, course. A more specific level
    replaces a wider one, except that a locked wider level always wins.
    """
    on = on or offering.term.academic_year.start_date
    if programme_id is None:
        section = offering.sections.order_by("name").first()
        programme_id = None if section is None else section.programme_id
    university = University.objects.first()
    wanted = [
        (Scope.UNIVERSITY, None if university is None else university.pk),
        (Scope.COLLEGE, None),
        (Scope.PROGRAMME, programme_id),
        (Scope.COURSE, offering.course_id),
    ]
    chosen: MethodAssignment | None = None
    for scope_type, scope_id in wanted:
        if scope_type != Scope.COLLEGE and scope_id is None:
            continue
        found = [
            a
            for a in MethodAssignment.objects.filter(scope_type=scope_type, scope_id=scope_id)
            if _applies(a, on)
        ]
        if not found:
            continue
        candidate = max(found, key=lambda a: a.valid_from or date.min)
        chosen = candidate
        if candidate.locked:
            break  # a locked level cannot be overridden by anything more specific
    if chosen is None:
        return None
    version = version_in_force(chosen.method, on)
    return None if version is None else (version, chosen)
