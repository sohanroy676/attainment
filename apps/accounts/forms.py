from collections.abc import Iterable
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm

from apps.tenancy.services import set_auth_identity


class LoginForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "That username and password do not match. Please try again.",
        "inactive": "This account is switched off. Please ask your college administrator.",
    }


class TenantPasswordResetForm(PasswordResetForm):
    """Finds users by email before a college is known (same narrow lookup as login)."""

    def get_users(self, email: str) -> Iterable[Any]:
        set_auth_identity(login=email)
        user_model = get_user_model()
        users = user_model.auth_lookup.filter(email__iexact=email, is_active=True)
        return [user for user in users if user.has_usable_password()]
