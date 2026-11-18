from django.urls import path

from . import views

app_name = "assessments"

urlpatterns = [
    path("<uuid:assessment_id>/", views.paper_page, name="paper"),
]
