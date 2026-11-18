from django.urls import path

from . import views

app_name = "privacy"

urlpatterns = [
    path("retention/", views.retention_page, name="retention"),
    path("student/<uuid:student_id>/export.json", views.student_export, name="export"),
]
