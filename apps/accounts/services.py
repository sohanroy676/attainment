"""Accounts' public interface. Other modules call these functions, never the models.

`has_permission` is the one permission check in the system (design section 9): views,
services and templates all go through it.
"""

import uuid
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

from apps.audit import services as audit

from .models import Role, RoleAssignment, ScopeType, User
from .permissions import PERMISSIONS

ScopeResolver = Callable[[str, str], list[tuple[str, str]]]
_scope_resolvers: list[ScopeResolver] = []


def register_scope_resolver(resolver: ScopeResolver) -> None:
    """Let a module that knows the structure say which wider scopes contain a scope.

    `resolver(scope_type, scope_id)` returns (scope_type, scope_id) pairs that contain it, for
    example a section's offering, programme and department. academics registers one.
    """
    if resolver not in _scope_resolvers:
        _scope_resolvers.append(resolver)


def containing_scopes(scope_type: str, scope_id: uuid.UUID | str) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for resolver in _scope_resolvers:
        found.update(resolver(scope_type, str(scope_id)))
    return found


def _covers(
    assignment: RoleAssignment, scope_type: str | None, scope_id: uuid.UUID | str | None
) -> bool:
    """Does this assignment's scope include the requested scope?

    A college-wide assignment covers everything in the college. Otherwise the scope must match
    exactly, or contain the requested scope (a department head covers the department's
    programmes, offerings and sections) as reported by the registered resolvers.
    """
    if assignment.scope_type == ScopeType.COLLEGE:
        return True
    if scope_type is None or scope_id is None:
        return False
    held = (str(assignment.scope_type), str(assignment.scope_id))
    return held == (scope_type, str(scope_id)) or held in containing_scopes(scope_type, scope_id)


def has_permission(
    user: Any,
    permission: str,
    scope_type: str | None = None,
    scope_id: uuid.UUID | str | None = None,
) -> bool:
    """True if `user` holds a role granting `permission` over the requested scope.

    With no scope given, only a college-wide assignment can grant it.
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    for assignment in RoleAssignment.objects.filter(user_id=user.pk):
        if permission in PERMISSIONS.get(assignment.role, frozenset()) and _covers(
            assignment, scope_type, scope_id
        ):
            return True
    return False


def scoped_permission_required(
    permission: str, scope_type: str, scope_kwarg: str
) -> Callable[[Callable[..., HttpResponse]], Callable[..., HttpResponse]]:
    """View decorator: the URL keyword `scope_kwarg` names the scope being requested."""

    def decorator(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not has_permission(request.user, permission, scope_type, kwargs.get(scope_kwarg)):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def roles_of(user: Any) -> list[RoleAssignment]:
    return list(RoleAssignment.objects.filter(user_id=user.pk).order_by("role", "scope_type"))


def create_user(username: str, password: str, email: str = "", full_name: str = "") -> User:
    """Create a user in the current college, enforcing the password rules."""
    validate_password(password)
    return User.objects.create_user(username, password, email=email, full_name=full_name)


def _role_snapshot(assignment: RoleAssignment) -> dict[str, object]:
    return {
        "user_id": assignment.user_id,
        "role": assignment.role,
        "scope_type": assignment.scope_type,
        "scope_id": assignment.scope_id,
    }


def assign_role(
    user: User,
    role: Role,
    scope_type: ScopeType = ScopeType.COLLEGE,
    scope_id: uuid.UUID | None = None,
    actor: User | None = None,
    reason: str = "",
) -> RoleAssignment:
    """Give `user` a role over a scope. Logged; a repeat of an existing assignment is a no-op."""
    assignment, created = RoleAssignment.objects.get_or_create(
        user=user, role=role, scope_type=scope_type, scope_id=scope_id
    )
    if created:
        audit.record(
            "role.assigned",
            "role_assignment",
            entity_id=assignment.pk,
            actor_id=None if actor is None else actor.pk,
            after=_role_snapshot(assignment),
            reason=reason,
        )
    return assignment


def revoke_role(assignment: RoleAssignment, actor: User | None = None, reason: str = "") -> None:
    audit.record(
        "role.revoked",
        "role_assignment",
        entity_id=assignment.pk,
        actor_id=None if actor is None else actor.pk,
        before=_role_snapshot(assignment),
        reason=reason,
    )
    assignment.delete()
