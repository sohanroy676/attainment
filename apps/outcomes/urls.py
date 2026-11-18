from django.urls import path

from . import views

app_name = "outcomes"

urlpatterns = [
    path("map/<uuid:definition_id>/<uuid:programme_id>/", views.mapping_page, name="mapping"),
]
