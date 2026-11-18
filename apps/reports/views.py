"""Report screens: HTML, PDF and Excel of the stored results. Access follows the role table:
course reports need `reports.view` over the offering, batch reports over the programme, the NBA
list `reports.view` college-wide and the full export `data.export`."""

import uuid
from collections.abc import Callable
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from apps.academics.models import Batch, CourseOffering, Programme
from apps.accounts.services import has_permission
from apps.audit import services as audit
from apps.results import services as results
from apps.tenancy.throttle import throttled

from . import context, excel, export
from . import render as rendering
from .chart import bar_chart

COURSE_HTML = ("co_sheet", "analysis", "co_po", "action_taken", "appendix")
COURSE_XLSX: dict[str, Callable[[context.CourseReport], bytes]] = {
    "co_sheet": excel.course_co_sheet,
    "analysis": excel.course_result,
    "co_po": excel.course_co_po,
}
TITLES = {
    "co_sheet": "CO attainment by assessment",
    "analysis": "Course CO attainment analysis",
    "co_po": "CO-PO / PSO table",
    "action_taken": "Action Taken Report",
    "appendix": "Explanation appendix",
}


def _programme(request: HttpRequest, offering: CourseOffering) -> Programme:
    programmes = results.programmes_of(offering)
    wanted = request.GET.get("programme")
    if wanted:
        found = next((p for p in programmes if str(p.pk) == wanted), None)
    else:
        found = programmes[0] if len(programmes) == 1 else None
    if found is None:
        raise Http404("Choose a programme.")
    return found


def _deliver(
    request: HttpRequest, template: str, ctx: dict[str, Any], fmt: str, filename: str
) -> HttpResponse:
    html = rendering.render_html(template, request.user.college.code, ctx, request)
    if fmt == "html":
        return HttpResponse(html)
    if not rendering.pdf_available():
        return HttpResponse(
            "PDF output is not available on this server (the WeasyPrint libraries are missing). "
            "Use the HTML version and print it, or run the app in Docker.",
            status=503,
            content_type="text/plain",
        )
    if (too_many := throttled(request, "pdf")) is not None:
        return too_many
    response = HttpResponse(rendering.to_pdf(html), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}.pdf"'
    return response


def _xlsx(data: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(data, content_type=excel.XLSX)
    response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
    return response


@login_required
def course_index(request: HttpRequest, offering_id: uuid.UUID) -> HttpResponse:
    offering = get_object_or_404(
        CourseOffering.objects.select_related("course", "term"), pk=offering_id
    )
    if not has_permission(request.user, "reports.view", "offering", offering.pk):
        raise PermissionDenied
    programmes = results.programmes_of(offering)
    return render(
        request,
        "reports/course_index.html",
        {
            "offering": offering,
            "programmes": programmes,
            "reports": [(key, TITLES[key], key in COURSE_XLSX) for key in COURSE_HTML],
        },
    )


@login_required
def course_report(
    request: HttpRequest, offering_id: uuid.UUID, name: str, fmt: str
) -> HttpResponse:
    if name not in COURSE_HTML or fmt not in ("html", "pdf", "xlsx"):
        raise Http404
    offering = get_object_or_404(
        CourseOffering.objects.select_related("course", "term__academic_year"), pk=offering_id
    )
    if not has_permission(request.user, "reports.view", "offering", offering.pk):
        raise PermissionDenied
    if fmt == "xlsx" and name not in COURSE_XLSX:
        raise Http404
    programme = _programme(request, offering)
    report = context.course_report(offering, programme)
    if report is None:
        raise Http404("This course has no result yet.")
    ctx: dict[str, Any] = {"r": report, "footer": report.footer}
    template = name
    if name == "analysis":
        template = "analysis_lab" if report.kind == "lab" else "analysis_theory"
    if name == "appendix":
        keys = request.GET.getlist("key") or [
            "course",
            *[f"final/{row.co}" for row in report.co_rows],
        ]
        ctx["explained"] = [
            (key, results.explain_visible(report.run, key, request.user)) for key in keys
        ]
    if fmt == "xlsx":
        return _xlsx(COURSE_XLSX[name](report), f"{name}-{offering.pk}")
    return _deliver(request, template, ctx, fmt, f"{name}-{offering.pk}")


def _batch_or_404(batch_id: uuid.UUID) -> Batch:
    return get_object_or_404(Batch.objects.select_related("programme"), pk=batch_id)


@login_required
def batch_index(request: HttpRequest, batch_id: uuid.UUID) -> HttpResponse:
    batch = _batch_or_404(batch_id)
    if not has_permission(request.user, "reports.view", "programme", batch.programme_id):
        raise PermissionDenied
    return render(request, "reports/batch_index.html", {"batch": batch})


@login_required
def batch_report(request: HttpRequest, batch_id: uuid.UUID, fmt: str) -> HttpResponse:
    if fmt not in ("html", "pdf", "xlsx"):
        raise Http404
    batch = _batch_or_404(batch_id)
    if not has_permission(request.user, "reports.view", "programme", batch.programme_id):
        raise PermissionDenied
    report = context.batch_report(batch)
    if report is None:
        raise Http404("This batch has no result yet.")
    if fmt == "xlsx":
        return _xlsx(excel.batch_workbook(report), f"batch-{batch.pk}")
    ctx = {"r": report, "footer": report.footer, "chart_svg": bar_chart(report.codes, report.chart)}
    return _deliver(request, "batch", ctx, fmt, f"batch-{batch.pk}")


@login_required
def nba_list(request: HttpRequest) -> HttpResponse:
    if not has_permission(request.user, "reports.view"):
        raise PermissionDenied
    return _xlsx(excel.nba_workbook(context.nba_rows()), "nba-course-list")


@login_required
def full_export(request: HttpRequest, fmt: str) -> HttpResponse:
    if fmt not in ("xlsx", "json"):
        raise Http404
    if not has_permission(request.user, "data.export"):
        raise PermissionDenied
    if (too_many := throttled(request, "export")) is not None:
        return too_many
    audit.record(
        "college.exported",
        "college",
        request.user.college_id,
        actor_id=request.user.pk,
        after={"format": fmt, "rows": export.counts()},
    )
    if fmt == "json":
        response = HttpResponse(export.as_json(), content_type="application/json")
        response["Content-Disposition"] = 'attachment; filename="college-export.json"'
        return response
    return _xlsx(export.as_excel(), "college-export")
