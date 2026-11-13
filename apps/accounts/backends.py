from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest

from apps.tenancy.services import set_auth_identity, set_current_college


class TenantAuthBackend(ModelBackend):
    """Finds the user by username before any college is known, then pins the college.

    Row-level security hides every user row except the one named in the pre-login setting,
    so this lookup cannot see other users. Passwords are checked here; lockout is handled by
    django-axes, which runs before this backend.
    """

    def authenticate(  # type: ignore[override]
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> Any:
        if not username or password is None:
            return None
        user_model = get_user_model()
        set_auth_identity(login=username)
        try:
            user = user_model.auth_lookup.get(username=username)
        except user_model.DoesNotExist:
            user_model().set_password(password)  # same cost as a real check
            return None
        finally:
            set_auth_identity()
        if user.check_password(password) and self.user_can_authenticate(user):
            set_current_college(user.college_id)
            return user
        return None
