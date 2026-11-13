"""A7, A10, A11 and the structure rules; the setup screens (Django admin) and their isolation."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client

from apps.academics.models import (
    Batch,
    Course,
    CourseCode,
    CourseGroup,
    CourseGroupMember,
    CourseOffering,
    Department,
    FacultyAssignment,
    Programme,
    Section,
)
from apps.academics.services import assign_faculty, check_section, sections_visible_to
from apps.accounts.models import Role, ScopeType
from apps.accounts.services import assign_role, has_permission
from apps.accounts.tests.helpers import PASSWORD, make_college, make_user
from apps.audit.models import AuditEvent
from apps.audit.services import verify_chain
from apps.tenancy.services import college_context

from .helpers import make_structure

pytestmark = [pytest.mark.integration]


def test_a7_one_course_with_two_codes_and_twin_courses_in_one_group(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        CourseCode.objects.create(course=s.course, code="UI21", department=s.department)
        CourseCode.objects.create(course=s.course, code="UII21")
        twin = Course.objects.create(title="Deep Learning AIML (synthetic)")
        CourseCode.objects.create(course=twin, code="UI21A")
        group = CourseGroup.objects.create(name="CSE/AIML twins", kind=CourseGroup.Kind.TWIN)
        for course in (s.course, twin):
            CourseGroupMember.objects.create(group=group, course=course)
        elective = CourseGroup.objects.create(
            name="Open elective I", kind=CourseGroup.Kind.OPEN_ELECTIVE
        )
        CourseGroupMember.objects.create(group=elective, course=twin)
        assert s.course.codes.count() == 2  # one course identity, two codes
        assert set(group.courses.all()) == {s.course, twin}
        assert list(twin.groups.order_by("name").values_list("name", flat=True)) == [
            "CSE/AIML twins",
            "Open elective I",
        ]
        with pytest.raises(IntegrityError), transaction.atomic():
            CourseCode.objects.create(course=s.course, code="UI21")  # the same code twice


def test_section_batch_must_belong_to_the_sections_programme(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        other = Programme.objects.create(department=s.department, name="B.E. AIML", level="UG")
        foreign = Batch.objects.create(
            programme=other, name="2021-25", start_year=2021, end_year=2025
        )
        s.section_a.batch = foreign
        with pytest.raises(ValidationError):
            check_section(s.section_a)


def test_batch_years_and_unique_codes_are_enforced_by_the_database(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        with pytest.raises(IntegrityError), transaction.atomic():
            Batch.objects.create(programme=s.programme, name="bad", start_year=2025, end_year=2021)
        with pytest.raises(IntegrityError), transaction.atomic():
            Department.objects.create(name="Duplicate", code="CSE")


def test_the_same_department_code_can_exist_in_two_colleges(db: None) -> None:
    a, b = make_college("a"), make_college("b")
    make_structure(a)
    make_structure(b)  # both have a department coded CSE
    with college_context(a.id):
        assert Department.objects.count() == 1
    with college_context(b.id):
        assert Department.objects.count() == 1


# A10 -------------------------------------------------------
def test_a10_lecturer_sees_only_assigned_sections(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    lecturer = make_user(college, "a.lecturer")
    with college_context(college.id):
        assign_faculty(lecturer, s.offering, s.section_a)
        assert list(sections_visible_to(lecturer)) == [s.section_a]
        assert has_permission(lecturer, "marks.enter_internal", ScopeType.SECTION, s.section_a.pk)
        assert not has_permission(
            lecturer, "marks.enter_internal", ScopeType.SECTION, s.section_b.pk
        )
        assert FacultyAssignment.objects.filter(user=lecturer).count() == 1


def test_a10_assigning_the_whole_offering_covers_all_its_sections(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    lecturer = make_user(college, "a.lecturer")
    with college_context(college.id):
        assign_faculty(lecturer, s.offering)
        assert set(sections_visible_to(lecturer)) == {s.section_a, s.section_b}
        assert has_permission(lecturer, "marks.enter_internal", ScopeType.SECTION, s.section_b.pk)


def test_a10_a_department_head_covers_the_departments_sections_but_not_others(db: None) -> None:
    college = make_college("a")
    s = make_structure(college, "CSE")
    elsewhere = make_structure(college, "ECE")
    hod = make_user(college, "a.hod")
    with college_context(college.id):
        assign_role(hod, Role.HOD, ScopeType.DEPARTMENT, s.department.pk)
        assert set(sections_visible_to(hod)) == {s.section_a, s.section_b}
        assert has_permission(hod, "workflow.approve", ScopeType.SECTION, s.section_a.pk)
        assert has_permission(hod, "workflow.approve", ScopeType.PROGRAMME, s.programme.pk)
        assert not has_permission(
            hod, "workflow.approve", ScopeType.SECTION, elsewhere.section_a.pk
        )
        assert not has_permission(hod, "workflow.approve")  # no scope given: college-wide only


def test_a10_college_wide_roles_see_every_section_and_unassigned_users_none(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    admin, nobody = make_user(college, "a.admin"), make_user(college, "a.nobody")
    with college_context(college.id):
        assign_role(admin, Role.COLLEGE_ADMIN)
        assert set(sections_visible_to(admin)) == {s.section_a, s.section_b}
        assert list(sections_visible_to(nobody)) == []


def test_assigning_a_section_of_another_offering_is_refused(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    lecturer = make_user(college, "a.lecturer")
    with college_context(college.id):
        other_course = Course.objects.create(title="Other course (synthetic)")
        other_offering = CourseOffering.objects.create(course=other_course, term=s.term)
        foreign = Section.objects.create(
            offering=other_offering, name="A", programme=s.programme, batch=s.batch
        )
        with pytest.raises(ValidationError):
            assign_faculty(lecturer, s.offering, foreign)


# A11 and the setup screens (Django admin) ------------------
def _login(username: str) -> Client:
    client = Client()
    response = client.post("/accounts/login/", {"username": username, "password": PASSWORD})
    assert response.status_code == 302
    return client


def test_a11_admin_creates_and_updates_are_audited_with_the_actor(committed_db: None) -> None:
    college = make_college("a")
    admin = make_user(college, "a.admin")
    with college_context(college.id):
        assign_role(admin, Role.COLLEGE_ADMIN)
    client = _login("a.admin")
    assert client.get("/admin/").status_code == 200
    response = client.post(
        "/admin/academics/department/add/", {"name": "Mechanical", "code": "MECH"}
    )
    assert response.status_code == 302
    with college_context(college.id):
        department = Department.objects.get(code="MECH")
        created = AuditEvent.objects.get(action="academics.department.created")
        assert created.actor_id == admin.id and created.entity_id == str(department.pk)
        assert created.after["code"] == "MECH" and created.at is not None
    change = client.post(
        f"/admin/academics/department/{department.pk}/change/",
        {"name": "Mechanical Engg", "code": "MECH"},
    )
    assert change.status_code == 302
    with college_context(college.id):
        updated = AuditEvent.objects.get(action="academics.department.updated")
        assert updated.before["name"] == "Mechanical"
        assert updated.after["name"] == "Mechanical Engg"
        assert verify_chain()


def test_a11_faculty_assignment_through_admin_creates_the_role_and_logs_both(
    committed_db: None,
) -> None:
    college = make_college("a")
    s = make_structure(college)
    admin, lecturer = make_user(college, "a.admin"), make_user(college, "a.lecturer")
    with college_context(college.id):
        assign_role(admin, Role.COLLEGE_ADMIN)
    client = _login("a.admin")
    response = client.post(
        "/admin/academics/facultyassignment/add/",
        {"user": str(lecturer.pk), "offering": str(s.offering.pk), "section": str(s.section_a.pk)},
    )
    assert response.status_code == 302, response.content.decode()[:300]
    with college_context(college.id):
        assert has_permission(lecturer, "marks.enter_internal", ScopeType.SECTION, s.section_a.pk)
        actions = set(AuditEvent.objects.values_list("action", flat=True))
        assert {"academics.facultyassignment.created", "role.assigned"} <= actions


def test_only_structure_managers_may_use_the_setup_screens(committed_db: None) -> None:
    college = make_college("a")
    lecturer = make_user(college, "a.lecturer")
    make_user(college, "a.nobody")
    with college_context(college.id):
        assign_role(lecturer, Role.LECTURER, ScopeType.SECTION, lecturer.pk)
    for username in ("a.lecturer", "a.nobody"):
        response = _login(username).get("/admin/academics/department/")
        assert response.status_code in (302, 403)
        assert response.status_code == 403 or "/login" in response["Location"]
    assert Client().get("/admin/academics/department/").status_code == 302


def test_the_admin_never_shows_another_colleges_records(committed_db: None) -> None:
    a, b = make_college("a"), make_college("b")
    admin_a = make_user(a, "a.admin")
    make_structure(b, "SECRET")  # a department that only College B has
    with college_context(a.id):
        assign_role(admin_a, Role.COLLEGE_ADMIN)
    client = _login("a.admin")
    page = client.get("/admin/academics/department/")
    assert page.status_code == 200 and b"SECRET" not in page.content
    with college_context(b.id):
        other = Department.objects.get(code="SECRET")
    url = f"/admin/academics/department/{other.pk}/change/"
    assert client.get(url).status_code in (302, 404)
    assert b"SECRET" not in client.get(url, follow=True).content
