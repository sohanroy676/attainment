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
