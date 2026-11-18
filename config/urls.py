from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import home

from .health import healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("accounts/", include("apps.accounts.urls")),
    path("admin/", admin.site.urls),
    path("imports/", include("apps.imports.urls")),
    path("outcomes/", include("apps.outcomes.urls")),
    path("methods/", include("apps.methodology.urls")),
    path("papers/", include("apps.assessments.urls")),
    path("marks/", include("apps.marks.urls")),
    path("workflow/", include("apps.workflow.urls")),
    path("results/", include("apps.results.urls")),
    path("", home, name="home"),
]
