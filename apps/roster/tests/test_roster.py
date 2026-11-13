"""A3 to A6 and the privacy rule for the audit log. Synthetic students only."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.academics.tests.helpers import make_structure
from apps.accounts.tests.helpers import make_college, make_user
from apps.audit.models import AuditEvent
from apps.roster import services as roster
from apps.roster.models import Enrolment, SectionMembership, Student, StudentIdentifier
from apps.tenancy.services import college_context

pytestmark = [pytest.mark.integration]


def _student(name: str, roll: str, section=None, batch=None):  # type: ignore[no-untyped-def]
    student = roster.create_student(name)
    roster.add_identifier(student, roll, section=section, batch=batch)
    return student


def test_a1_a_gap_in_roll_numbers_creates_no_student_for_the_gap(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        for roll in [1, 2, 3, 4, 6, 7, 8]:  # the roster skips 5
            _student(f"Student {roll}", str(roll), section=s.section_a)
        assert Student.objects.count() == 7
        assert roster.find_by_identifier("5", section=s.section_a) is None
        assert roster.find_by_identifier("6", section=s.section_a) is not None


def test_a3_the_same_roll_number_in_two_sections_is_two_students(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        in_a = _student("Student A1", "1", section=s.section_a)
        in_b = _student("Student B1", "1", section=s.section_b)
        assert in_a.pk != in_b.pk
        assert roster.find_by_identifier("1", section=s.section_a) == in_a
        assert roster.find_by_identifier("1", section=s.section_b) == in_b
        with pytest.raises(ValidationError, match="already in use"):
            _student("Impostor", "1", section=s.section_a)  # same roll in the same section


def test_identifier_scopes_batch_and_college_wide(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        first = _student("Student 1", "1602-23-748-001", batch=s.batch)  # alphanumeric
        assert roster.find_by_identifier("1602-23-748-001", batch=s.batch) == first
        with pytest.raises(ValidationError):
            _student("Student 2", "1602-23-748-001", batch=s.batch)
        # the same value without a scope is a different label space
        other = _student("Student 3", "1602-23-748-001")
        assert other != first
        with pytest.raises(ValidationError):
            roster.add_identifier(other, "x", section=s.section_a, batch=s.batch)  # two scopes


def test_a4_a_roll_number_change_keeps_the_student_and_the_history(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        student = _student("Student 1", "17", section=s.section_a)
        roster.change_identifier(
            student, "roll_no", "117", on=date(2025, 7, 1), section=s.section_a
        )
        assert roster.find_by_identifier("117", section=s.section_a) == student
        assert roster.find_by_identifier("17", section=s.section_a) is None  # no longer current
        history = list(roster.identifier_history(student).values_list("value", "valid_to"))
        assert history == [("17", date(2025, 7, 1)), ("117", None)]
        assert Student.objects.count() == 1
        # the old number is free for someone else now
        assert _student("Student 2", "17", section=s.section_a) is not None


def test_a5_a_section_change_keeps_history_and_the_enrolments_section_decides(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        student = _student("Student 1", "1", section=s.section_a)
        enrolment = roster.enrol(student, s.offering, s.section_a, on=date(2025, 6, 10))
        roster.move_section(enrolment, s.section_b, on=date(2025, 8, 1), reason="timetable")
        enrolment.refresh_from_db()
        assert enrolment.section == s.section_b  # marks now count in B
        memberships = list(
            SectionMembership.objects.filter(student=student)
            .order_by("valid_from")
            .values_list("section__name", "valid_from", "valid_to")
        )
        assert memberships == [
            ("A", date(2025, 6, 10), date(2025, 8, 1)),
            ("B", date(2025, 8, 1), None),
        ]
        assert set(roster.enrolled_students(s.offering, s.section_b)) == {student}
        assert set(roster.enrolled_students(s.offering, s.section_a)) == set()
        actions = AuditEvent.objects.filter(entity="roster.enrolment").values_list(
            "action", "reason"
        )
        assert ("roster.enrolment.updated", "timetable") in set(actions)


def test_a6_withdrawn_students_keep_their_history_and_not_enrolled_differs(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        stays = _student("Student 1", "1", section=s.section_a)
        leaves = _student("Student 2", "2", section=s.section_a)
        never = _student("Student 3", "3", section=s.section_a)  # known, but never enrolled
        roster.enrol(stays, s.offering, s.section_a)
        gone = roster.enrol(leaves, s.offering, s.section_a)
        roster.withdraw(gone, on=date(2025, 9, 1), reason="left the college")
        assert set(roster.enrolled_students(s.offering)) == {stays}
        assert Enrolment.objects.filter(student=leaves, status="withdrawn").count() == 1  # kept
        assert not Enrolment.objects.filter(student=never).exists()  # not enrolled: no row at all
        assert Student.objects.count() == 3


def test_enrolling_twice_or_into_another_offerings_section_is_refused(db: None) -> None:
    from apps.academics.models import Course, CourseOffering, Section

    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        student = _student("Student 1", "1", section=s.section_a)
        roster.enrol(student, s.offering, s.section_a)
        with pytest.raises(ValidationError, match="already"):
            roster.enrol(student, s.offering, s.section_b)
        other = CourseOffering.objects.create(
            course=Course.objects.create(title="Other (synthetic)"), term=s.term
        )
        foreign = Section.objects.create(
            offering=other, name="A", programme=s.programme, batch=s.batch
        )
        with pytest.raises(ValidationError, match="different offering"):
            roster.enrol(student, s.offering, foreign)


def test_the_audit_log_never_holds_names_or_identifier_values(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    actor = make_user(college, "a.admin")
    with college_context(college.id):
        student = roster.create_student("Distinctive Name", actor=actor)
        roster.add_identifier(student, "SECRET-ROLL-77", section=s.section_a, actor=actor)
        roster.enrol(student, s.offering, s.section_a, actor=actor)
        events = list(AuditEvent.objects.filter(action__startswith="roster."))
        assert len(events) >= 3
        blob = " ".join(str(e.after) + str(e.before) + e.entity_id for e in events)
        assert "Distinctive" not in blob and "SECRET-ROLL-77" not in blob
        assert str(student.pk) in blob  # people are referred to by internal id
        assert all(e.actor_id == actor.pk for e in events)


def test_student_needs_a_name_and_identifier_needs_a_value(db: None) -> None:
    college = make_college("a")
    with college_context(college.id):
        with pytest.raises(ValidationError):
            roster.create_student("   ")
        student = roster.create_student("Student 1")
        with pytest.raises(ValidationError):
            roster.add_identifier(student, "  ")


def test_roster_tables_are_isolated_between_colleges(db: None) -> None:
    a, b = make_college("a"), make_college("b")
    sa, sb = make_structure(a), make_structure(b)
    with college_context(a.id):
        _student("Student A", "1", section=sa.section_a)
    with college_context(b.id):
        _student("Student B", "1", section=sb.section_a)
    with college_context(a.id):
        assert Student.objects.count() == 1 and StudentIdentifier.objects.count() == 1
        assert roster.find_by_identifier("1", section=sb.section_a) is None
    with college_context(None):
        assert Student.objects.count() == 0
