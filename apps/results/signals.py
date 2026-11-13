"""Automatic recalculation: when marks, mapping, target, method, indirect values, an approved
override or an enrolment change, the affected offerings are recalculated once after commit."""

from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.academics.models import CourseOffering
from apps.assessments.models import QuestionPart
from apps.marks.models import MarkCell
from apps.methodology.models import MethodAssignment, MethodVersion
from apps.outcomes.models import COPOMap, Target
from apps.roster.models import Enrolment

from .models import IndirectValue
from .services import mark_dirty, offerings_with_runs


@receiver(post_save, sender=MarkCell)
def _marks_changed(sender: Any, instance: MarkCell, **kwargs: Any) -> None:
    mark_dirty(instance.row.assessment.offering_id)


@receiver([post_save, post_delete], sender=COPOMap)
def _mapping_changed(sender: Any, instance: COPOMap, **kwargs: Any) -> None:
    course_id = instance.co.definition.course_id
    for offering_id in CourseOffering.objects.filter(course_id=course_id).values_list(
        "pk", flat=True
    ):
        mark_dirty(offering_id)


@receiver(post_save, sender=Target)
def _target_changed(sender: Any, instance: Target, **kwargs: Any) -> None:
    if instance.offering_id is not None:
        mark_dirty(instance.offering_id)


@receiver(post_save, sender=IndirectValue)
def _indirect_changed(sender: Any, instance: IndirectValue, **kwargs: Any) -> None:
    mark_dirty(instance.offering_id)


@receiver(post_save, sender=Enrolment)
def _enrolment_changed(sender: Any, instance: Enrolment, **kwargs: Any) -> None:
    mark_dirty(instance.offering_id)


@receiver(post_save, sender=QuestionPart)
def _paper_changed(sender: Any, instance: QuestionPart, **kwargs: Any) -> None:
    mark_dirty(instance.assessment.offering_id)


@receiver(post_save, sender=MethodAssignment)
@receiver(post_save, sender=MethodVersion)
def _method_changed(sender: Any, instance: Any, **kwargs: Any) -> None:
    for offering_id in offerings_with_runs():
        mark_dirty(offering_id)
