"""The CO-PO grid: one row per course outcome, one column per programme outcome."""

import uuid

from django.contrib.auth.decorators import login_required
from django.contrib.messages import add_message, constants
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.academics.models import Programme
from apps.accounts.services import has_permission

from . import services
from .models import CourseDefinitionVersion, ProgrammeOutcome

CHOICES = [("", "blank"), ("0", "0"), ("1", "1"), ("2", "2"), ("3", "3")]


@login_required
@require_http_methods(["GET", "POST"])
def mapping_page(
    request: HttpRequest, definition_id: uuid.UUID, programme_id: uuid.UUID
) -> HttpResponse:
    definition = get_object_or_404(CourseDefinitionVersion, pk=definition_id)
    programme = get_object_or_404(Programme, pk=programme_id)
    if not has_permission(request.user, "outcomes.edit"):
        raise PermissionDenied
    outcomes = list(ProgrammeOutcome.objects.filter(programme=programme).exclude(kind="PEO"))
    cos = list(definition.outcomes.all())
    if request.method == "POST":
        grid: dict[str, dict[str, int | None]] = {}
        try:
            for co in cos:
                grid[co.code] = {}
                for outcome in outcomes:
                    raw = request.POST.get(f"cell:{co.code}:{outcome.code}", "")
                    grid[co.code][outcome.code] = int(raw) if raw != "" else None
            changed = services.save_mapping_grid(definition, programme, grid, actor=request.user)
        except (ValueError, ValidationError) as error:
            messages = error.messages if isinstance(error, ValidationError) else [str(error)]
            for message in messages:
                add_message(request, constants.ERROR, message)
        else:
            add_message(request, constants.SUCCESS, f"Saved ({changed} cells changed).")
            return redirect(request.path)
    current = services.mapping_grid(definition, programme)
    rows = [
        {
            "co": co,
            "cells": [
                {
                    "name": f"cell:{co.code}:{o.code}",
                    "value": ""
                    if o.code not in current[co.code]
                    else str(current[co.code][o.code]),
                }
                for o in outcomes
            ],
        }
        for co in cos
    ]
    return render(
        request,
        "outcomes/mapping.html",
        {
            "definition": definition,
            "programme": programme,
            "outcomes": outcomes,
            "rows": rows,
            "choices": CHOICES,
        },
    )
