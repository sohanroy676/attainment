"""Result screens: course and section pages, Explain, indirect entry, Excel export."""

import io
import uuid
from decimal import InvalidOperation

import openpyxl
from django.contrib.auth.decorators import login_required
from django.contrib.messages import add_message, constants
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.academics.models import Batch, CourseOffering, Programme, Section
from apps.accounts.services import has_permission

from . import services
from .models import CalculationRun, IndirectValue
from .present import present, present_batch

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


# batch pages -----------------------------------------------
def _batch_or_404(batch_id: uuid.UUID) -> Batch:
    return get_object_or_404(Batch.objects.select_related("programme"), pk=batch_id)


@login_required
@require_http_methods(["GET", "POST"])
def batch_page(request: HttpRequest, batch_id: uuid.UUID) -> HttpResponse:
    batch = _batch_or_404(batch_id)
    programme_id = batch.programme_id
    if not has_permission(request.user, "reports.view", "programme", programme_id):
        raise PermissionDenied
    can_prepare = has_permission(request.user, "batch.prepare", "programme", programme_id)
    if request.method == "POST":
        if not can_prepare:
            raise PermissionDenied
        services.calculate_batch(
            batch,
            actor=request.user,
            include_unsigned=request.POST.get("include_unsigned") == "1",
            keep="snapshot" in request.POST,
        )
        add_message(
            request,
            constants.SUCCESS,
            "A snapshot of the batch result was kept."
            if "snapshot" in request.POST
            else "The batch result was recalculated.",
        )
        return redirect(request.path)
    run = services.latest_batch_run(batch)
    return render(
        request,
        "results/batch.html",
        {
            "batch": batch,
            "p": None if run is None else present_batch(run),
            "can_prepare": can_prepare,
            "include_unsigned": bool(run and run.include_unsigned),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def batch_inputs_page(request: HttpRequest, batch_id: uuid.UUID) -> HttpResponse:
    """Targets per outcome (batch.prepare) and indirect values (indirect.enter)."""
    batch = _batch_or_404(batch_id)
    if not has_permission(request.user, "batch.prepare", "programme", batch.programme_id):
        raise PermissionDenied
    rows = services.batch_inputs(batch)
    if request.method == "POST":
        targets = {
            code: request.POST[f"target:{code}"]
            for code, _t, _i in rows
            if request.POST.get(f"target:{code}", "").strip()
        }
        indirect = {
            code: request.POST[f"indirect:{code}"]
            for code, _t, _i in rows
            if request.POST.get(f"indirect:{code}", "").strip()
        }
        try:
            if indirect and not has_permission(request.user, "indirect.enter"):
                raise PermissionDenied
            with transaction.atomic():
                services.set_batch_targets(batch, targets, request.user)
                if indirect:
                    services.set_batch_indirect(
                        batch, indirect, request.POST.get("note", ""), request.user
                    )
        except PermissionDenied:
            add_message(request, constants.ERROR, "Only IQAC may enter indirect values.")
        except (ValidationError, InvalidOperation) as error:
            for message in getattr(error, "messages", ["Please enter numbers."]):
                add_message(request, constants.ERROR, message)
        else:
            add_message(
                request, constants.SUCCESS, "Saved. Indirect values are entered, not measured."
            )
            return redirect(request.path)
    return render(request, "results/batch_inputs.html", {"batch": batch, "rows": rows})


@login_required
def batch_compare_page(request: HttpRequest, batch_id: uuid.UUID) -> HttpResponse:
    """This batch beside the two before it, and its computed values beside its old workbook."""
    batch = _batch_or_404(batch_id)
    if not has_permission(request.user, "reports.view", "programme", batch.programme_id):
        raise PermissionDenied
    codes = [o.code for o in services.batch_outcomes(batch.programme)]
    columns = services.comparison_columns(batch)
    table = [(code, [c.values.get(code) for c in columns]) for code in codes]
    return render(
        request,
        "results/batch_compare.html",
        {
            "batch": batch,
            "columns": columns,
            "table": table,
            "side_by_side": services.compare_with_imported(batch),
            "can_prepare": has_permission(
                request.user, "batch.prepare", "programme", batch.programme_id
            ),
        },
    )
