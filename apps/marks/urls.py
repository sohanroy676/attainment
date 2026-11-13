from django.urls import path

from . import views

app_name = "marks"

urlpatterns = [
    path("<uuid:assessment_id>/<uuid:section_id>/", views.grid, name="grid"),
    path("<uuid:assessment_id>/<uuid:section_id>/template/", views.template, name="template"),
    path("<uuid:assessment_id>/<uuid:section_id>/import/", views.upload_marks, name="import"),
    path("<uuid:assessment_id>/scripts/", views.upload_scripts, name="scripts"),
    path("<uuid:assessment_id>/see/", views.upload_see, name="see"),
    path("batch/<uuid:batch_id>/", views.batch_page, name="batch"),
    path("cell/<uuid:cell_id>/history/", views.cell_history, name="history"),
]
