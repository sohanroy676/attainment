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

from .models import Role, RoleAssignment, ScopeType, User
from .permissions import PERMISSIONS


def _covers(
    assignment: RoleAssignment, scope_type: str | None, scope_id: uuid.UUID | str | None
) -> bool:
    """Does this assignment's scope include the requested scope?

    A college-wide assignment covers everything in the college. Otherwise the scope must match
    exactly. Containment between department, programme, offering and section (a department
    head covering its sections) is added with the academic structure in v0.4.0.
    """
    if assignment.scope_type == ScopeType.COLLEGE:
        return True
    if scope_type is None or scope_id is None:
        return False
    return assignment.scope_type == scope_type and str(assignment.scope_id) == str(scope_id)


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


def assign_role(
    user: User,
    role: Role,
    scope_type: ScopeType = ScopeType.COLLEGE,
    scope_id: uuid.UUID | None = None,
) -> RoleAssignment:
    assignment, _ = RoleAssignment.objects.get_or_create(
        user=user, role=role, scope_type=scope_type, scope_id=scope_id
    )
    return assignment


def revoke_role(assignment: RoleAssignment) -> None:
    assignment.delete()
