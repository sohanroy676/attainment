"""v0.11.0: upload abuse, audit verification command, rate limits."""

import io
import zipfile

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections, transaction
from django.test import Client, override_settings

from apps.accounts.models import Role
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import PASSWORD, make_college, make_user
from apps.audit import services as audit
from apps.imports.parsers import MAX_UNPACKED_BYTES, UnreadableFile, parse_roster
from apps.tenancy.services import college_context

pytestmark = [pytest.mark.integration]


# A3: upload abuse ---------------------------------------------------------------------------
def _zip(entries: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return out.getvalue()


def test_a3_a_decompression_bomb_is_refused_before_anything_is_unpacked() -> None:
    bomb = _zip({"xl/worksheets/sheet1.xml": b"0" * (MAX_UNPACKED_BYTES + 1)})
    assert len(bomb) < 1024 * 1024  # small on disk, huge once unpacked
    with pytest.raises(UnreadableFile, match="unsafe size"):
        parse_roster("roster.xlsx", bomb)


def test_a3_a_zip_with_thousands_of_parts_is_refused() -> None:
    many = _zip({f"part{i}.xml": b"x" for i in range(1500)})
    with pytest.raises(UnreadableFile, match="unsafe size"):
        parse_roster("roster.xlsx", many)


def test_a3_a_broken_zip_with_the_right_first_bytes_is_refused() -> None:
    with pytest.raises(UnreadableFile, match="not a real Excel"):
        parse_roster("roster.xlsx", b"PK\x03\x04" + b"garbage" * 100)


# A6: the audit verify command ----------------------------------------------------------------
def _forge(college_id) -> None:  # type: ignore[no-untyped-def]
    owner = connections["owner"]
    with owner.cursor() as cursor, transaction.atomic(using="owner"):
        cursor.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER audit_append_only")
        cursor.execute("SELECT set_config('app.college_id', %s, true)", [str(college_id)])
        cursor.execute("UPDATE audit_auditevent SET reason = 'forged' WHERE seq = 2")
        cursor.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER audit_append_only")


def test_a6_the_verify_command_passes_then_detects_a_tampered_row(committed_db: None) -> None:
    a, b = make_college("a"), make_college("b")
    for college in (a, b):
        with college_context(college.id):
            for name in ("one", "two", "three"):
                audit.record(name, "thing")
    out = io.StringIO()
    call_command("verify_audit", "--college", str(a.id), "--college", str(b.id), stdout=out)
    assert out.getvalue().count("OK") == 2
    _forge(a.id)
    out = io.StringIO()
    with pytest.raises(CommandError, match="broken for 1 college"):
        call_command("verify_audit", "--all", stdout=out)
    text = out.getvalue()
    assert f"{a.id}: BROKEN" in text and f"{b.id}: OK" in text


def test_the_verify_command_needs_to_be_told_which_colleges(db: None) -> None:
    with pytest.raises(CommandError, match="--all or at least one"):
        call_command("verify_audit")
    with pytest.raises(CommandError, match="UUID"):
        call_command("verify_audit", "--college", "not-an-id")


# A2: rate limits and lockout -----------------------------------------------------------------
@override_settings(RATE_LIMITS={"pdf": (20, 60), "upload": (30, 60), "export": (2, 3600)})
def test_a2_the_full_export_is_rate_limited_per_user(committed_db: None) -> None:
    from django.core.cache import cache

    cache.clear()
    college = make_college("a")
    admin = make_user(college, "a.admin")
    other = make_user(college, "a.admin2")
    with college_context(college.id):
        assign_role(admin, Role.COLLEGE_ADMIN)
        assign_role(other, Role.COLLEGE_ADMIN)
    client = Client()
    client.post("/accounts/login/", {"username": "a.admin", "password": PASSWORD})
    assert [client.get("/reports/export.json").status_code for _ in range(3)] == [200, 200, 429]
    assert client.get("/reports/export.json")["Retry-After"] == "3600"
    second = Client()
    second.post("/accounts/login/", {"username": "a.admin2", "password": PASSWORD})
    assert second.get("/reports/export.json").status_code == 200  # another user has their own count
    cache.clear()


@override_settings(RATE_LIMITS={"pdf": (20, 60), "upload": (2, 60), "export": (5, 3600)})
def test_a2_uploads_are_rate_limited(committed_db: None) -> None:
    from django.core.cache import cache

    from apps.workflow.tests.helpers import make_wf_env

    cache.clear()
    w = make_wf_env()
    admin = make_user(w.college, "a.admin")
    with college_context(w.college.id):
        assign_role(admin, Role.COLLEGE_ADMIN)
    client = Client()
    client.post("/accounts/login/", {"username": "a.admin", "password": PASSWORD})
    url = f"/imports/roster/{w.env.s.section_a.pk}/"
    codes = [client.post(url, {}).status_code for _ in range(4)]
    assert codes[-1] == 429 and 429 not in codes[:2], codes
    cache.clear()


def test_a2_five_wrong_passwords_lock_the_account(committed_db: None) -> None:
    college = make_college("a")
    make_user(college, "a.lecturer")
    client = Client()
    for _ in range(5):
        client.post("/accounts/login/", {"username": "a.lecturer", "password": "wrong-password-1"})
    locked = client.post("/accounts/login/", {"username": "a.lecturer", "password": PASSWORD})
    assert locked.status_code in (403, 429) and b"locked" in locked.content.lower()


# the first administrator of a real college ---------------------------------------------------
def test_create_college_makes_a_college_and_an_admin_who_can_log_in(committed_db: None) -> None:
    out = io.StringIO()
    call_command("create_college", "Example College", "example", "first.admin", stdout=out)
    text = out.getvalue()
    password = text.split("Password for first.admin: ")[1].splitlines()[0]
    client = Client()
    assert (
        client.post(
            "/accounts/login/", {"username": "first.admin", "password": password}
        ).status_code
        == 302
    )
    assert client.get("/privacy/retention/").status_code == 200  # a college admin right
    with pytest.raises(CommandError, match="not created"):
        call_command("create_college", "Other", "example", "second.admin", stdout=io.StringIO())
