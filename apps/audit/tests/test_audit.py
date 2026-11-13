"""A7: login and role events are logged; the log cannot be updated or deleted."""

import threading

import pytest
from django.db import DatabaseError, connection, connections, transaction
from django.test import Client

from apps.accounts.models import Role, ScopeType
from apps.accounts.services import assign_role, revoke_role
from apps.accounts.tests.helpers import PASSWORD, make_college, make_user
from apps.audit import services as audit
from apps.audit.models import AuditEvent
from apps.tenancy.services import college_context

pytestmark = [pytest.mark.integration]


def _actions() -> list[str]:
    return list(AuditEvent.objects.order_by("seq").values_list("action", flat=True))


def test_a7_login_logout_and_role_changes_are_logged(committed_db: None) -> None:
    college = make_college("a")
    admin = make_user(college, "a.admin")
    lecturer = make_user(college, "a.lecturer")
    with college_context(college.id):
        assignment = assign_role(
            lecturer, Role.LECTURER, ScopeType.SECTION, admin.id, actor=admin, reason="new term"
        )
        revoke_role(assignment, actor=admin)
    client = Client()
    client.post("/accounts/login/", {"username": "a.lecturer", "password": PASSWORD})
    client.post("/accounts/logout/")
    with college_context(college.id):
        assert _actions() == ["role.assigned", "role.revoked", "auth.login", "auth.logout"]
        assigned = AuditEvent.objects.get(action="role.assigned")
        assert assigned.actor_id == admin.id
        assert assigned.reason == "new term"
        assert assigned.after["role"] == "lecturer"
        login = AuditEvent.objects.get(action="auth.login")
        assert login.actor_id == lecturer.id
        assert login.ip == "127.0.0.1"
        assert audit.verify_chain()


def test_a7_app_role_cannot_update_delete_or_truncate(committed_db: None) -> None:
    college = make_college("a")
    with college_context(college.id):
        audit.record("test.event", "thing", entity_id="1")
        for statement in (
            "UPDATE audit_auditevent SET reason = 'edited'",
            "DELETE FROM audit_auditevent",
            "TRUNCATE audit_auditevent",
        ):
            with (
                pytest.raises(DatabaseError, match="permission denied"),
                transaction.atomic(),
                connection.cursor() as cursor,
            ):
                cursor.execute(statement)
        assert AuditEvent.objects.count() == 1


def test_a7_even_the_owner_is_blocked_by_the_trigger(committed_db: None) -> None:
    college = make_college("a")
    with college_context(college.id):
        audit.record("test.event", "thing")
    owner = connections["owner"]
    with owner.cursor() as cursor, transaction.atomic(using="owner"):
        cursor.execute("SELECT set_config('app.college_id', %s, true)", [str(college.id)])
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic(using="owner"):
            cursor.execute("UPDATE audit_auditevent SET reason = 'edited'")
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic(using="owner"):
            cursor.execute("DELETE FROM audit_auditevent")


def test_hash_chain_links_rows_and_detects_tampering(committed_db: None) -> None:
    college = make_college("a")
    with college_context(college.id):
        first = audit.record("a", "thing", after={"n": 1})
        second = audit.record("b", "thing", before={"n": 1}, after={"n": 2})
        third = audit.record("c", "thing")
        assert first.hash_prev == ""
        assert second.hash_prev == first.hash
        assert third.hash_prev == second.hash
        assert [e.seq for e in (first, second, third)] == [1, 2, 3]
        assert audit.verify_chain()

    # Tamper as the owner with the trigger switched off, the way an attacker with DB access would.
    owner = connections["owner"]
    with owner.cursor() as cursor, transaction.atomic(using="owner"):
        cursor.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER audit_append_only")
        cursor.execute("SELECT set_config('app.college_id', %s, true)", [str(college.id)])
        cursor.execute("UPDATE audit_auditevent SET reason = 'forged' WHERE seq = 2")
        cursor.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER audit_append_only")
    with college_context(college.id):
        assert not audit.verify_chain()


def test_deleting_a_middle_row_breaks_the_chain(committed_db: None) -> None:
    college = make_college("a")
    with college_context(college.id):
        for name in ("a", "b", "c"):
            audit.record(name, "thing")
    owner = connections["owner"]
    with owner.cursor() as cursor, transaction.atomic(using="owner"):
        cursor.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER audit_append_only")
        cursor.execute("SELECT set_config('app.college_id', %s, true)", [str(college.id)])
        cursor.execute("DELETE FROM audit_auditevent WHERE seq = 2")
        cursor.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER audit_append_only")
    with college_context(college.id):
        assert not audit.verify_chain()


def test_each_college_has_its_own_chain_and_cannot_read_the_other(committed_db: None) -> None:
    a, b = make_college("a"), make_college("b")
    with college_context(a.id):
        audit.record("a.one", "thing")
        audit.record("a.two", "thing")
    with college_context(b.id):
        event = audit.record("b.one", "thing")
        assert (event.seq, event.hash_prev) == (1, "")
        assert _actions() == ["b.one"]
        assert audit.verify_chain()
    with college_context(None):
        assert AuditEvent.objects.count() == 0


def test_record_needs_a_college_and_a_transaction(committed_db: None) -> None:
    with pytest.raises(RuntimeError, match="No current college"):
        audit.record("x", "thing")
    college = make_college("a")
    from apps.tenancy.context import set_current_college_id

    set_current_college_id(college.id)
    with pytest.raises(RuntimeError, match="transaction"):
        audit.record("x", "thing")


def test_concurrent_writers_keep_the_chain_intact(committed_db: None) -> None:
    college = make_college("a")
    errors: list[BaseException] = []

    def write() -> None:
        try:
            for _ in range(5):
                with college_context(college.id):
                    audit.record("race", "thing")
        except BaseException as error:  # noqa: BLE001 - reported to the main thread
            errors.append(error)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=write) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    with college_context(college.id):
        assert AuditEvent.objects.count() == 20
        assert audit.verify_chain()
