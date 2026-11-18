from django.urls import path

from . import views

app_name = "workflow"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("audit/", views.audit_log, name="audit"),
    path("batch/<uuid:batch_id>/", views.batch_stage_page, name="batch"),
    path("batch/<uuid:batch_id>/<str:action>/", views.batch_stage_action, name="batch_action"),
    path(
        "section/<uuid:section_id>/<uuid:assessment_id>/<str:action>/",
        views.section_action,
        name="section_action",
    ),
    path("<uuid:offering_id>/<uuid:programme_id>/", views.stage_page, name="stage"),
    path(
        "<uuid:offering_id>/<uuid:programme_id>/<str:action>/",
        views.stage_action,
        name="stage_action",
    ),
]
