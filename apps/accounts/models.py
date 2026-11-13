from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone

from apps.tenancy.managers import TenantManager
from apps.tenancy.models import TenantModel


class TenantUserManager(TenantManager, BaseUserManager[Any]):
    """The normal user manager: only the current college's users."""

    def create_user(self, username: str, password: str | None = None, **fields: Any) -> Any:
        user = self.model(username=username, **fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


class AuthLookupManager(BaseUserManager[Any]):
    """Unfiltered in Python, but the database still limits it (see accounts migration 0001).

    Used only before anybody is logged in (login, password reset), after
    tenancy.services.set_auth_identity made exactly one user row visible.
    """


class User(TenantModel, AbstractBaseUser):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(blank=True)
    full_name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = []

    objects = TenantUserManager()
    auth_lookup = AuthLookupManager()

    def __str__(self) -> str:
        return self.username

    # Django admin (the setup screens) asks these questions; the answers come from the one
    # permission service, so the admin never grants more than the roles do.
    ADMIN_PERMISSION = {  # noqa: RUF012
        "academics": "structure.manage",
        "roster": "roster.manage",
        "imports": "roster.manage",
        "outcomes": "outcomes.edit",
        "assessments": "paper.edit",
        "methodology": "method.edit",
    }

    def _may_administer(self, app_label: str | None) -> bool:
        from .services import has_permission

        if not self.is_active:
            return False
        wanted = (
            [self.ADMIN_PERMISSION[app_label]]
            if app_label in self.ADMIN_PERMISSION
            else []
            if app_label
            else sorted(set(self.ADMIN_PERMISSION.values()))
        )
        return any(has_permission(self, permission) for permission in wanted)

    @property
    def is_staff(self) -> bool:
        return self._may_administer(None)

    def has_perm(self, perm: str, obj: object = None) -> bool:
        return self._may_administer(perm.split(".")[0])

    def has_module_perms(self, app_label: str) -> bool:
        return self._may_administer(app_label)


class Role(models.TextChoices):
    COLLEGE_ADMIN = "college_admin", "College admin"
    IQAC = "iqac", "IQAC"
    HOD = "hod", "Head of department"
    COORDINATOR = "coordinator", "Course coordinator"
    LECTURER = "lecturer", "Lecturer"
    EXAM_BRANCH = "exam_branch", "Exam branch"
    PRINCIPAL = "principal", "Principal"
    AUDITOR = "auditor", "Auditor"


class ScopeType(models.TextChoices):
    COLLEGE = "college", "College"
    DEPARTMENT = "department", "Department"
    PROGRAMME = "programme", "Programme"
    OFFERING = "offering", "Course offering"
    SECTION = "section", "Section"


class RoleAssignment(TenantModel):
    """A role held by a user over one scope. A user may hold several (design section 9).

    scope_id points at a department, programme, offering or section. Those tables arrive in
    later versions, so it is a plain id here; it is empty exactly when the scope is the college.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.CharField(max_length=20, choices=Role.choices)
    scope_type = models.CharField(
        max_length=20, choices=ScopeType.choices, default=ScopeType.COLLEGE
    )
    scope_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(scope_type="college", scope_id__isnull=True)
                    | (~models.Q(scope_type="college") & models.Q(scope_id__isnull=False))
                ),
                name="role_scope_id_matches_scope_type",
            ),
            models.UniqueConstraint(
                fields=["user", "role", "scope_type", "scope_id"],
                nulls_distinct=False,
                name="role_assignment_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.role} @ {self.scope_type}"
