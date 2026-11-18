from django.urls import path

from . import views

app_name = "methodology"

urlpatterns = [
    path("", views.method_list, name="list"),
    path("version/<uuid:version_id>/", views.version_page, name="version"),
]
