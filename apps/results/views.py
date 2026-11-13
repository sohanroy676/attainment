"""Result screens: course and section pages, Explain, indirect entry, Excel export."""

import io
import uuid
from decimal import InvalidOperation

import openpyxl
from django.contrib.auth.decorators import login_required
from django.contrib.messages import add_message, constants
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.academics.models import CourseOffering, Programme, Section
from apps.accounts.services import has_permission

from . import services
from .models import CalculationRun, IndirectValue
from .present import present

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _may_view_course(request: HttpRequest, offering: CourseOffering) -> bool:
    return has_permission(request.user, "reports.view", "offering", offering.pk)


def _programme(request: HttpRequest, offering: CourseOffering) -> Programme | None:
    programmes = services.programmes_of(offering)
    wanted = request.GET.get("programme") or request.POST.get("programme")
    if wanted:
        return next((p for p in programmes if str(p.pk) == wanted), None)
    return programmes[0] if len(programmes) == 1 else None


@login_required
def course_page(request: HttpRequest, offering_id: uuid.UUID) -> HttpResponse:
    offering = get_object_or_404(
        CourseOffering.objects.select_related("course", "term"), pk=offering_id
    )
    if not _may_view_course(request, offering):
        raise PermissionDenied
    programmes = services.programmes_of(offering)
    programme = _programme(request, offering)
    if programme is None:
        return render(
            request, "results/choose.html", {"offering": offering, "programmes": programmes}
        )
    run = services.latest_run(offering, programme)
    shown = None if run is None else present(run)
    sections = list(offering.sections.filter(programme=programme).order_by("name"))
    return render(
        request,
        "results/course.html",
        {
            "offering": offering,
            "programme": programme,
            "run": run,
            "p": shown,
            "sections": sections,
            "can_indirect": has_permission(request.user, "indirect.enter"),
            "differs": services.differs_from_signed(offering, programme),
        },
    )


@login_required
@require_POST
def recalculate(request: HttpRequest, offering_id: uuid.UUID) -> HttpResponse:
    offering = get_object_or_404(CourseOffering, pk=offering_id)
    if not _may_view_course(request, offering):
        raise PermissionDenied
    programme = _programme(request, offering)
    if programme is None:
        raise PermissionDenied
    if "snapshot" in request.POST:
        services.snapshot(offering, programme, request.user)
        add_message(request, constants.SUCCESS, "A snapshot of this result was kept.")
    else:
        services.calculate(offering, programme, actor=request.user)
        add_message(request, constants.SUCCESS, "The result was recalculated.")
    return redirect(f"/results/{offering.pk}/?programme={programme.pk}")


@login_required
def section_page(
    request: HttpRequest, offering_id: uuid.UUID, section_id: uuid.UUID
) -> HttpResponse:
    offering = get_object_or_404(CourseOffering, pk=offering_id)
    section = get_object_or_404(
        Section.objects.select_related("programme"), pk=section_id, offering=offering
    )
    if not has_permission(request.user, "reports.view", "section", section.pk):
        raise PermissionDenied
    run = services.latest_run(offering, section.programme)
    shown = None if run is None else present(run, section.name)
    return render(
        request,
        "results/section.html",
        {"offering": offering, "section": section, "p": shown, "run": run},
    )


@login_required
def explain_page(request: HttpRequest, run_id: uuid.UUID) -> HttpResponse:
    run = get_object_or_404(
        CalculationRun.objects.select_related("offering", "method_version"), pk=run_id
    )
    key = request.GET.get("key", "")
    allowed_course = _may_view_course(request, run.offering)
    sections = {s.name: s for s in run.offering.sections.all()}
    entries = []
    for scope, entry in services.explain(run, key):
        if scope == "course" and allowed_course:
            entries.append((scope, entry))
        elif scope.startswith("section "):
            section = sections.get(scope[8:])
            if section is not None and has_permission(
                request.user, "reports.view", "section", section.pk
            ):
                entries.append((scope, entry))
    if not entries and not allowed_course:
        raise PermissionDenied
    return render(
        request,
        "results/explain.html",
        {"run": run, "key": key, "entries": entries},
    )


@login_required
@require_http_methods(["GET", "POST"])
def indirect_page(request: HttpRequest, offering_id: uuid.UUID) -> HttpResponse:
    offering = get_object_or_404(CourseOffering, pk=offering_id)
    if not has_permission(request.user, "indirect.enter"):
        raise PermissionDenied
    definition = services.latest_definition(offering)
    cos = [] if definition is None else [co.code for co in definition.outcomes.all()]
    current = {i.co_code: i for i in IndirectValue.objects.filter(offering=offering)}
    if request.method == "POST":
        values = {
            c: request.POST[f"co:{c}"] for c in cos if request.POST.get(f"co:{c}", "").strip()
        }
        try:
            services.set_indirect(offering, values, request.POST.get("note", ""), request.user)
        except (ValidationError, InvalidOperation) as error:
            messages = getattr(error, "messages", ["Please enter numbers."])
            for message in messages:
                add_message(request, constants.ERROR, message)
        else:
            add_message(
                request, constants.SUCCESS, "Saved. These values are entered, not measured."
            )
            return redirect(request.path)
    rows = [(c, current[c].value if c in current else "") for c in cos]
    return render(request, "results/indirect.html", {"offering": offering, "rows": rows})


@login_required
def export(request: HttpRequest, offering_id: uuid.UUID) -> HttpResponse:
    offering = get_object_or_404(CourseOffering, pk=offering_id)
    if not _may_view_course(request, offering):
        raise PermissionDenied
    programme = _programme(request, offering)
    run = None if programme is None else services.latest_run(offering, programme)
    if run is None:
        raise PermissionDenied
    shown = present(run)
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Result"
    sheet.append(
        [
            str(offering),
            shown.method_name,
            f"engine {run.engine_version}",
            f"input {run.input_hash}",
        ]
    )
    sheet.append(["Status", "Provisional" if not shown.complete else "Complete"])
    for table in shown.tables:
        sheet.append([])
        sheet.append([table.title, *table.header])
        for label, cells in table.rows:
            sheet.append([label, *[c.text for c in cells]])
    sheet.append([])
    sheet.append(["Course attainment", shown.course_text, f"unrounded {shown.course_unrounded}"])
    sheet.append(["Target", shown.target])
    sheet.append(["Attained", {True: "Yes", False: "No", None: ""}[shown.attained]])
    for line in shown.checklist + shown.flags:
        sheet.append(["Note", line])
    out = io.BytesIO()
    book.save(out)
    response = HttpResponse(out.getvalue(), content_type=XLSX)
    response["Content-Disposition"] = 'attachment; filename="result.xlsx"'
    return response
