"""The paper page: parts, problems, and pass-mark overrides with their approval state."""

import uuid

from django.contrib.auth.decorators import login_required
from django.contrib.messages import add_message, constants
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.services import has_permission

from . import services
from .models import Assessment, QuestionPart


@login_required
@require_http_methods(["GET", "POST"])
def paper_page(request: HttpRequest, assessment_id: uuid.UUID) -> HttpResponse:
    paper = get_object_or_404(
        Assessment.objects.select_related("offering__course"), pk=assessment_id
    )
    can_edit = has_permission(request.user, "paper.edit")
    can_decide = has_permission(request.user, "override.apply")
    if not (can_edit or can_decide):
        raise PermissionDenied
    if request.method == "POST":
        part = get_object_or_404(QuestionPart, pk=request.POST.get("part"), assessment=paper)
        try:
            if request.POST.get("action") == "propose" and can_edit:
                services.set_override(
                    part,
                    request.POST.get("pass_mark", ""),
                    request.POST.get("reason", ""),
                    request.user,
                )
                add_message(request, constants.SUCCESS, "Waiting for IQAC approval.")
            elif request.POST.get("action") in ("approve", "reject") and can_decide:
                services.decide_override(part, request.user, request.POST["action"] == "approve")
                add_message(request, constants.SUCCESS, "The decision was saved.")
            else:
                raise PermissionDenied
        except ValidationError as error:
            for message in error.messages:
                add_message(request, constants.ERROR, message)
        except ArithmeticError:
            add_message(request, constants.ERROR, "Please enter the pass mark as a number.")
        return redirect(request.path)
    parts = paper.parts.select_related("question__choice_group", "co")
    return render(
        request,
        "assessments/paper.html",
        {
            "paper": paper,
            "parts": parts,
            "problems": services.validate_paper(paper),
            "can_edit": can_edit,
            "can_decide": can_decide,
        },
    )
