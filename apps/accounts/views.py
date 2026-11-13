import uuid
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
    PasswordResetConfirmView,
    PasswordResetView,
)
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.http import urlsafe_base64_decode

from apps.tenancy.services import set_auth_identity, set_current_college

from .forms import LoginForm, TenantPasswordResetForm


class TenantLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class TenantPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    form_class = TenantPasswordResetForm
    success_url = reverse_lazy("accounts:password_reset_done")


class TenantPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")

    def get_user(self, uidb64: str) -> Any:
        try:
            user_id = uuid.UUID(urlsafe_base64_decode(uidb64).decode())
        except (TypeError, ValueError, OverflowError, UnicodeDecodeError):
            return None
        set_auth_identity(user_id=user_id)
        user = get_user_model().auth_lookup.filter(pk=user_id, is_active=True).first()
        if user is not None:
            # The token is checked next; saving the new password needs the user's college.
            set_current_college(user.college_id)
        return user


@login_required
def home(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/home.html")
