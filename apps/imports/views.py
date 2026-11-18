"""Roster import screens: choose a section, upload, preview, confirm or discard."""

import uuid

from django.contrib.auth.decorators import login_required
from django.contrib.messages import add_message, constants
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.academics.models import Section
from apps.academics.services import sections_visible_to
from apps.accounts.services import has_permission
from apps.roster import services as roster

from . import services
from .models import ImportBatch
from .parsers import UnreadableFile


def _may_import(request: HttpRequest, section: Section) -> bool:
    return has_permission(request.user, "roster.manage", "section", section.pk)


@login_required
def choose_section(request: HttpRequest) -> HttpResponse:
    sections = [
        s
        for s in sections_visible_to(request.user).select_related("offering__course", "programme")
        if _may_import(request, s)
    ]
    return render(request, "imports/choose.html", {"sections": sections})


@login_required
@require_http_methods(["GET", "POST"])
def upload(request: HttpRequest, section_id: uuid.UUID) -> HttpResponse:
    section = get_object_or_404(Section.objects.select_related("offering__course"), pk=section_id)
    if not _may_import(request, section):
        raise PermissionDenied
    if request.method == "POST":
        file = request.FILES.get("file")
        scope = request.POST.get("scope", "section")
        if file is None:
            add_message(request, constants.ERROR, "Please choose a file.")
        elif scope not in services.SCOPES:
            add_message(request, constants.ERROR, "Please choose where roll numbers are unique.")
        else:
            try:
                batch = services.preview_roster(
                    section, file.name, file.read(), scope=scope, actor=request.user
                )
            except UnreadableFile as error:
                add_message(request, constants.ERROR, str(error))
            else:
                return redirect("imports:preview", batch_id=batch.pk)
    return render(request, "imports/upload.html", {"section": section, "scopes": services.SCOPES})


@login_required
@require_http_methods(["GET", "POST"])
def preview(request: HttpRequest, batch_id: uuid.UUID) -> HttpResponse:
    batch = get_object_or_404(ImportBatch.objects.select_related("section__offering"), pk=batch_id)
    if not _may_import(request, batch.section):
        raise PermissionDenied
    if request.method == "POST":
        if "discard" in request.POST:
            services.reject_roster(batch, actor=request.user)
            add_message(request, constants.INFO, "The file was discarded. Nothing was changed.")
            return redirect("imports:upload", section_id=batch.section_id)
        try:
            services.commit_roster(
                batch, actor=request.user, withdraw_missing="withdraw_missing" in request.POST
            )
        except ValidationError as error:
            add_message(request, constants.ERROR, " ".join(error.messages))
            return redirect("imports:preview", batch_id=batch.pk)
        add_message(request, constants.SUCCESS, "The roster was updated.")
        return redirect("imports:preview", batch_id=batch.pk)
    missing = []
    if batch.status == ImportBatch.Status.PREVIEWED:
        plan = services.plan_roster(batch.section, services.rows_of(batch), batch.scope)
        missing = [
            (roster.current_identifier(s, section=batch.section) or "-", s.name)
            for s in plan.missing
        ]
    return render(
        request,
        "imports/preview.html",
        {"batch": batch, "report": batch.report, "missing": missing},
    )
