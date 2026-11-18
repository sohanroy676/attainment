from django.urls import path

from . import views

app_name = "results"

urlpatterns = [
    path("<uuid:offering_id>/", views.course_page, name="course"),
    path("<uuid:offering_id>/recalculate/", views.recalculate, name="recalculate"),
    path("<uuid:offering_id>/section/<uuid:section_id>/", views.section_page, name="section"),
    path("<uuid:offering_id>/indirect/", views.indirect_page, name="indirect"),
    path("<uuid:offering_id>/export.xlsx", views.export, name="export"),
    path("run/<uuid:run_id>/explain/", views.explain_page, name="explain"),
]
