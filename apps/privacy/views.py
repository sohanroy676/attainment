"""Privacy screens for the college admin: the retention list and one student's data export."""

import uuid
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from apps.accounts.services import has_permission
from apps.roster.models import Student
from apps.tenancy.throttle import throttled

from . import services


def _require(request: HttpRequest) -> None:
    if not has_permission(request.user, "privacy.manage"):
        raise PermissionDenied


@login_required
def retention_page(request: HttpRequest) -> HttpResponse:
    _require(request)
    return render(
        request,
        "privacy/retention.html",
        {
            "rows": services.retention_list(date.today()),
            "years": services.retention_years(),
            "days": services.notice_days(),
        },
    )


@login_required
def student_export(request: HttpRequest, student_id: uuid.UUID) -> HttpResponse:
    _require(request)
    if (too_many := throttled(request, "export")) is not None:
        return too_many
    student = get_object_or_404(Student, pk=student_id)
    try:
        data = services.student_export(student, request.user)
    except ValidationError as error:
        return HttpResponse(error.messages[0], status=410, content_type="text/plain")
    response = HttpResponse(services.export_json(data), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="student-{student.pk}.json"'
    return response
