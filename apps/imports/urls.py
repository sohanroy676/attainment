from django.urls import path

from . import views

app_name = "imports"

urlpatterns = [
    path("", views.choose_section, name="choose"),
    path("roster/<uuid:section_id>/", views.upload, name="upload"),
    path("<uuid:batch_id>/", views.preview, name="preview"),
]
