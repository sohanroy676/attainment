from django.urls import include, path

from apps.accounts.views import home

from .health import healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("accounts/", include("apps.accounts.urls")),
    path("", home, name="home"),
]
