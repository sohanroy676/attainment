from django.contrib.auth.views import LogoutView, PasswordResetCompleteView, PasswordResetDoneView
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.TenantLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("password-reset/", views.TenantPasswordResetView.as_view(), name="password_reset"),
    path(
        "password-reset/sent/",
        PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        views.TenantPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
]
