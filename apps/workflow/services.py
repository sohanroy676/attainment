"""Workflow's public interface: submit and accept marks, review, approve, sign, reopen, inbox.

Every move is checked against the table in `machine.py`, the person's right over the scope, and
(where the table says so) a written reason. Every move is audited with before, after and reason.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.academics.models import CourseOffering, Programme, Section
from apps.academics.services import sections_visible_to
from apps.accounts.models import RoleAssignment, ScopeType, User
from apps.accounts.permissions import PERMISSIONS
from apps.accounts.services import has_permission
from apps.assessments import services as papers
from apps.assessments.models import Assessment
from apps.audit import services as audit
from apps.marks import services as marks
from apps.marks.models import MarkSheetRow
from apps.results import services as results
from apps.results.models import CalculationRun

from .machine import LOCKED_STAGES, SECTION_MOVES, SEE_SUBMIT_PERMISSION, STAGE_MOVES
from .models import Reopening, ResultStage, SectionState, Signature, SupportGrant

SS = SectionState.Status
RS = ResultStage.Status


# sections --------------------------------------------------
def section_status(section: Section, assessment: Assessment) -> str:
    state = SectionState.objects.filter(section=section, assessment=assessment).first()
    return SS.DRAFT if state is None else state.status


def stage_of(offering: CourseOffering, programme: Programme) -> ResultStage | None:
    return ResultStage.objects.filter(offering=offering, programme=programme).first()


def _locked(section: Section) -> bool:
    """Is the section's result approved or signed (its marks are locked)?"""
    return ResultStage.objects.filter(
        offering_id=section.offering_id, programme_id=section.programme_id,
        status__in=LOCKED_STAGES,
    ).exists()  # fmt: skip


def _permission_for(action: str, move_permission: str, assessment: Assessment) -> str:
    if action == "submit" and assessment.tool == "SEE":
        return SEE_SUBMIT_PERMISSION
    return move_permission


def transition_section(
    section: Section, assessment: Assessment, action: str, actor: User, reason: str = ""
) -> SectionState:
    """Submit, accept or return one section's marks for one assessment."""
    if assessment.offering_id != section.offering_id:
        raise ValidationError("That assessment does not belong to this section's course.")
    with transaction.atomic():
        state, _ = SectionState.objects.select_for_update().get_or_create(
            section=section, assessment=assessment
        )
        move = SECTION_MOVES.get((state.status, action))
        if move is None:
            raise ValidationError(f"A section in state {state.status!r} cannot be {action}ed.")
        permission = _permission_for(action, move.permission, assessment)
        if not has_permission(actor, permission, ScopeType.SECTION, section.pk):
            raise PermissionDenied(f"You may not {action} these marks.")
        if move.reason_required and not reason.strip():
            raise ValidationError(f"A reason is required to {action} marks.")
        if _locked(section):
            raise ValidationError("The result is approved: reopen it first.")
        if action == "submit" and marks.started_rows(assessment, section) == 0:
            raise ValidationError("There are no marks to submit.")
        before = audit.snapshot(state)
        state.status = move.to
        state.reason = reason.strip() if action == "return" else ""
        state.changed_by = actor
        state.save()
        if action == "submit":
            marks.set_rows_status(assessment, section, MarkSheetRow.Status.SUBMITTED, actor)
        elif action == "return":
            marks.set_rows_status(
                assessment, section, MarkSheetRow.Status.ENTERED, actor, reason.strip()
            )
        audit.record_model(
            "updated", state, actor_id=actor.pk, before=before, after=audit.snapshot(state),
            reason=reason.strip() or action,
        )  # fmt: skip
    return state


# course results --------------------------------------------
def sections_of(offering: CourseOffering, programme: Programme) -> list[Section]:
    return list(offering.sections.filter(programme=programme).order_by("name"))


def review_problems(offering: CourseOffering, programme: Programme) -> list[str]:
    """What stops the course result from being reviewed: every section's every assessment must
    be accepted."""
    sections = sections_of(offering, programme)
    assessments = list(offering.assessments.order_by("tool"))
    if not sections:
        return ["The course has no sections for this programme."]
    if not assessments:
        return ["The course has no assessments."]
    return [
        f"{a.name} of section {s.name} is {section_status(s, a)}, not accepted."
        for s in sections
        for a in assessments
        if section_status(s, a) != SS.ACCEPTED
    ]


def _acting_role(actor: User, permission: str, offering: CourseOffering) -> str:
    """The role through which the actor holds `permission` here (recorded on the signature)."""
    for assignment in RoleAssignment.objects.filter(user_id=actor.pk).order_by("role"):
        if permission in PERMISSIONS.get(assignment.role, frozenset()) and has_permission(
            actor, permission, ScopeType.OFFERING, offering.pk
        ):
            return str(assignment.role)
    return ""


def _stage_move(
    offering: CourseOffering,
    programme: Programme,
    action: str,
    actor: User,
    reason: str,
) -> tuple[ResultStage | None, str]:
    stage = (
        ResultStage.objects.select_for_update()
        .filter(offering=offering, programme=programme)
        .first()
    )
    current = None if stage is None else stage.status
    move = STAGE_MOVES.get((current, action))
    if move is None:
        where = "not yet reviewed" if current is None else current
        raise ValidationError(f"A result that is {where} cannot be {action}ed.")
    if not has_permission(actor, move.permission, ScopeType.OFFERING, offering.pk):
        raise PermissionDenied(f"You may not {action} this result.")
    if move.reason_required and not reason.strip():
        raise ValidationError(f"A reason is required to {action} a result.")
    return stage, move.to


def review(offering: CourseOffering, programme: Programme, actor: User) -> ResultStage:
    """The coordinator marks the course result reviewed (every section's marks accepted)."""
    with transaction.atomic():
        stage, target = _stage_move(offering, programme, "review", actor, "")
        problems = review_problems(offering, programme)
        if problems:
            raise ValidationError(problems)
        before = None if stage is None else audit.snapshot(stage)
        if stage is None:
            stage = ResultStage(offering=offering, programme=programme, cycle=1)
        stage.status = target
        stage.save()
        audit.record_model(
            "created" if before is None else "updated", stage, actor_id=actor.pk,
            before=before, after=audit.snapshot(stage), reason="result reviewed",
        )  # fmt: skip
    return stage


def _record_signature(
    stage: ResultStage, kind: str, run: CalculationRun, actor: User, role: str
) -> Signature:
    signature = Signature.objects.create(
        stage=stage, cycle=stage.cycle, kind=kind, run=run, user=actor,
        signer_name=actor.full_name or actor.username, role=role, at=timezone.now(),
        content_hash=results.run_content_hash(run),
    )  # fmt: skip
    audit.record_model("created", signature, actor_id=actor.pk, after=audit.snapshot(signature))
    return signature


def approve(offering: CourseOffering, programme: Programme, actor: User) -> ResultStage:
    """The HoD approves: a snapshot is kept, the marks lock. A result still stopped for review
    (provisional) cannot be approved."""
    with transaction.atomic():
        stage, target = _stage_move(offering, programme, "approve", actor, "")
        assert stage is not None  # the table only allows approve from reviewed
        run = results.snapshot(offering, programme, actor)
        if run.status != CalculationRun.Status.COMPLETE:
            raise ValidationError(
                ["The result is provisional and cannot be approved:", *run.checklist]
            )
        before = audit.snapshot(stage)
        stage.status, stage.run = target, run
        stage.save()
        papers.lock_offering(offering, actor)
        _record_signature(stage, Signature.Kind.APPROVAL, run, actor,
                          _acting_role(actor, "workflow.approve", offering))  # fmt: skip
        audit.record_model(
            "updated", stage, actor_id=actor.pk, before=before, after=audit.snapshot(stage),
            reason="result approved; marks locked",
        )  # fmt: skip
    return stage


def sign(offering: CourseOffering, programme: Programme, actor: User) -> ResultStage:
    """The principal signs: the approved run is sealed and the database refuses any change."""
    with transaction.atomic():
        stage, target = _stage_move(offering, programme, "sign", actor, "")
        assert stage is not None and stage.run is not None
        run = results.seal(stage.run, actor)
        before = audit.snapshot(stage)
        stage.status = target
        stage.save()
        _record_signature(stage, Signature.Kind.SIGNATURE, run, actor,
                          _acting_role(actor, "workflow.sign", offering))  # fmt: skip
        audit.record_model(
            "updated", stage, actor_id=actor.pk, before=before, after=audit.snapshot(stage),
            reason="result signed",
        )  # fmt: skip
    return stage


def reopen(offering: CourseOffering, programme: Programme, actor: User, reason: str) -> ResultStage:
    """HoD or IQAC reopens an approved or signed result with a reason. The marks unlock, a new
    signature cycle starts, and a fresh run is stored. The signed run stays readable."""
    with transaction.atomic():
        stage, target = _stage_move(offering, programme, "reopen", actor, reason)
        assert stage is not None
        before = audit.snapshot(stage)
        Reopening.objects.create(
            stage=stage, from_cycle=stage.cycle, from_status=stage.status,
            reason=reason.strip(), by=actor, at=timezone.now(),
        )  # fmt: skip
        stage.status, stage.run = target, None
        stage.cycle += 1
        stage.save()
        still_locked = (
            ResultStage.objects.filter(offering=offering, status__in=LOCKED_STAGES)
            .exclude(pk=stage.pk)
            .exists()
        )
        if not still_locked:
            papers.unlock_offering(offering, actor, reason.strip())
        results.calculate(offering, programme, actor=actor)
        audit.record_model(
            "updated", stage, actor_id=actor.pk, before=before, after=audit.snapshot(stage),
            reason=reason.strip(),
        )  # fmt: skip
    return stage


# support access --------------------------------------------
MAX_SUPPORT_HOURS = 72


def grant_support(
    user: User, granted_by: User, hours: int, reason: str, now: datetime | None = None
) -> SupportGrant:
    """The college admin lets a support person see this college's marks for a limited time."""
    if not has_permission(granted_by, "users.manage"):
        raise PermissionDenied("Only the college admin can grant support access.")
    if not reason.strip():
        raise ValidationError("A support grant needs a reason.")
    if not 1 <= hours <= MAX_SUPPORT_HOURS:
        raise ValidationError(f"Support access lasts 1 to {MAX_SUPPORT_HOURS} hours.")
    start = now or timezone.now()
    with transaction.atomic():
        grant = SupportGrant.objects.create(
            user=user, granted_by=granted_by, reason=reason.strip(),
            expires_at=start + timedelta(hours=hours),
        )  # fmt: skip
        audit.record_model(
            "created",
            grant,
            actor_id=granted_by.pk,
            after=audit.snapshot(grant),
            reason=reason.strip(),
        )
    return grant


def revoke_support(grant: SupportGrant, actor: User) -> None:
    if not has_permission(actor, "users.manage"):
        raise PermissionDenied("Only the college admin can revoke support access.")
    before = audit.snapshot(grant)
    grant.revoked = True
    grant.save(update_fields=["revoked", "updated_at"])
    audit.record_model(
        "updated", grant, actor_id=actor.pk, before=before, after=audit.snapshot(grant)
    )


def has_support_access(user: User, now: datetime | None = None) -> bool:
    """True while an unrevoked, unexpired grant exists for this person."""
    return SupportGrant.objects.filter(
        user=user, revoked=False, expires_at__gt=now or timezone.now()
    ).exists()


# inbox -----------------------------------------------------
@dataclass(frozen=True)
class Task:
    kind: str  # submit, accept, review, approve, sign
    label: str
    offering_id: uuid.UUID
    section_id: uuid.UUID | None = None
    assessment_id: uuid.UUID | None = None
    programme_id: uuid.UUID | None = None


def inbox(user: User) -> list[Task]:
    """What is waiting for this person: only items they hold the right to act on."""
    tasks: list[Task] = []
    sections = list(
        sections_visible_to(user).select_related("offering__course", "programme").order_by("name")
    )
    pairs: dict[tuple[uuid.UUID, uuid.UUID], tuple[Section, CourseOffering, Programme]] = {}
    for section in sections:
        offering = section.offering
        pairs.setdefault(
            (offering.pk, section.programme_id), (section, offering, section.programme)
        )
        for assessment in offering.assessments.order_by("tool"):
            status = section_status(section, assessment)
            title = f"{offering.course.title} {assessment.name}, section {section.name}"
            submit_permission = _permission_for("submit", "workflow.submit", assessment)
            if (
                status in (SS.DRAFT, SS.RETURNED)
                and has_permission(user, submit_permission, ScopeType.SECTION, section.pk)
                and marks.started_rows(assessment, section)
            ):
                tasks.append(Task("submit", f"Submit {title}", offering.pk, section.pk,
                                  assessment.pk, section.programme_id))  # fmt: skip
            if status == SS.SUBMITTED and has_permission(
                user, "workflow.accept", ScopeType.SECTION, section.pk
            ):
                tasks.append(Task("accept", f"Accept or return {title}", offering.pk, section.pk,
                                  assessment.pk, section.programme_id))  # fmt: skip
    for _section, offering, programme in pairs.values():
        stage = stage_of(offering, programme)
        label = f"{offering.course.title} ({programme.name})"
        current = None if stage is None else stage.status
        wanted = {
            None: ("review", "workflow.accept"),
            RS.REOPENED: ("review", "workflow.accept"),
            RS.REVIEWED: ("approve", "workflow.approve"),
            RS.APPROVED: ("sign", "workflow.sign"),
        }.get(current)
        if wanted is None:
            continue
        kind, permission = wanted
        if not has_permission(user, permission, ScopeType.OFFERING, offering.pk):
            continue
        if kind == "review" and review_problems(offering, programme):
            continue
        tasks.append(
            Task(kind, f"{kind.capitalize()} {label}", offering.pk, programme_id=programme.pk)
        )
    return tasks
