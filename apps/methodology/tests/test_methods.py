"""A5 lifecycle and immutability, A6 inheritance and locks, A7 validation, and the screens."""

import json
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client

from apps.academics.models import AcademicYear, CourseOffering, Term, University
from apps.academics.tests.helpers import make_structure
from apps.accounts.models import Role
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import PASSWORD, make_college, make_user
from apps.methodology import services
from apps.methodology.models import MethodVersion
from apps.tenancy.services import college_context

pytestmark = [pytest.mark.integration]

D = date


def _tweak(version: MethodVersion, **top_level: object) -> str:
    raw = json.loads(version.config_text)
    raw.update(top_level)
    return json.dumps(raw)


def test_a5_activation_fixes_the_hash_and_makes_the_version_immutable(db: None) -> None:
    college = make_college("a")
    with college_context(college.id):
        draft = services.create_from_template("vasavi_theory")
        assert draft.status == "draft" and draft.content_hash == ""
        services.activate(draft, D(2025, 6, 1))
        draft.refresh_from_db()
        assert draft.status == "active" and draft.effective_from == D(2025, 6, 1)
        assert draft.content_hash == services.config_hash(draft.config_text)
        with pytest.raises(ValidationError, match="cannot be edited"):
            services.update_draft(draft, draft.config_text)
        with pytest.raises(ValidationError, match="Only a draft"):
            services.activate(draft, D(2026, 6, 1))


def test_a5_the_database_itself_refuses_to_change_or_delete_a_published_version(db: None) -> None:
    college = make_college("a")
    with college_context(college.id):
        version = services.create_from_template("vasavi_theory")
        services.activate(version, D(2025, 6, 1))
        for statement, args in (
            (
                "UPDATE methodology_methodversion SET config_text = %s WHERE id = %s",
                ["{}", version.pk],
            ),
            ("UPDATE methodology_methodversion SET content_hash = 'x' WHERE id = %s", [version.pk]),
            ("UPDATE methodology_methodversion SET status = 'draft' WHERE id = %s", [version.pk]),
            ("DELETE FROM methodology_methodversion WHERE id = %s", [version.pk]),
        ):
            with (
                pytest.raises(DatabaseError, match="immutable|cannot be deleted"),
                transaction.atomic(),
                connection.cursor() as cursor,
            ):
                cursor.execute(statement, args)
        version.refresh_from_db()
        assert version.status == "active"


def test_a5_an_earlier_term_keeps_its_version_and_a_later_term_gets_the_new_one(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        v1 = services.create_from_template("vasavi_theory")
        services.activate(v1, D(2025, 6, 1))
        v2 = services.new_draft_from(v1)
        services.update_draft(v2, _tweak(v1, missing_data="renormalise"))
        services.activate(v2, D(2026, 6, 1))
        v1.refresh_from_db()
        assert v1.status == "retired" and v1.effective_to == D(2026, 5, 31)
        services.assign_method("college", v1.method)

        year2 = AcademicYear.objects.create(
            label="2026-27", start_date=D(2026, 6, 1), end_date=D(2027, 5, 31)
        )
        later = CourseOffering.objects.create(
            course=s.course, term=Term.objects.create(academic_year=year2, number=6)
        )
        earlier_version, _ = services.method_for_offering(s.offering)
        later_version, _ = services.method_for_offering(later)
        assert earlier_version.number == 1 and later_version.number == 2
        assert services.version_in_force(v1.method, D(2025, 5, 31)) is None  # before any version
        assert services.version_in_force(v1.method, D(2026, 5, 31)).number == 1  # type: ignore[union-attr]
        assert services.version_in_force(v1.method, D(2026, 6, 1)).number == 2  # type: ignore[union-attr]


def test_a5_activation_dates_must_move_forward(db: None) -> None:
    college = make_college("a")
    with college_context(college.id):
        v1 = services.create_from_template("vasavi_theory")
        services.activate(v1, D(2025, 6, 1))
        v2 = services.new_draft_from(v1)
        with pytest.raises(ValidationError, match="must start after"):
            services.activate(v2, D(2025, 6, 1))
        assert v2.number == 2 and v2.status == "draft"


def test_the_hash_is_of_the_content_not_of_the_formatting(db: None) -> None:
    text = '{"b": 0.30, "a": [1, 2]}'
    reordered = '{\n  "a": [1,2],\n  "b": 0.30\n}'
    assert services.config_hash(text) == services.config_hash(reordered)
    assert services.config_hash(text) != services.config_hash(
        '{"b": 0.3, "a": [1, 2]}'
    )  # 0.30 vs 0.3 differ in text only


def test_templates_theory_and_lab_are_valid_and_unknown_ones_refused(db: None) -> None:
    college = make_college("a")
    with college_context(college.id):
        theory = services.create_from_template("vasavi_theory")
        lab = services.create_from_template("vasavi_lab")
        assert services.parse_config(theory.config_text).tools["SEE"].behaviour == "question_wise"
        lab_config = services.parse_config(lab.config_text)
        assert (
            lab_config.tools["LAB"].behaviour == "single_total" and lab_config.final.indirect == 0
        )
        with pytest.raises(ValidationError, match="Unknown template"):
            services.create_from_template("nope")


# A6 --------------------------------------------------------
def _method(name: str):  # type: ignore[no-untyped-def]
    version = services.create_from_template("vasavi_theory", name)
    services.activate(version, D(2025, 1, 1))
    return version.method


def test_a6_the_most_specific_level_wins(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        college_method, programme_method, course_method = (_method(n) for n in ("C", "P", "K"))
        services.assign_method("college", college_method)
        assert services.method_for_offering(s.offering)[1].method == college_method  # type: ignore[index]
        services.assign_method("programme", programme_method, s.programme.pk)
        assert services.method_for_offering(s.offering)[1].method == programme_method  # type: ignore[index]
        services.assign_method("course", course_method, s.course.pk)
        assert services.method_for_offering(s.offering)[1].method == course_method  # type: ignore[index]


def test_a6_a_locked_university_value_cannot_be_changed_by_a_college(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        university = University.objects.create(name="Affiliating University", short_name="AU")
        mandated, own = _method("University rules"), _method("College own")
        services.assign_method("university", mandated, university.pk, locked=True)
        with pytest.raises(ValidationError, match="locked its method"):
            services.assign_method("college", own)
        with pytest.raises(ValidationError, match="locked"):
            services.assign_method("programme", own, s.programme.pk)
        with pytest.raises(ValidationError, match="locked"):
            services.assign_method("course", own, s.course.pk)
        assert services.method_for_offering(s.offering)[1].method == mandated  # type: ignore[index]


def test_a6_a_lock_set_later_still_wins_over_an_existing_specific_choice(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        wide, narrow = _method("Wide"), _method("Narrow")
        services.assign_method("course", narrow, s.course.pk)
        assert services.method_for_offering(s.offering)[1].method == narrow  # type: ignore[index]
        services.assign_method("college", wide, locked=True)  # a lock does not check narrower ones
        assert services.method_for_offering(s.offering)[1].method == wide  # type: ignore[index]


def test_a6_a_lock_covers_only_its_own_dates(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        wide, own = _method("Wide"), _method("Own")
        services.assign_method("college", wide, valid_to=D(2025, 12, 31), locked=True)
        services.assign_method(
            "course", own, s.course.pk, valid_from=D(2026, 1, 1)
        )  # after the lock
        assert services.method_for_offering(s.offering, on=D(2026, 2, 1))[1].method == own  # type: ignore[index]
        with pytest.raises(ValidationError):
            services.assign_method("course", own, s.course.pk, valid_from=D(2025, 6, 1))


def test_no_assignment_means_no_method(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        assert services.method_for_offering(s.offering) is None


# A7 --------------------------------------------------------
def test_a7_errors_name_the_field_and_the_problem(db: None) -> None:
    college = make_college("a")
    with college_context(college.id):
        draft = services.create_from_template("vasavi_theory")
        bad = _tweak(draft, direct={"INTERNAL": 0.30, "ASSIGN": 0.05, "QUIZ": 0.05, "SEE": 0.80})
        with pytest.raises(ValidationError) as caught:
            services.update_draft(draft, bad)
        assert any(m.startswith("direct:") and "sum to 1" in m for m in caught.value.messages)
        with pytest.raises(ValidationError) as caught:
            services.update_draft(draft, "{not json")
        assert "not valid JSON" in caught.value.messages[0]
        draft.refresh_from_db()
        assert "0.60" in draft.config_text  # the bad edit was not saved


# the screens -----------------------------------------------
def _login(username: str) -> Client:
    client = Client()
    assert (
        client.post("/accounts/login/", {"username": username, "password": PASSWORD}).status_code
        == 302
    )
    return client


def _iqac(college):  # type: ignore[no-untyped-def]
    user = make_user(college, "a.iqac")
    with college_context(college.id):
        assign_role(user, Role.IQAC)
    return _login("a.iqac")


def test_m3_m4_create_edit_activate_then_the_active_version_is_locked(committed_db: None) -> None:
    college = make_college("a")
    client = _iqac(college)
    created = client.post("/methods/", {"template": "vasavi_theory", "name": "Vasavi R22"})
    assert created.status_code == 302
    page = client.get(created["Location"]).content.decode()
    assert "Save draft" in page and "Version" not in "" and "draft" in page.lower()
    with college_context(college.id):
        version = MethodVersion.objects.get()
    text = version.config_text.replace('"pass_pct": 60', '"pass_pct": 55')  # the M3 change
    bad = client.post(
        created["Location"],
        {"action": "save", "config_text": text.replace('"SEE"', '"SEE", "x"', 1)},
    )
    assert bad.status_code == 200  # invalid JSON stays on the page with a message
    ok = client.post(created["Location"], {"action": "save", "config_text": text})
    assert ok.status_code == 302
    activated = client.post(
        created["Location"],
        {"action": "activate", "config_text": text, "effective_from": "2026-06-01"},
    )
    assert activated.status_code == 302
    locked = client.get(created["Location"]).content.decode()
    assert "cannot be edited" in locked and "Create a new draft from this version" in locked
    assert "Save draft" not in locked
    blocked = client.post(created["Location"], {"action": "save", "config_text": "{}"}, follow=True)
    assert b"cannot be edited" in blocked.content
    copy = client.post(created["Location"], {"action": "copy"})
    assert copy.status_code == 302 and copy["Location"] != created["Location"]
    with college_context(college.id):
        assert sorted(MethodVersion.objects.values_list("number", flat=True)) == [1, 2]
        assert '"pass_pct": 55' in MethodVersion.objects.get(number=2).config_text


def test_activation_without_a_valid_date_is_refused_politely(committed_db: None) -> None:
    college = make_college("a")
    client = _iqac(college)
    created = client.post("/methods/", {"template": "vasavi_lab"})
    with college_context(college.id):
        text = MethodVersion.objects.get().config_text
    response = client.post(
        created["Location"],
        {"action": "activate", "config_text": text, "effective_from": ""},
        follow=True,
    )
    assert b"valid start date" in response.content
    with college_context(college.id):
        assert MethodVersion.objects.get().status == "draft"


def test_only_those_who_may_edit_methods_reach_the_screens(committed_db: None) -> None:
    college = make_college("a")
    make_user(college, "a.lecturer")
    assert _login("a.lecturer").get("/methods/").status_code == 403
    assert Client().get("/methods/").status_code == 302
    other = make_college("b")
    client_b = _iqac(other)
    with college_context(college.id):
        version = services.create_from_template("vasavi_lab")
    assert client_b.get(f"/methods/version/{version.pk}/").status_code == 404
