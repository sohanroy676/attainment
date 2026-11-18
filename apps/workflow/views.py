"""Workflow screens: the task inbox, a course result's approval page, and the audit viewer."""

import uuid

from django.contrib.auth.decorators import login_required
from django.contrib.messages import add_message, constants
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.academics.models import Batch, CourseOffering, Programme, Section
from apps.accounts.services import has_permission
from apps.assessments.models import Assessment
from apps.results import services as results

from . import services
from .machine import BATCH_MOVES, SECTION_MOVES, STAGE_MOVES


def _say(request: HttpRequest, error: ValidationError | PermissionDenied) -> None:
    texts = error.messages if isinstance(error, ValidationError) else [str(error)]
    for text in texts:
        add_message(request, constants.ERROR, text)


@login_required
def inbox(request: HttpRequest) -> HttpResponse:
    return render(request, "workflow/inbox.html", {"tasks": services.inbox(request.user)})


@login_required
@require_POST
def section_action(
    request: HttpRequest, section_id: uuid.UUID, assessment_id: uuid.UUID, action: str
) -> HttpResponse:
    section = get_object_or_404(Section, pk=section_id)
    assessment = get_object_or_404(Assessment, pk=assessment_id)
    if action not in {a for _, a in SECTION_MOVES}:
        raise Http404
    try:
        services.transition_section(
            section, assessment, action, request.user, request.POST.get("reason", "")
        )
        add_message(request, constants.SUCCESS, f"Done: {action}.")
    except (ValidationError, PermissionDenied) as error:
        _say(request, error)
    return redirect("workflow:stage", section.offering_id, section.programme_id)


def _stage_context(
    request: HttpRequest, offering: CourseOffering, programme: Programme
) -> dict[str, object]:
    stage = services.stage_of(offering, programme)
    sections = services.sections_of(offering, programme)
    grid = [
        {
            "assessment": a,
            "cells": [{"section": s, "status": services.section_status(s, a)} for s in sections],
        }
        for a in offering.assessments.order_by("tool")
    ]
    return {
        "offering": offering,
        "programme": programme,
        "stage": stage,
        "sections": sections,
        "grid": grid,
        "signatures": [] if stage is None else list(stage.signatures.order_by("at")),
        "reopenings": [] if stage is None else list(stage.reopenings.order_by("at")),
        "problems": services.review_problems(offering, programme),
        "differs": results.differs_from_signed(offering, programme),
        "signed_run": results.signed_run(offering, programme),
        "may": {
            action: has_permission(request.user, move.permission, "offering", offering.pk)
            for (_, action), move in STAGE_MOVES.items()
        },
    }


@login_required
def stage_page(
    request: HttpRequest, offering_id: uuid.UUID, programme_id: uuid.UUID
) -> HttpResponse:
    offering = get_object_or_404(
        CourseOffering.objects.select_related("course", "term"), pk=offering_id
    )
    programme = get_object_or_404(Programme, pk=programme_id)
    if not has_permission(request.user, "reports.view", "offering", offering.pk):
        raise PermissionDenied
    return render(request, "workflow/stage.html", _stage_context(request, offering, programme))


@login_required
@require_POST
def stage_action(
    request: HttpRequest, offering_id: uuid.UUID, programme_id: uuid.UUID, action: str
) -> HttpResponse:
    offering = get_object_or_404(CourseOffering, pk=offering_id)
    programme = get_object_or_404(Programme, pk=programme_id)
    try:
        if action == "review":
            services.review(offering, programme, request.user)
        elif action == "approve":
            services.approve(offering, programme, request.user)
        elif action == "sign":
            services.sign(offering, programme, request.user)
        elif action == "reopen":
            services.reopen(offering, programme, request.user, request.POST.get("reason", ""))
        else:
            raise Http404
        add_message(request, constants.SUCCESS, f"Done: {action}.")
    except (ValidationError, PermissionDenied) as error:
        _say(request, error)
    return redirect("workflow:stage", offering.pk, programme.pk)


@login_required
def audit_log(request: HttpRequest) -> HttpResponse:
    """The audit viewer, newest first: all events with the right college-wide, a department's
    events with the right over that department."""
    scope = services.audit_scope(request.user)
    if scope is None:
        raise PermissionDenied
    events = scope.order_by("-seq")
    wanted = request.GET.get("action", "").strip()
    if wanted:
        events = events.filter(action__startswith=wanted)
    page = Paginator(events, 50).get_page(request.GET.get("page"))
    return render(request, "workflow/audit.html", {"page": page, "wanted": wanted})


@login_required
def batch_stage_page(request: HttpRequest, batch_id: uuid.UUID) -> HttpResponse:
    batch = get_object_or_404(Batch.objects.select_related("programme"), pk=batch_id)
    if not has_permission(request.user, "reports.view", "programme", batch.programme_id):
        raise PermissionDenied
    stage = services.batch_stage_of(batch)
    signed = results.signed_batch_run(batch)
    return render(
        request,
        "workflow/batch_stage.html",
        {
            "batch": batch,
            "stage": stage,
            "signatures": [] if stage is None else list(stage.signatures.order_by("at")),
            "reopenings": [] if stage is None else list(stage.reopenings.order_by("at")),
            "differs": results.batch_differs_from_signed(batch),
            "signed_run": signed,
            "may": {
                action: has_permission(
                    request.user, move.permission, "programme", batch.programme_id
                )
                for (_, action), move in BATCH_MOVES.items()
            },
        },
    )


@login_required
@require_POST
def batch_stage_action(request: HttpRequest, batch_id: uuid.UUID, action: str) -> HttpResponse:
    batch = get_object_or_404(Batch.objects.select_related("programme"), pk=batch_id)
    try:
        if action == "prepare":
            services.prepare_batch(batch, request.user)
        elif action == "approve":
            services.approve_batch(batch, request.user)
        elif action == "sign":
            services.sign_batch(batch, request.user)
        elif action == "reopen":
            services.reopen_batch(batch, request.user, request.POST.get("reason", ""))
        else:
            raise Http404
        add_message(request, constants.SUCCESS, f"Done: {action}.")
    except (ValidationError, PermissionDenied) as error:
        _say(request, error)
    return redirect("workflow:batch", batch.pk)
