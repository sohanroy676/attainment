"""Method screens: list, create from a template, edit a draft, activate, copy to a new draft."""

import uuid
from datetime import date

from django.contrib.auth.decorators import login_required
from django.contrib.messages import add_message, constants
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.services import has_permission

from . import services
from .models import Method, MethodVersion


def _require(request: HttpRequest, permission: str) -> None:
    if not has_permission(request.user, permission):
        raise PermissionDenied


def _errors(request: HttpRequest, error: ValidationError) -> None:
    for message in error.messages:
        add_message(request, constants.ERROR, message)


@login_required
@require_http_methods(["GET", "POST"])
def method_list(request: HttpRequest) -> HttpResponse:
    _require(request, "method.edit")
    if request.method == "POST":
        try:
            version = services.create_from_template(
                request.POST.get("template", ""),
                request.POST.get("name") or None,
                actor=request.user,
            )
        except ValidationError as error:
            _errors(request, error)
        else:
            return redirect("methodology:version", version_id=version.pk)
    methods = Method.objects.prefetch_related("versions").order_by("name")
    return render(
        request,
        "methodology/list.html",
        {"methods": methods, "templates": services.TEMPLATES},
    )


@login_required
@require_http_methods(["GET", "POST"])
def version_page(request: HttpRequest, version_id: uuid.UUID) -> HttpResponse:
    _require(request, "method.edit")
    version = get_object_or_404(MethodVersion.objects.select_related("method"), pk=version_id)
    text = version.config_text
    if request.method == "POST":
        action = request.POST.get("action")
        text = request.POST.get("config_text", version.config_text)
        try:
            if action == "save":
                services.update_draft(version, text, actor=request.user)
                add_message(request, constants.SUCCESS, "The draft was saved and is valid.")
                return redirect(request.path)
            if action == "activate":
                _require(request, "method.activate")
                services.update_draft(version, text, actor=request.user)
                services.activate(
                    version, date.fromisoformat(request.POST["effective_from"]), request.user
                )
                add_message(request, constants.SUCCESS, "The version is now active.")
                return redirect(request.path)
            if action == "copy":
                draft = services.new_draft_from(version, actor=request.user)
                return redirect("methodology:version", version_id=draft.pk)
        except (ValidationError, ValueError, KeyError) as error:
            if isinstance(error, ValidationError):
                _errors(request, error)
            else:
                add_message(request, constants.ERROR, "Please give a valid start date.")
    return render(
        request,
        "methodology/version.html",
        {
            "version": version,
            "text": text,
            "editable": version.status == MethodVersion.Status.DRAFT,
        },
    )
