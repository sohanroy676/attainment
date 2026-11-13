import uuid
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client

from apps.accounts.management.commands.seed_demo import NAMESPACE
from apps.accounts.models import RoleAssignment, User
from apps.audit.models import AuditEvent
from apps.tenancy.models import College
from apps.tenancy.services import college_context

pytestmark = [pytest.mark.integration]

PASSWORD = "demo password 2026 x"


def all_college_ids() -> list[uuid.UUID]:
    return [uuid.uuid5(NAMESPACE, f"college:{code}") for code in ("a", "b")]


def _seed(*args: str) -> str:
    out = StringIO()
    call_command("seed_demo", *args, stdout=out)
    return out.getvalue()


def test_seed_creates_two_isolated_colleges_with_one_account_per_role(committed_db: None) -> None:
    _seed("--password", PASSWORD)
    for college_id in all_college_ids():
        with college_context(college_id):
            assert College.objects.count() == 1
            assert User.objects.count() == 8
            assert RoleAssignment.objects.count() == 8
            usernames = set(User.objects.values_list("username", flat=True))
            assert len({name.split(".")[0] for name in usernames}) == 1  # only its own users
            assert AuditEvent.objects.filter(action="role.assigned").count() == 8


def test_seed_is_idempotent(committed_db: None) -> None:
    _seed("--password", PASSWORD)
    assert "nothing changed" in _seed("--password", PASSWORD)
    for college_id in all_college_ids():
        with college_context(college_id):
            assert User.objects.count() == 8


def test_demo_accounts_can_log_in_and_see_only_their_college(committed_db: None) -> None:
    _seed("--password", PASSWORD)
    for username in ("a.lecturer", "b.principal"):
        client = Client()
        response = client.post("/accounts/login/", {"username": username, "password": PASSWORD})
        assert response.status_code == 302
        assert username.encode() in client.get("/").content


def test_seed_prints_a_generated_password_that_works(committed_db: None) -> None:
    output = _seed()
    password = output.split("Password for the new accounts: ")[1].strip()
    response = Client().post("/accounts/login/", {"username": "a.admin", "password": password})
    assert response.status_code == 302
