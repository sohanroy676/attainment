"""Academics' public interface: structure rules, faculty assignment, who may see which section."""

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet

from apps.accounts import services as accounts
from apps.accounts.models import Role, RoleAssignment, ScopeType, User
from apps.audit import services as audit

from .models import CourseOffering, FacultyAssignment, Section


def containing_scopes(scope_type: str, scope_id: str) -> list[tuple[str, str]]:
    """The wider scopes that contain a section, offering or programme (for role checks)."""
    try:
        key = uuid.UUID(scope_id)
    except ValueError:
        return []
    found: list[tuple[str, str]] = []
    if scope_type == "section":
        section = Section.objects.select_related("programme").filter(pk=key).first()
        if section is not None:
            found += [
                ("offering", str(section.offering_id)),
                ("programme", str(section.programme_id)),
                ("department", str(section.programme.department_id)),
            ]
    elif scope_type == "offering":
        for section in Section.objects.select_related("programme").filter(offering_id=key):
            found += [
                ("programme", str(section.programme_id)),
                ("department", str(section.programme.department_id)),
            ]
    elif scope_type == "programme":
        from .models import Programme

        programme = Programme.objects.filter(pk=key).first()
        if programme is not None:
            found.append(("department", str(programme.department_id)))
    return found


def check_section(section: Section) -> None:
    """A section's batch must belong to the section's programme."""
    if section.batch.programme_id != section.programme_id:
        raise ValidationError("The batch does not belong to the section's programme.")


def assign_faculty(
    user: User,
    offering: CourseOffering,
    section: Section | None = None,
    actor: User | None = None,
) -> FacultyAssignment:
    """Let a lecturer teach an offering (all sections) or one section.

    Also gives the user the lecturer role over that scope, so the permission service and the
    visible-sections query agree. Both steps are logged.
    """
    if section is not None and section.offering_id != offering.pk:
        raise ValidationError("The section belongs to a different offering.")
    assignment, created = FacultyAssignment.objects.get_or_create(
        user=user, offering=offering, section=section
    )
    if created:
        audit.record_model(
            "created", assignment, actor_id=None if actor is None else actor.pk,
            after=audit.snapshot(assignment),
        )  # fmt: skip
    scope, scope_id = (
        (ScopeType.OFFERING, offering.pk) if section is None else (ScopeType.SECTION, section.pk)
    )
    accounts.assign_role(
        user, Role.LECTURER, scope, scope_id, actor=actor, reason="faculty assignment"
    )
    return assignment


def sections_visible_to(user: Any) -> QuerySet[Section]:
    """Sections the user may see: all for a college-wide role, otherwise those their scoped roles
    cover (a section, an offering, a programme or a department)."""
    assignments = list(RoleAssignment.objects.filter(user_id=user.pk))
    if not user.is_active:
        return Section.objects.none()
    if any(a.scope_type == ScopeType.COLLEGE for a in assignments):
        return Section.objects.all()
    condition = Q(pk__in=[])
    for a in assignments:
        if a.scope_type == ScopeType.SECTION:
            condition |= Q(pk=a.scope_id)
        elif a.scope_type == ScopeType.OFFERING:
            condition |= Q(offering_id=a.scope_id)
        elif a.scope_type == ScopeType.PROGRAMME:
            condition |= Q(programme_id=a.scope_id)
        elif a.scope_type == ScopeType.DEPARTMENT:
            condition |= Q(programme__department_id=a.scope_id)
    return Section.objects.filter(condition)
