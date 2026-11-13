"""A6: scoped permissions, and isolation of the role table."""

import uuid

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory

from apps.accounts.models import Role, RoleAssignment, ScopeType
from apps.accounts.services import (
    assign_role,
    create_user,
    has_permission,
    revoke_role,
    roles_of,
    scoped_permission_required,
)
from apps.tenancy.services import college_context

from .helpers import make_college, make_user

pytestmark = [pytest.mark.integration]

SECTION_X, SECTION_Y = uuid.uuid4(), uuid.uuid4()


def test_a6_lecturer_assigned_to_section_x_is_denied_section_y(db: None) -> None:
    college = make_college("a")
    lecturer = make_user(college, "a.lecturer")
    with college_context(college.id):
        assign_role(lecturer, Role.LECTURER, ScopeType.SECTION, SECTION_X)
        assert has_permission(lecturer, "marks.enter_internal", ScopeType.SECTION, SECTION_X)
        assert not has_permission(lecturer, "marks.enter_internal", ScopeType.SECTION, SECTION_Y)
        assert not has_permission(lecturer, "marks.enter_internal", ScopeType.SECTION, None)
        assert not has_permission(lecturer, "marks.enter_internal")


def test_a6_view_decorator_denies_the_other_section(db: None) -> None:
    college = make_college("a")
    lecturer = make_user(college, "a.lecturer")

    @scoped_permission_required("marks.enter_internal", ScopeType.SECTION, "section_id")
    def view(request: object, section_id: uuid.UUID) -> str:
        return "ok"

    with college_context(college.id):
        assign_role(lecturer, Role.LECTURER, ScopeType.SECTION, SECTION_X)
        request = RequestFactory().get("/")
        request.user = lecturer
        assert view(request, section_id=SECTION_X) == "ok"
        with pytest.raises(PermissionDenied):
            view(request, section_id=SECTION_Y)


def test_role_only_grants_its_own_permissions(db: None) -> None:
    college = make_college("a")
    lecturer = make_user(college, "a.lecturer")
    with college_context(college.id):
        assign_role(lecturer, Role.LECTURER, ScopeType.SECTION, SECTION_X)
        assert not has_permission(lecturer, "marks.enter_see", ScopeType.SECTION, SECTION_X)
        assert not has_permission(lecturer, "method.activate", ScopeType.SECTION, SECTION_X)
        assert not has_permission(lecturer, "no.such.permission", ScopeType.SECTION, SECTION_X)


def test_college_wide_role_covers_every_scope_and_several_roles_combine(db: None) -> None:
    college = make_college("a")
    user = make_user(college, "a.multi")
    with college_context(college.id):
        assign_role(user, Role.AUDITOR)
        assign_role(user, Role.LECTURER, ScopeType.SECTION, SECTION_X)
        assert has_permission(user, "audit.view", ScopeType.SECTION, SECTION_Y)
        assert has_permission(user, "marks.enter_internal", ScopeType.SECTION, SECTION_X)
        assert len(roles_of(user)) == 2


def test_inactive_and_anonymous_users_have_no_permissions(db: None) -> None:
    college = make_college("a")
    user = make_user(college, "a.off", is_active=False)
    with college_context(college.id):
        assign_role(user, Role.COLLEGE_ADMIN)
        assert not has_permission(user, "users.manage")
        assert not has_permission(AnonymousUser(), "users.manage")


def test_revoking_a_role_removes_the_permission(db: None) -> None:
    college = make_college("a")
    user = make_user(college, "a.iqac")
    with college_context(college.id):
        assignment = assign_role(user, Role.IQAC)
        assert has_permission(user, "method.edit")
        revoke_role(assignment)
        assert not has_permission(user, "method.edit")


def test_scope_id_must_match_scope_type_in_the_database(db: None) -> None:
    college = make_college("a")
    user = make_user(college, "a.bad")
    with college_context(college.id):
        with pytest.raises(IntegrityError), transaction.atomic():
            RoleAssignment.objects.create(user=user, role=Role.LECTURER, scope_type="section")
        with pytest.raises(IntegrityError), transaction.atomic():
            RoleAssignment.objects.create(
                user=user, role=Role.LECTURER, scope_type="college", scope_id=SECTION_X
            )


def test_duplicate_assignment_is_not_created_twice(db: None) -> None:
    college = make_college("a")
    user = make_user(college, "a.dup")
    with college_context(college.id):
        assign_role(user, Role.IQAC)
        assign_role(user, Role.IQAC)
        assert RoleAssignment.objects.count() == 1


def test_create_user_enforces_the_password_rules(db: None) -> None:
    college = make_college("a")
    with college_context(college.id):
        with pytest.raises(ValidationError):
            create_user("a.short", "Abcdef1!x")
        assert create_user("a.long", "Abcdef1!xy").username == "a.long"


def test_roles_are_isolated_between_colleges(db: None) -> None:
    a, b = make_college("a"), make_college("b")
    user_a, user_b = make_user(a, "a.admin"), make_user(b, "b.admin")
    with college_context(a.id):
        assign_role(user_a, Role.COLLEGE_ADMIN)
    with college_context(b.id):
        assign_role(user_b, Role.COLLEGE_ADMIN)
    with college_context(a.id):
        assert RoleAssignment.objects.count() == 1
        assert not has_permission(
            user_b, "users.manage"
        )  # the other college's admin has nothing here
    with college_context(None):
        assert RoleAssignment.objects.count() == 0
