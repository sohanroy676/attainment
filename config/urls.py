from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import home

from .health import healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("accounts/", include("apps.accounts.urls")),
    path("admin/", admin.site.urls),
    path("imports/", include("apps.imports.urls")),
    path("", home, name="home"),
]
