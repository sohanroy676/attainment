"""Quality loop screens: one page per course offering, plus the proof file download."""

import uuid
from datetime import date

from django.contrib.auth.decorators import login_required
from django.contrib.messages import add_message, constants
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET, require_POST

from apps.academics.models import CourseOffering
from apps.tenancy.throttle import throttled

from . import services
from .models import ActionPlan, Evidence, Observation


def _offering(offering_id: uuid.UUID) -> CourseOffering:
    return get_object_or_404(
        CourseOffering.objects.select_related("course", "term__academic_year"), pk=offering_id
    )


def _say(request: HttpRequest, error: ValidationError | PermissionDenied) -> None:
    texts = error.messages if isinstance(error, ValidationError) else [str(error)]
    for text in texts:
        add_message(request, constants.ERROR, text)


def _date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw) if raw.strip() else None
    except ValueError:
        raise ValidationError("Please enter the date as year-month-day.") from None


@login_required
@require_GET
def offering_page(request: HttpRequest, offering_id: uuid.UUID) -> HttpResponse:
    offering = _offering(offering_id)
    if not services.may_view(request.user, offering):
        raise PermissionDenied
    return render(
        request,
        "quality/offering.html",
        {
            "offering": offering,
            "observations": list(offering.observations.all()),
            "plans": list(offering.plans.select_related("owner")),
            "earlier": services.previous_plans(offering),
            "actions": list(
                offering.actions_taken.select_related("plan").prefetch_related("evidence")
            ),
            "can_edit": services.may_edit(request.user, offering),
            "draft": services.prefill(offering)
            if services.may_edit(request.user, offering)
            else "",
            "max_mb": services.MAX_FILE_BYTES // 1048576,
        },
    )


@login_required
@require_POST
def observation_add(request: HttpRequest, offering_id: uuid.UUID) -> HttpResponse:
    offering = _offering(offering_id)
    try:
        services.add_observation(offering, request.POST.get("text", ""), request.user)
        add_message(request, constants.SUCCESS, "Observation saved.")
    except (ValidationError, PermissionDenied) as error:
        _say(request, error)
    return redirect("quality:offering", offering.pk)


@login_required
@require_POST
def plan_add(request: HttpRequest, offering_id: uuid.UUID) -> HttpResponse:
    offering = _offering(offering_id)
    try:
        observation = None
        if request.POST.get("observation"):
            observation = get_object_or_404(Observation, pk=request.POST["observation"])
        services.add_plan(
            offering, request.POST.get("text", ""), request.user,
            due_date=_date(request.POST.get("due_date", "")), observation=observation,
        )  # fmt: skip
        add_message(request, constants.SUCCESS, "Action plan saved.")
    except (ValidationError, PermissionDenied) as error:
        _say(request, error)
    return redirect("quality:offering", offering.pk)


@login_required
@require_POST
def observation_edit(
    request: HttpRequest, offering_id: uuid.UUID, observation_id: uuid.UUID
) -> HttpResponse:
    offering = _offering(offering_id)
    observation = get_object_or_404(Observation, pk=observation_id, offering=offering)
    try:
        services.edit_observation(observation, request.POST.get("text", ""), request.user)
        add_message(request, constants.SUCCESS, "Observation updated.")
    except (ValidationError, PermissionDenied) as error:
        _say(request, error)
    return redirect("quality:offering", offering.pk)


@login_required
@require_POST
def plan_edit(request: HttpRequest, offering_id: uuid.UUID, plan_id: uuid.UUID) -> HttpResponse:
    offering = _offering(offering_id)
    plan = get_object_or_404(ActionPlan, pk=plan_id, offering=offering)
    try:
        services.edit_plan(
            plan,
            request.POST.get("text", ""),
            _date(request.POST.get("due_date", "")),
            request.user,
        )
        add_message(request, constants.SUCCESS, "Action plan updated.")
    except (ValidationError, PermissionDenied) as error:
        _say(request, error)
    return redirect("quality:offering", offering.pk)


@login_required
@require_POST
def action_add(request: HttpRequest, offering_id: uuid.UUID, plan_id: uuid.UUID) -> HttpResponse:
    offering = _offering(offering_id)
    plan = get_object_or_404(
        ActionPlan.objects.select_related("offering__term__academic_year"), pk=plan_id
    )
    if (too_many := throttled(request, "upload")) is not None:
        return too_many
    try:
        done_on = _date(request.POST.get("done_on", ""))
        if done_on is None:
            raise ValidationError("Please enter the date the action was done.")
        files = [
            (f.name or "file", f.read(services.MAX_FILE_BYTES + 1))
            for f in request.FILES.getlist("files")
        ]
        services.record_action(
            plan, offering, request.POST.get("text", ""), done_on, request.user, files
        )
        add_message(request, constants.SUCCESS, "Action recorded.")
    except (ValidationError, PermissionDenied) as error:
        _say(request, error)
    return redirect("quality:offering", offering.pk)


@login_required
@require_GET
def evidence_download(request: HttpRequest, evidence_id: uuid.UUID) -> HttpResponse:
    row = get_object_or_404(Evidence.objects.select_related("action__offering"), pk=evidence_id)
    if not services.may_view(request.user, row.action.offering):
        raise PermissionDenied
    response = HttpResponse(bytes(row.content), content_type=row.content_type)
    response["Content-Disposition"] = content_disposition_header(True, row.name)
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response
