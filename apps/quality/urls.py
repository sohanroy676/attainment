from django.urls import path

from . import views

app_name = "quality"

urlpatterns = [
    path("evidence/<uuid:evidence_id>/", views.evidence_download, name="evidence"),
    path("<uuid:offering_id>/", views.offering_page, name="offering"),
    path("<uuid:offering_id>/observation/", views.observation_add, name="observation"),
    path("<uuid:offering_id>/plan/", views.plan_add, name="plan"),
    path(
        "<uuid:offering_id>/observation/<uuid:observation_id>/edit/",
        views.observation_edit,
        name="observation_edit",
    ),
    path("<uuid:offering_id>/plan/<uuid:plan_id>/edit/", views.plan_edit, name="plan_edit"),
    path("<uuid:offering_id>/action/<uuid:plan_id>/", views.action_add, name="action"),
]
