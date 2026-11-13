"""Assessments' public interface: build, validate, copy and override question papers."""

import uuid
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.academics.models import CourseOffering
from apps.accounts.models import User
from apps.accounts.services import has_permission
from apps.audit import services as audit
from apps.outcomes.models import CourseOutcome

from .models import Assessment, ChoiceGroup, Question, QuestionPart

Behaviour = Assessment.Behaviour


def _actor(actor: User | None) -> uuid.UUID | None:
    return None if actor is None else actor.pk


def course_outcomes_for(offering: CourseOffering) -> dict[str, CourseOutcome]:
    """The COs of the offering's course in its newest definition, by code."""
    definition = offering.course.definitions.order_by("-version").first()
    return {} if definition is None else {co.code: co for co in definition.outcomes.all()}


def create_paper(
    offering: CourseOffering,
    tool: str,
    name: str,
    behaviour: str,
    questions: Sequence[Mapping[str, Any]],
    groups: Mapping[str, Mapping[str, Any]] | None = None,
    max_total: Decimal | str | None = None,
    actor: User | None = None,
) -> Assessment:
    """Create a paper from a plain description.

    questions: [{"number": "11", "choice_group": "G" or None,
                 "parts": [{"label": "a", "max": "4", "co": "CO1" or None, "code": optional}]}]
    groups:    {"G": {"best_n": 5, "best_k_parts": {"17": 2}}}
    The paper is saved as given; call validate_paper to see what is wrong with it.
    """
    cos = course_outcomes_for(offering)
    with transaction.atomic():
        assessment = Assessment.objects.create(
            offering=offering,
            tool=tool,
            name=name,
            behaviour=behaviour,
            max_total=None if max_total is None else Decimal(max_total),
        )
        audit.record_model(
            "created", assessment, actor_id=_actor(actor), after=audit.snapshot(assessment)
        )
        made = {
            code: ChoiceGroup.objects.create(
                assessment=assessment,
                code=code,
                best_n=rule["best_n"],
                best_k_parts=dict(rule.get("best_k_parts", {})),
            )
            for code, rule in (groups or {}).items()
        }
        part_order = 0
        for order, spec in enumerate(questions, start=1):
            group = spec.get("choice_group")
            if group is not None and group not in made:
                raise ValidationError(
                    f"Question {spec['number']} uses unknown choice group {group!r}."
                )
            question = Question.objects.create(
                assessment=assessment,
                number=str(spec["number"]),
                order=order,
                choice_group=None if group is None else made[group],
            )
            for part in spec["parts"]:
                co_code = part.get("co")
                if co_code is not None and co_code not in cos:
                    raise ValidationError(
                        f"Part {spec['number']}{part.get('label', '')}: {co_code} is not a "
                        "course outcome of this course."
                    )
                part_order += 1
                QuestionPart.objects.create(
                    assessment=assessment,
                    question=question,
                    label=part.get("label", ""),
                    code=part.get("code") or f"{question.number}{part.get('label', '')}",
                    max=Decimal(str(part["max"])),
                    co=None if co_code is None else cos[co_code],
                    order=part_order,
                )
    return assessment


def answerable_total(assessment: Assessment) -> Decimal:
    """The most a student can score: compulsory parts plus, for each choice group, the best N
    questions (counting only the best K parts of a question where that is set)."""
    total = Decimal(0)
    by_group: dict[uuid.UUID, list[Decimal]] = {}
    for question in assessment.questions.select_related("choice_group").prefetch_related("parts"):
        maxima = sorted((p.max for p in question.parts.all()), reverse=True)
        if question.choice_group is None:
            total += sum(maxima, Decimal(0))
            continue
        k = question.choice_group.best_k_parts.get(question.number)
        value = sum(maxima[:k] if k else maxima, Decimal(0))
        by_group.setdefault(question.choice_group_id, []).append(value)
    for group in assessment.groups.all():
        values = sorted(by_group.get(group.pk, []), reverse=True)
        total += sum(values[: group.best_n], Decimal(0))
    return total


def validate_paper(assessment: Assessment) -> list[str]:
    """Everything wrong with a paper, in plain words. An empty list means it is sound."""
    problems: list[str] = []
    parts = list(assessment.parts.select_related("question", "co__definition__course"))
    if not parts:
        return ["The paper has no parts."]
    course_id = assessment.offering.course_id
    for part in parts:
        where = f"Part {part.code}"
        if part.co is None and assessment.behaviour == Behaviour.QUESTION_WISE:
            problems.append(f"{where} has no CO tag.")
        if part.co is not None and part.co.definition.course_id != course_id:
            problems.append(f"{where} is tagged to a CO of another course.")
        if part.override_pass_mark is not None and part.override_pass_mark > part.max:
            problems.append(f"{where}: the pass-mark override is above the part's maximum.")
    for group in assessment.groups.prefetch_related("questions__parts"):
        questions = {q.number: q for q in group.questions.all()}
        if group.best_n > len(questions):
            problems.append(
                f"Choice group {group.code}: best {group.best_n} is more than its "
                f"{len(questions)} questions."
            )
        for number, k in group.best_k_parts.items():
            question = questions.get(str(number))
            if question is None:
                problems.append(
                    f"Choice group {group.code}: question {number} is not in the group."
                )
            elif k > question.parts.count():
                problems.append(
                    f"Choice group {group.code}: best {k} parts of question {number} is more than "
                    f"its {question.parts.count()} parts."
                )
    if assessment.max_total is not None and not problems:
        expected = answerable_total(assessment)
        if (
            assessment.behaviour != Behaviour.PER_STUDENT_AVERAGE
            and expected != assessment.max_total
        ):
            problems.append(
                f"The total {assessment.max_total} does not match the parts: a student can "
                f"score at most {expected}."
            )
    return problems


# overrides -------------------------------------------------
def _refuse_when_locked(part: QuestionPart) -> None:
    """Overrides are allowed only before approval (design 8.8): after that, reopen first."""
    if part.assessment.status in (Assessment.Status.APPROVED, Assessment.Status.LOCKED):
        raise ValidationError("The result is approved: reopen it before changing an override.")


def set_override(
    part: QuestionPart, pass_mark: Decimal | str, reason: str, actor: User
) -> QuestionPart:
    """Propose a pass mark for one part. It is not used until IQAC approves it."""
    _refuse_when_locked(part)
    if not reason.strip():
        raise ValidationError("An override needs a reason.")
    pass_mark = Decimal(pass_mark)
    if not 0 <= pass_mark <= part.max:
        raise ValidationError(f"The pass mark must be between 0 and {part.max}.")
    before = audit.snapshot(part)
    part.override_pass_mark = pass_mark
    part.override_reason = reason.strip()
    part.override_status = QuestionPart.OverrideStatus.PENDING
    part.override_entered_by = actor
    part.override_approved_by = None
    part.save()
    audit.record_model(
        "updated", part, actor_id=actor.pk, before=before, after=audit.snapshot(part),
        reason=part.override_reason,
    )  # fmt: skip
    return part


def decide_override(part: QuestionPart, approver: User, approve: bool) -> QuestionPart:
    """IQAC (or anyone with override.apply) approves or rejects a proposed override."""
    if not has_permission(approver, "override.apply"):
        raise PermissionDenied("Only IQAC or the HoD can approve a pass-mark override.")
    _refuse_when_locked(part)
    if part.override_status != QuestionPart.OverrideStatus.PENDING:
        raise ValidationError("There is no override waiting for a decision.")
    before = audit.snapshot(part)
    part.override_status = (
        QuestionPart.OverrideStatus.APPROVED if approve else QuestionPart.OverrideStatus.REJECTED
    )
    part.override_approved_by = approver
    part.save()
    audit.record_model(
        "updated", part, actor_id=approver.pk, before=before, after=audit.snapshot(part),
        reason="override approved" if approve else "override rejected",
    )  # fmt: skip
    return part


def approved_overrides(offering: CourseOffering) -> dict[tuple[str, str], tuple[Decimal, str]]:
    """(tool, part code) -> (pass mark, reason) for approved overrides only. Pending and rejected
    overrides are never handed to the engine."""
    rows = QuestionPart.objects.filter(
        assessment__offering=offering,
        override_status=QuestionPart.OverrideStatus.APPROVED,
    ).select_related("assessment")
    return {(p.assessment.tool, p.code): (p.override_pass_mark, p.override_reason) for p in rows}


# the engine view of a paper --------------------------------
def engine_parts(assessment: Assessment) -> list[dict[str, Any]]:
    """Parts in the dictionary form the engine's loader reads (id, question, max, co, group)."""
    return [
        {
            "id": p.code,
            "question": p.question.number,
            "max": str(p.max),
            "co": None if p.co is None else p.co.code,
            "choice_group": None
            if p.question.choice_group is None
            else p.question.choice_group.code,
        }
        for p in assessment.parts.select_related("question__choice_group", "co")
    ]


def engine_choice_rules(assessment: Assessment) -> dict[str, dict[str, Any]]:
    """The paper's choice groups as the engine's per-group rules: {"G": {"best_n": 5, ...}}."""
    return {
        g.code: {"best_n": g.best_n, "best_k_parts": {str(k): v for k, v in g.best_k_parts.items()}}
        for g in assessment.groups.all()
    }


# copying and importing -------------------------------------
def copy_paper(
    source: Assessment, target_offering: CourseOffering, actor: User | None = None
) -> Assessment:
    """Copy a paper (parts, CO tags by code, choice groups) to another offering, for example last
    year's. Overrides are not copied: they belong to one paper and need fresh approval."""
    cos = course_outcomes_for(target_offering)
    questions = []
    for q in source.questions.prefetch_related("parts__co").select_related("choice_group"):
        parts = []
        for p in q.parts.all():
            code = None if p.co is None else p.co.code
            if code is not None and code not in cos:
                raise ValidationError(
                    f"The target course has no {code}; set up its outcomes before copying."
                )
            parts.append({"label": p.label, "code": p.code, "max": p.max, "co": code})
        questions.append(
            {
                "number": q.number,
                "choice_group": None if q.choice_group is None else q.choice_group.code,
                "parts": parts,
            }
        )
    groups = {
        g.code: {"best_n": g.best_n, "best_k_parts": g.best_k_parts} for g in source.groups.all()
    }
    return create_paper(
        target_offering, source.tool, source.name, source.behaviour, questions, groups,
        max_total=source.max_total, actor=actor,
    )  # fmt: skip


def import_engine_paper(
    offering: CourseOffering,
    tool: str,
    name: str,
    behaviour: str,
    parts: Sequence[Mapping[str, Any]],
    choice_rules: Mapping[str, Mapping[str, Any]] | None = None,
    actor: User | None = None,
) -> Assessment:
    """Create a paper from engine-format parts (id, question, max, co, choice_group), as
    written by scripts/build_ds_a.py. Parts of one question are grouped in order of appearance."""
    order: list[str] = []
    by_question: dict[str, dict[str, Any]] = {}
    for p in parts:
        number = str(p.get("question", p["id"]))
        if number not in by_question:
            order.append(number)
            by_question[number] = {
                "number": number,
                "choice_group": p.get("choice_group"),
                "parts": [],
            }
        by_question[number]["parts"].append(
            {"label": "", "code": str(p["id"]), "max": p["max"], "co": p.get("co")}
        )
    return create_paper(
        offering, tool, name, behaviour, [by_question[n] for n in order],
        groups=choice_rules, actor=actor,
    )  # fmt: skip


# approval locks ----------------------------------------------
def lock_offering(offering: CourseOffering, actor: User) -> int:
    """Lock every paper of the offering at approval. Returns how many changed."""
    return _set_offering_status(offering, Assessment.Status.APPROVED, actor, "result approved")


def unlock_offering(offering: CourseOffering, actor: User, reason: str) -> int:
    """Open every locked paper again after a reopen, with the reason in the audit log."""
    return _set_offering_status(offering, Assessment.Status.OPEN, actor, reason)


def _set_offering_status(offering: CourseOffering, status: str, actor: User, reason: str) -> int:
    changed = 0
    for assessment in offering.assessments.all():
        if assessment.status == status:
            continue
        before = audit.snapshot(assessment)
        assessment.status = status
        assessment.save(update_fields=["status", "updated_at"])
        audit.record_model(
            "updated", assessment, actor_id=actor.pk, before=before,
            after=audit.snapshot(assessment), reason=reason,
        )  # fmt: skip
        changed += 1
    return changed
