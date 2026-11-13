"""Marks screens: the grid, the pre-filled sheet, imports with preview, SEE uploads, history."""

import uuid
from collections.abc import Callable

from django.contrib.auth.decorators import login_required
from django.contrib.messages import add_message, constants
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.academics.models import Section
from apps.accounts.services import has_permission
from apps.assessments.models import Assessment
from apps.imports.models import ImportBatch
from apps.imports.parsers import UnreadableFile
from apps.roster.models import Enrolment
from apps.roster.services import current_identifier

from . import importer, services
from .models import MarkCell

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _roll(enrolment: Enrolment, section: Section) -> str:
    return current_identifier(enrolment.student, section=section) or "-"


@login_required
@require_http_methods(["GET", "POST"])
def grid(request: HttpRequest, assessment_id: uuid.UUID, section_id: uuid.UUID) -> HttpResponse:
    assessment = get_object_or_404(Assessment.objects.select_related("offering"), pk=assessment_id)
    section = get_object_or_404(Section, pk=section_id, offering=assessment.offering)
    if not services.can_read(request.user, assessment, section):
        raise PermissionDenied
    editable = services.can_write(request.user, assessment, section)
    parts = list(assessment.parts.select_related("co"))
    enrolments = list(
        Enrolment.objects.filter(section=section, status=Enrolment.Status.ENROLLED).select_related(
            "student"
        )
    )
    errors: dict[str, str] = {}
    posted: dict[str, str] = {}
    saved = 0
    if request.method == "POST":
        if not editable:
            raise PermissionDenied
        for enrolment in enrolments:
            for part in parts:
                key = f"{enrolment.pk}:{part.code}"
                text, old = request.POST.get(f"cell:{key}", ""), request.POST.get(f"old:{key}", "")
                if text == old:
                    continue
                posted[key] = text
                try:
                    state, value = services.parse_mark_text(text, part.max)
                    row = services.get_row(enrolment, assessment, create=True)
                    services.save_cell(
                        row,
                        part,
                        state,
                        value,
                        request.user,
                        expected_version=int(request.POST.get(f"ver:{key}", "0")),
                        reason=request.POST.get("reason", ""),
                    )
                    saved += 1
                    posted.pop(key)
                except ValidationError as error:
                    errors[key] = error.messages[0]
        if not errors:
            add_message(request, constants.SUCCESS, f"Saved {saved} marks.")
            return redirect(request.path)
        add_message(request, constants.ERROR, "Some marks were not saved; see the marked cells.")
    rows = []
    for enrolment in sorted(enrolments, key=lambda e: (len(_roll(e, section)), _roll(e, section))):
        sheet = services.get_row(enrolment, assessment)
        stored = {} if sheet is None else {c.part_id: c for c in sheet.cells.all()}
        cells = []
        for part in parts:
            cell = stored.get(part.pk)
            key = f"{enrolment.pk}:{part.code}"
            cells.append(
                {
                    "key": key,
                    "code": part.code,
                    "old": services.cell_text(cell),
                    "text": posted.get(key, services.cell_text(cell)),
                    "ver": 0 if cell is None else cell.row_version,
                    "error": errors.get(key, ""),
                    "cell": cell,
                }
            )
        rows.append({"roll": _roll(enrolment, section), "cells": cells})
    context = {
        "assessment": assessment,
        "section": section,
        "parts": parts,
        "rows": rows,
        "editable": editable,
    }
    return render(request, "marks/grid.html", context)


@login_required
def template(request: HttpRequest, assessment_id: uuid.UUID, section_id: uuid.UUID) -> HttpResponse:
    assessment = get_object_or_404(Assessment, pk=assessment_id)
    section = get_object_or_404(Section, pk=section_id, offering=assessment.offering)
    if not services.can_write(request.user, assessment, section):
        raise PermissionDenied
    response = HttpResponse(importer.build_template(assessment, section), content_type=XLSX)
    name = f"{assessment.tool}-{section.name}.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


def _upload(
    request: HttpRequest,
    assessment: Assessment,
    run: Callable[[str, bytes], ImportBatch],
    title: str,
) -> HttpResponse:
    if request.method == "POST":
        file = request.FILES.get("file")
        if file is None:
            add_message(request, constants.ERROR, "Please choose a file.")
        else:
            try:
                batch = run(file.name, file.read())
            except UnreadableFile as error:
                add_message(request, constants.ERROR, str(error))
            except ValidationError as error:
                add_message(request, constants.ERROR, "; ".join(error.messages))
            else:
                return redirect("marks:batch", batch_id=batch.pk)
    return render(request, "marks/upload.html", {"title": title, "assessment": assessment})


@login_required
@require_http_methods(["GET", "POST"])
def upload_marks(
    request: HttpRequest, assessment_id: uuid.UUID, section_id: uuid.UUID
) -> HttpResponse:
    assessment = get_object_or_404(Assessment, pk=assessment_id)
    section = get_object_or_404(Section, pk=section_id, offering=assessment.offering)
    if not services.can_write(request.user, assessment, section):
        raise PermissionDenied

    def run(name: str, content: bytes) -> ImportBatch:
        return importer.preview_marks(assessment, section, name, content, request.user)

    title = f"Upload marks: {assessment.name}, section {section.name}"
    return _upload(request, assessment, run, title)


@login_required
@require_http_methods(["GET", "POST"])
def upload_scripts(request: HttpRequest, assessment_id: uuid.UUID) -> HttpResponse:
    assessment = get_object_or_404(Assessment, pk=assessment_id, tool="SEE")
    if not has_permission(request.user, "marks.enter_see"):
        raise PermissionDenied

    def run(name: str, content: bytes) -> ImportBatch:
        return importer.preview_scripts(assessment, name, content, request.user)

    return _upload(request, assessment, run, "Upload the script mapping (script_no, roll_no)")


@login_required
@require_http_methods(["GET", "POST"])
def upload_see(request: HttpRequest, assessment_id: uuid.UUID) -> HttpResponse:
    assessment = get_object_or_404(Assessment, pk=assessment_id, tool="SEE")
    if not has_permission(request.user, "marks.enter_see"):
        raise PermissionDenied

    def run(name: str, content: bytes) -> ImportBatch:
        return importer.preview_see_marks(assessment, name, content, request.user)

    return _upload(request, assessment, run, "Upload SEE marks by script number")


@login_required
@require_http_methods(["GET", "POST"])
def batch_page(request: HttpRequest, batch_id: uuid.UUID) -> HttpResponse:
    batch = get_object_or_404(
        ImportBatch.objects.select_related("assessment", "section"), pk=batch_id
    )
    kinds = (ImportBatch.Kind.MARKS, ImportBatch.Kind.SCRIPTS)
    if batch.kind not in kinds or batch.assessment is None:
        raise PermissionDenied
    allowed = (
        services.can_write(request.user, batch.assessment, batch.section)
        if batch.section is not None
        else has_permission(request.user, "marks.enter_see")
    )
    if not allowed:
        raise PermissionDenied
    if request.method == "POST":
        try:
            if batch.kind == ImportBatch.Kind.SCRIPTS:
                importer.commit_scripts(batch, request.user)
            else:
                importer.commit_marks(batch, request.user)
        except ValidationError as error:
            for message in error.messages:
                add_message(request, constants.ERROR, message)
        else:
            add_message(request, constants.SUCCESS, "The file was loaded.")
        return redirect(request.path)
    return render(request, "marks/batch.html", {"batch": batch, "report": batch.report})


@login_required
def cell_history(request: HttpRequest, cell_id: uuid.UUID) -> HttpResponse:
    cell = get_object_or_404(
        MarkCell.objects.select_related("row__assessment", "row__enrolment", "part"), pk=cell_id
    )
    if not services.can_read(request.user, cell.row.assessment, cell.row.enrolment.section):
        raise PermissionDenied
    return render(request, "marks/history.html", {"cell": cell, "changes": services.history(cell)})
