"""Quality loop services: observations, action plans, actions taken and proof files (design 8.9).

Who may do what: anyone with `observations.edit` over the offering or one of its sections writes
and records; anyone with `reports.view` there reads. Proof files are PDF, PNG or JPEG only, at
most 5 MB each and a fixed total per college; the type is read from the file's own bytes.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.academics.models import CourseOffering
from apps.accounts.models import User
from apps.accounts.services import has_permission
from apps.audit import services as audit
from apps.results import services as results

from .models import ActionPlan, ActionTaken, Evidence, Observation

MAX_FILE_BYTES = getattr(settings, "QUALITY_FILE_MAX_BYTES", 5 * 1024 * 1024)
MAX_COLLEGE_BYTES = getattr(settings, "QUALITY_COLLEGE_MAX_BYTES", 200 * 1024 * 1024)
MAX_FILES_PER_ACTION = 10
MAX_TEXT = 5000

# extension -> (content type, magic bytes at the start of the file)
KINDS = {
    "pdf": ("application/pdf", b"%PDF-"),
    "png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    "jpg": ("image/jpeg", b"\xff\xd8\xff"),
    "jpeg": ("image/jpeg", b"\xff\xd8\xff"),
}


# rights ----------------------------------------------------
def _may(user: User, permission: str, offering: CourseOffering) -> bool:
    """The right over the offering, or over one of its sections (a lecturer holds it there)."""
    if has_permission(user, permission, "offering", offering.pk):
        return True
    return any(
        has_permission(user, permission, "section", section.pk)
        for section in offering.sections.all()
    )


def may_view(user: User, offering: CourseOffering) -> bool:
    return _may(user, "reports.view", offering) or _may(user, "observations.edit", offering)


def may_edit(user: User, offering: CourseOffering) -> bool:
    return _may(user, "observations.edit", offering)


def _require_edit(user: User, offering: CourseOffering) -> None:
    if not may_edit(user, offering):
        raise PermissionDenied("You may not write observations or plans for this course.")


def _clean_text(text: str, what: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise ValidationError(f"Please write the {what}.")
    if len(cleaned) > MAX_TEXT:
        raise ValidationError(f"The {what} is longer than {MAX_TEXT} characters.")
    return cleaned


# the gap view fills in a first draft ---------------------------
def prefill(offering: CourseOffering) -> str:
    """A draft of observations from the gap view: COs under target and the weakest questions."""
    programmes = results.programmes_of(offering)
    lines: list[str] = []
    for programme in programmes:
        gaps = results.course_gaps(offering, programme, question_limit=3)
        if gaps is None:
            continue
        prefix = f"{programme.name}: " if len(programmes) > 1 else ""
        lines += [
            f"{prefix}{g.key} is below the target ({g.value} against {g.target})." for g in gaps.cos
        ]
        lines += [
            f"{prefix}Weak question: {q.tool} part {q.part} ({q.co or 'no CO'}), "
            f"{q.percent}% of students passed."
            for q in gaps.questions
            if q.percent != "-"
        ]
    return "\n".join(lines)


# observations and plans ------------------------------------
def add_observation(offering: CourseOffering, text: str, actor: User) -> Observation:
    _require_edit(actor, offering)
    row = Observation.objects.create(
        offering=offering, text=_clean_text(text, "observation"), written_by=actor
    )
    audit.record_model("created", row, actor_id=actor.pk, after=audit.snapshot(row))
    return row


def add_plan(
    offering: CourseOffering,
    text: str,
    actor: User,
    owner: User | None = None,
    due_date: date | None = None,
    observation: Observation | None = None,
) -> ActionPlan:
    _require_edit(actor, offering)
    if observation is not None and observation.offering_id != offering.pk:
        raise ValidationError("That observation belongs to another course offering.")
    row = ActionPlan.objects.create(
        offering=offering, text=_clean_text(text, "action plan"), owner=owner or actor,
        due_date=due_date, observation=observation, written_by=actor,
    )  # fmt: skip
    audit.record_model("created", row, actor_id=actor.pk, after=audit.snapshot(row))
    return row


def previous_plans(offering: CourseOffering) -> list[ActionPlan]:
    """Plans written on earlier offerings of the same course, oldest first, so the lecturer can
    record what was done about them."""
    start = offering.term.academic_year.start_date
    return list(
        ActionPlan.objects.filter(
            offering__course_id=offering.course_id,
            offering__term__academic_year__start_date__lt=start,
        )
        .select_related("offering__term", "owner")
        .prefetch_related("actions__evidence")
        .order_by("offering__term__academic_year__start_date", "created_at")
    )


# actions taken ---------------------------------------------
def add_action(
    plan: ActionPlan, offering: CourseOffering, text: str, done_on: date, actor: User
) -> ActionTaken:
    """Record what was done about an earlier plan, on a later offering of the same course."""
    _require_edit(actor, offering)
    if plan.offering.course_id != offering.course_id or plan.offering_id == offering.pk:
        raise ValidationError("An action is recorded on a later offering of the plan's course.")
    if plan.offering.term.academic_year.start_date >= offering.term.academic_year.start_date:
        raise ValidationError("An action is recorded on a later offering than the plan.")
    if done_on > timezone.localdate():
        raise ValidationError("The date an action was done cannot be in the future.")
    row = ActionTaken.objects.create(
        plan=plan, offering=offering, text=_clean_text(text, "action taken"),
        done_on=done_on, recorded_by=actor,
    )  # fmt: skip
    audit.record_model("created", row, actor_id=actor.pk, after=audit.snapshot(row))
    return row


# proof files -----------------------------------------------
@dataclass(frozen=True)
class CheckedFile:
    name: str
    content_type: str
    size: int
    sha256: str


def safe_name(filename: str) -> str:
    """The file's own name only: no folders, no control characters, at most 120 characters."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip().strip(".")
    return name[:120] or "file"


def check_file(filename: str, content: bytes) -> CheckedFile:
    """Refuse anything that is not a PDF, PNG or JPEG of acceptable size."""
    name = safe_name(filename)
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in KINDS:
        raise ValidationError(f"{name}: only PDF, PNG and JPEG files are accepted.")
    if not content:
        raise ValidationError(f"{name}: the file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise ValidationError(f"{name}: the file is larger than {MAX_FILE_BYTES // 1048576} MB.")
    content_type, magic = KINDS[extension]
    if not content.startswith(magic):
        raise ValidationError(f"{name}: the file is not really a {extension.upper()} file.")
    return CheckedFile(name, content_type, len(content), hashlib.sha256(content).hexdigest())


def college_bytes_used() -> int:
    return int(Evidence.objects.aggregate(total=Sum("size"))["total"] or 0)


def add_evidence(
    action: ActionTaken, files: list[tuple[str, bytes]], actor: User
) -> list[Evidence]:
    """Attach proof files to an action taken. All or nothing: one bad file rejects the lot."""
    _require_edit(actor, action.offering)
    if not files:
        raise ValidationError("Please choose a file.")
    if action.evidence.count() + len(files) > MAX_FILES_PER_ACTION:
        raise ValidationError(f"An action can have at most {MAX_FILES_PER_ACTION} proof files.")
    checked = [(check_file(name, content), content) for name, content in files]
    if college_bytes_used() + sum(c.size for c, _ in checked) > MAX_COLLEGE_BYTES:
        raise ValidationError("The college's proof file storage is full.")
    saved: list[Evidence] = []
    with transaction.atomic():
        for info, content in checked:
            row = Evidence.objects.create(
                action=action, name=info.name, content_type=info.content_type, size=info.size,
                sha256=info.sha256, content=content, uploaded_by=actor,
            )  # fmt: skip
            audit.record_model(
                "created", row, actor_id=actor.pk,
                after={"size": row.size, "content_type": row.content_type, "sha256": row.sha256},
            )  # fmt: skip
            saved.append(row)
    return saved


def record_action(
    plan: ActionPlan,
    offering: CourseOffering,
    text: str,
    done_on: date,
    actor: User,
    files: list[tuple[str, bytes]] | None = None,
) -> ActionTaken:
    """Record an action and its proof files together: if a file is refused, nothing is saved."""
    with transaction.atomic():
        action = add_action(plan, offering, text, done_on, actor)
        if files:
            add_evidence(action, files, actor)
    return action
