"""A1 to A4, A9 and the grid screens for marks."""

from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client

from apps.accounts.tests.helpers import PASSWORD
from apps.marks import services
from apps.marks.models import MarkCell, MarkChange, MarkSheetRow
from apps.tenancy.services import college_context

from .helpers import make_env

pytestmark = [pytest.mark.integration]

S = MarkCell.State
D = Decimal


def _part(assessment, code):  # type: ignore[no-untyped-def]
    return assessment.parts.get(code=code)


def _save(env, user, enrolment, code, text, **kwargs):  # type: ignore[no-untyped-def]
    part = _part(env.internal, code)
    state, value = services.parse_mark_text(text, part.max)
    row = services.get_row(enrolment, env.internal, create=True)
    return services.save_cell(row, part, state, value, user, **kwargs)


def test_a1_zero_blank_absent_and_not_attempted_stay_distinct(db: None) -> None:
    env = make_env()
    e = env.enrolments_a
    with college_context(env.college.id):
        for enrolment, text in zip(e[:4], ["0", "", "AB", "-"], strict=True):
            _save(env, env.lecturer_a, enrolment, "1a", text)
        states = {
            c.row.enrolment_id: (c.state, c.value) for c in MarkCell.objects.select_related("row")
        }
        assert states[e[0].pk] == (S.VALUE, D("0.00"))
        assert states[e[1].pk] == (S.BLANK, None)
        assert states[e[2].pk] == (S.ABSENT, None)
        assert states[e[3].pk] == (S.NOT_ATTEMPTED, None)
        assert [services.cell_text(c) for c in MarkCell.objects.order_by("created_at")] == [
            "0",
            "",
            "AB",
            "-",
        ]
        # the database also refuses a state that contradicts its value
        with pytest.raises(Exception), transaction.atomic():  # noqa: B017,PT011
            MarkCell.objects.filter(state="value").update(value=None)


def test_a1_the_engine_adapter_maps_states_as_configured(db: None) -> None:
    env = make_env()
    e = env.enrolments_a
    with college_context(env.college.id):
        for enrolment, text in zip(e, ["3", "0", "AB", "-", "WH"], strict=True):
            _save(env, env.lecturer_a, enrolment, "1a", text)
        default = services.engine_assessment(env.internal)
        kinds = {sid: cells["1a"].state.value for sid, cells in default.marks.items()}
        by_student = {str(x.student_id): x for x in e}
        assert (
            kinds[str(e[0].student_id)] == "entered"
            and default.marks[str(e[0].student_id)]["1a"].value == 3
        )
        assert default.marks[str(e[1].student_id)]["1a"].value == 0  # a real zero
        assert kinds[str(e[2].student_id)] == "absent"
        assert kinds[str(e[3].student_id)] == "blank" and kinds[str(e[4].student_id)] == "blank"
        configured = services.engine_assessment(env.internal, state_map={"withheld": "absent"})
        assert configured.marks[str(e[4].student_id)]["1a"].state.value == "absent"
        assert len(by_student) == 5
        assert "1b" in default.marks[str(e[0].student_id)]  # an unwritten part is blank, present


def test_a_student_with_every_cell_absent_is_absent_for_the_whole_assessment(db: None) -> None:
    env = make_env()
    with college_context(env.college.id):
        for code in ("1a", "1b"):
            _save(env, env.lecturer_a, env.enrolments_a[0], code, "AB")
        _save(env, env.lecturer_a, env.enrolments_a[1], "1a", "AB")
        _save(env, env.lecturer_a, env.enrolments_a[1], "1b", "2")
        data = services.engine_assessment(env.internal)
        assert data.absent_whole == frozenset({str(env.enrolments_a[0].student_id)})


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("5", "above the maximum 4"),
        ("-1", "below 0"),
        ("abc", "not a mark"),
        ("1.234", "more than two decimal"),
        ("NaN", "not a mark"),
        ("1e2", "above the maximum"),
    ],
)
def test_a2_invalid_text_is_rejected_with_a_plain_message(text: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        services.parse_mark_text(text, D(4))


def test_a2_service_level_validation(db: None) -> None:
    env = make_env()
    with college_context(env.college.id):
        part = _part(env.internal, "1a")
        row = services.get_row(env.enrolments_a[0], env.internal, create=True)
        for state, value in (
            ("value", D("5")),
            ("value", None),
            ("absent", D("1")),
            ("bogus", None),
        ):
            with pytest.raises(ValidationError):
                services.save_cell(row, part, state, value, env.lecturer_a)
        other = _part(env.see, "1")
        with pytest.raises(ValidationError, match="not on this assessment"):
            services.save_cell(row, other, "value", D("1"), env.lecturer_a)
        assert MarkCell.objects.count() == 0


def test_a3_a_second_save_of_an_old_version_is_refused_naming_who_changed_it(db: None) -> None:
    env = make_env()
    e = env.enrolments_a[0]
    with college_context(env.college.id):
        first = _save(env, env.lecturer_a, e, "1a", "2", expected_version=0)
        assert first.row_version == 1
        mine = _save(env, env.lecturer_a, e, "1a", "3", expected_version=1)
        assert mine.row_version == 2
        with pytest.raises(ValidationError, match="changed by a.lecturer_a. Reload") as caught:
            _save(env, env.lecturer_a, e, "1a", "4", expected_version=1)  # saw version 1
        assert isinstance(caught.value, services.StaleCell)
        assert MarkCell.objects.get().value == D("3.00")
        with pytest.raises(services.StaleCell):
            _save(
                env, env.lecturer_a, env.enrolments_a[1], "1a", "1", expected_version=5
            )  # no such cell


def test_a3_saving_the_same_value_again_changes_nothing(db: None) -> None:
    env = make_env()
    e = env.enrolments_a[0]
    with college_context(env.college.id):
        _save(env, env.lecturer_a, e, "1a", "2")
        again = _save(env, env.lecturer_a, e, "1a", "2")
        assert again.row_version == 1 and MarkChange.objects.count() == 1


def test_a4_every_edit_writes_who_when_old_and_new(db: None) -> None:
    env = make_env()
    e = env.enrolments_a[0]
    with college_context(env.college.id):
        cell = _save(env, env.lecturer_a, e, "1a", "2")
        _save(env, env.lecturer_a, e, "1a", "AB")
        _save(env, env.lecturer_a, e, "1a", "3.5")
        changes = [
            (c.old_state, c.old_value, c.new_state, c.new_value, c.by_id)
            for c in services.history(cell)
        ]
        who = env.lecturer_a.pk
        assert changes == [
            ("", None, "value", D("2.00"), who),
            ("value", D("2.00"), "absent", None, who),
            ("absent", None, "value", D("3.50"), who),
        ]
        assert all(c.at is not None for c in services.history(cell))


def test_a4_after_submission_a_reason_is_required(db: None) -> None:
    env = make_env()
    e = env.enrolments_a[0]
    with college_context(env.college.id):
        cell = _save(env, env.lecturer_a, e, "1a", "2")
        row = MarkSheetRow.objects.get()
        services.submit_row(row, env.lecturer_a)
        with pytest.raises(ValidationError, match="reason is required"):
            _save(env, env.lecturer_a, e, "1a", "3")
        _save(env, env.lecturer_a, e, "1a", "3", reason="re-evaluation")
        assert services.history(cell).last().reason == "re-evaluation"  # type: ignore[union-attr]


def test_a4_history_cannot_be_changed_or_deleted_even_by_the_app(db: None) -> None:
    env = make_env()
    with college_context(env.college.id):
        _save(env, env.lecturer_a, env.enrolments_a[0], "1a", "2")
        for statement in (
            "UPDATE marks_markchange SET reason = 'x'",
            "DELETE FROM marks_markchange",
        ):
            with (
                pytest.raises(DatabaseError, match="permission denied"),
                transaction.atomic(),
                connection.cursor() as cursor,
            ):
                cursor.execute(statement)
        assert MarkChange.objects.count() == 1


def test_locked_assessments_refuse_changes(db: None) -> None:
    env = make_env()
    with college_context(env.college.id):
        env.internal.status = "locked"
        env.internal.save()
        with pytest.raises(ValidationError, match="locked"):
            _save(env, env.lecturer_a, env.enrolments_a[0], "1a", "2")


# A9 --------------------------------------------------------
def test_a9_lecturer_a_cannot_read_or_write_section_b(db: None) -> None:
    env = make_env()
    with college_context(env.college.id):
        assert services.can_write(env.lecturer_a, env.internal, env.s.section_a)
        assert not services.can_write(env.lecturer_a, env.internal, env.s.section_b)
        assert not services.can_read(env.lecturer_a, env.internal, env.s.section_b)
        with pytest.raises(PermissionDenied):
            _save(env, env.lecturer_a, env.enrolments_b[0], "1a", "2")
        assert MarkCell.objects.count() == 0


def test_a9_exam_branch_writes_only_the_see_and_the_auditor_only_reads(db: None) -> None:
    env = make_env()
    with college_context(env.college.id):
        for section in (env.s.section_a, env.s.section_b):
            assert services.can_write(env.exam, env.see, section)
            assert not services.can_write(env.exam, env.internal, section)
            assert not services.can_read(env.exam, env.internal, section)
            assert services.can_read(env.auditor, env.internal, section)
            assert not services.can_write(env.auditor, env.internal, section)
            assert not services.can_write(env.auditor, env.see, section)
        with pytest.raises(PermissionDenied):
            _save(env, env.auditor, env.enrolments_a[0], "1a", "2")
        with pytest.raises(PermissionDenied):
            _save(env, env.exam, env.enrolments_a[0], "1a", "2")


def test_a9_a_department_head_does_not_get_to_enter_marks(db: None) -> None:
    from apps.accounts.models import Role, ScopeType
    from apps.accounts.services import assign_role
    from apps.accounts.tests.helpers import make_user

    env = make_env()
    hod = make_user(env.college, "a.hod")
    with college_context(env.college.id):
        assign_role(hod, Role.HOD, ScopeType.DEPARTMENT, env.s.department.pk)
        assert not services.can_write(hod, env.internal, env.s.section_a)
        assert services.can_read(
            hod, env.internal, env.s.section_a
        )  # reports.view over its sections


# the grid screen -------------------------------------------
def _login(username: str) -> Client:
    client = Client()
    assert (
        client.post("/accounts/login/", {"username": username, "password": PASSWORD}).status_code
        == 302
    )
    return client


def test_the_grid_saves_marks_shows_errors_and_refuses_stale_edits(committed_db: None) -> None:
    env = make_env()
    e0, e1 = env.enrolments_a[0], env.enrolments_a[1]
    url = f"/marks/{env.internal.pk}/{env.s.section_a.pk}/"
    one, two = _login("a.lecturer_a"), _login("a.lecturer_a")
    page = one.get(url).content.decode()
    assert f'name="cell:{e0.pk}:1a"' in page
    posted = {
        f"cell:{e0.pk}:1a": "3", f"old:{e0.pk}:1a": "", f"ver:{e0.pk}:1a": "0",
        f"cell:{e1.pk}:1a": "9", f"old:{e1.pk}:1a": "", f"ver:{e1.pk}:1a": "0",
    }  # fmt: skip
    bad = one.post(url, posted)
    assert bad.status_code == 200 and b"above the maximum 4" in bad.content
    with college_context(env.college.id):
        assert MarkCell.objects.get().value == D(
            "3.00"
        )  # the valid cell saved, the bad one did not
    second = {
        f"cell:{e0.pk}:1a": "3", f"old:{e0.pk}:1a": "3", f"ver:{e0.pk}:1a": "1",
        f"cell:{e1.pk}:1a": "2", f"old:{e1.pk}:1a": "", f"ver:{e1.pk}:1a": "0",
    }  # fmt: skip
    ok = one.post(url, second)
    assert ok.status_code == 302
    # a second browser still holds version 1 of the first cell and tries to change it
    stale = two.post(url, {f"cell:{e0.pk}:1a": "4", f"old:{e0.pk}:1a": "3", f"ver:{e0.pk}:1a": "0"})
    assert stale.status_code == 200 and b"Reload and try again" in stale.content


def test_the_grid_and_history_follow_the_permissions(committed_db: None) -> None:
    env = make_env()
    with college_context(env.college.id):
        cell = _save(env, env.lecturer_a, env.enrolments_a[0], "1a", "2")
    a_url = f"/marks/{env.internal.pk}/{env.s.section_a.pk}/"
    b_url = f"/marks/{env.internal.pk}/{env.s.section_b.pk}/"
    lecturer = _login("a.lecturer_a")
    assert lecturer.get(a_url).status_code == 200 and lecturer.get(b_url).status_code == 403
    assert lecturer.get(f"/marks/cell/{cell.pk}/history/").status_code == 200
    assert b"value 2.00" in lecturer.get(f"/marks/cell/{cell.pk}/history/").content
    auditor = _login("a.auditor")
    read_only = auditor.get(a_url)
    assert read_only.status_code == 200 and b'name="cell:' not in read_only.content
    assert auditor.post(a_url, {}).status_code == 403
    assert _login("a.lecturer_b").get(f"/marks/cell/{cell.pk}/history/").status_code == 403
    assert Client().get(a_url).status_code == 302


def test_another_colleges_marks_are_not_found(committed_db: None) -> None:
    make_env("a")
    other = make_env("b")
    url = f"/marks/{other.internal.pk}/{other.s.section_a.pk}/"
    assert _login("a.lecturer_a").get(url).status_code == 404
