from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("course/<uuid:offering_id>/", views.course_index, name="course_index"),
    path("course/<uuid:offering_id>/<slug:name>.<slug:fmt>", views.course_report, name="course"),
    path("batch/<uuid:batch_id>/", views.batch_index, name="batch_index"),
    path("batch/<uuid:batch_id>/report.<slug:fmt>", views.batch_report, name="batch"),
    path("nba.xlsx", views.nba_list, name="nba"),
    path("export.<slug:fmt>", views.full_export, name="export"),
]
