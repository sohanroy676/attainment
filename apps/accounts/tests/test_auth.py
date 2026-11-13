"""A5, A8, A9 and the manual flows M2, M4, M5 as automatic tests."""

import importlib
import re
import sys
import uuid

import pytest
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import connection
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.tenancy.services import college_context, set_auth_identity

from .helpers import PASSWORD, make_college, make_user

pytestmark = [pytest.mark.integration]

LOGIN = "/accounts/login/"


def _login(client: Client, username: str, password: str = PASSWORD) -> None:
    response = client.post(LOGIN, {"username": username, "password": password})
    assert response.status_code == 302, response.content.decode()[:500]


def _setting(name: str) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [name])
        return cursor.fetchone()[0]  # type: ignore[index]


def test_login_logout_and_home_page(committed_db: None) -> None:
    college = make_college("a")
    make_user(college, "a.lecturer", full_name="Asha Rao")
    client = Client()
    assert client.get("/").status_code == 302  # not logged in
    _login(client, "a.lecturer")
    page = client.get("/")
    assert page.status_code == 200
    assert b"Asha Rao" in page.content
    assert client.post("/accounts/logout/").status_code == 302
    assert client.get("/").status_code == 302


def test_wrong_password_shows_a_plain_message_and_does_not_reveal_which_part(
    committed_db: None,
) -> None:
    make_user(make_college("a"), "a.lecturer")
    wrong_password = Client().post(LOGIN, {"username": "a.lecturer", "password": "nope-nope-nope"})
    unknown_user = Client().post(LOGIN, {"username": "nobody", "password": "nope-nope-nope"})
    assert wrong_password.status_code == unknown_user.status_code == 200
    message = b"That username and password do not match."
    assert message in wrong_password.content
    assert message in unknown_user.content


def test_inactive_user_cannot_log_in(committed_db: None) -> None:
    make_user(make_college("a"), "a.gone", is_active=False)
    response = Client().post(LOGIN, {"username": "a.gone", "password": PASSWORD})
    assert response.status_code == 200


def test_a8_password_of_nine_characters_is_rejected(db: None) -> None:
    with pytest.raises(ValidationError):
        validate_password("Abcdef1!x")
    validate_password("Abcdef1!xy")  # ten characters


def test_a8_common_and_numeric_passwords_are_rejected(db: None) -> None:
    for weak in ("password1234", "1234567890123"):
        with pytest.raises(ValidationError):
            validate_password(weak)


def test_a8_account_locks_after_repeated_wrong_passwords(committed_db: None) -> None:
    make_user(make_college("a"), "a.lecturer")
    client = Client()
    for _ in range(5):
        client.post(LOGIN, {"username": "a.lecturer", "password": "wrong-wrong-wrong"})
    locked = client.post(LOGIN, {"username": "a.lecturer", "password": PASSWORD})
    assert locked.status_code == 429
    assert b"Too many attempts" in locked.content
    # another account is not affected
    make_user(make_college("b"), "b.lecturer")
    _login(Client(), "b.lecturer")


def test_m5_idle_session_returns_to_login(committed_db: None) -> None:
    make_user(make_college("a"), "a.lecturer")
    client = Client()
    _login(client, "a.lecturer")
    assert client.get("/").status_code == 200
    Session.objects.update(expire_date=timezone.now() - timezone.timedelta(minutes=1))
    response = client.get("/")
    assert response.status_code == 302
    assert response["Location"].startswith(LOGIN)


def test_idle_timeout_is_thirty_minutes_and_slides(settings: object) -> None:
    assert settings.SESSION_COOKIE_AGE == 1800  # type: ignore[attr-defined]
    assert settings.SESSION_SAVE_EVERY_REQUEST is True  # type: ignore[attr-defined]


def test_m4_password_reset_by_email(committed_db: None) -> None:
    make_user(make_college("a"), "a.lecturer", email="lecturer@example.org")
    client = Client()
    response = client.post("/accounts/password-reset/", {"email": "Lecturer@Example.org"})
    assert response.status_code == 302
    assert len(mail.outbox) == 1
    link = re.search(r"http://testserver(/accounts/password-reset/\S+)", mail.outbox[0].body)
    assert link
    page = client.get(link.group(1), follow=True)
    assert page.status_code == 200
    set_url = page.redirect_chain[-1][0]
    weak = client.post(set_url, {"new_password1": "short1!", "new_password2": "short1!"})
    assert weak.status_code == 200  # form shown again, nothing changed
    new_password = "a brand new password 77"
    done = client.post(set_url, {"new_password1": new_password, "new_password2": new_password})
    assert done.status_code == 302
    _login(Client(), "a.lecturer", new_password)
    old = Client().post(LOGIN, {"username": "a.lecturer", "password": PASSWORD})
    assert old.status_code == 200  # old password refused
    # the link works once
    again = client.get(link.group(1), follow=True)
    assert b"not valid" in again.content


def test_password_reset_for_unknown_email_sends_nothing_and_says_the_same(
    committed_db: None,
) -> None:
    make_user(make_college("a"), "a.lecturer", email="lecturer@example.org")
    response = Client().post("/accounts/password-reset/", {"email": "nobody@example.org"})
    assert response.status_code == 302
    assert mail.outbox == []


def test_reset_link_with_a_forged_user_id_is_invalid(committed_db: None) -> None:
    make_user(make_college("a"), "a.lecturer", email="lecturer@example.org")
    forged = f"/accounts/password-reset/{uuid.uuid4().hex}/set-password/"
    response = Client().get(forged, follow=True)
    assert b"not valid" in response.content


def test_pre_login_lookup_exposes_one_user_row_only(committed_db: None) -> None:
    college = make_college("a")
    make_user(college, "a.one", email="one@example.org")
    make_user(college, "a.two", email="two@example.org")
    make_user(make_college("b"), "b.one")
    from django.db import transaction

    with transaction.atomic():
        assert User.auth_lookup.count() == 0
        set_auth_identity(login="a.one")
        assert list(User.auth_lookup.values_list("username", flat=True)) == ["a.one"]
        set_auth_identity(login="TWO@example.org")
        assert list(User.auth_lookup.values_list("username", flat=True)) == ["a.two"]
        set_auth_identity()
        assert User.auth_lookup.count() == 0


def test_a4_users_are_isolated_by_orm_and_raw_sql(committed_db: None) -> None:
    a, b = make_college("a"), make_college("b")
    make_user(a, "a.one")
    make_user(b, "b.one")
    with college_context(a.id):
        assert list(User.objects.values_list("username", flat=True)) == ["a.one"]
        with connection.cursor() as cursor:
            cursor.execute("SELECT username FROM accounts_user")
            assert cursor.fetchall() == [("a.one",)]
    with connection.cursor() as cursor, college_context(None):
        cursor.execute("SELECT count(*) FROM accounts_user")
        assert cursor.fetchone() == (0,)


def test_a5_no_setting_leaks_between_requests_on_one_connection(committed_db: None) -> None:
    a, b = make_college("a"), make_college("b")
    make_user(a, "a.lecturer", full_name="Asha")
    make_user(b, "b.lecturer", full_name="Bala")
    client_a, client_b = Client(), Client()
    _login(client_a, "a.lecturer")
    _login(client_b, "b.lecturer")

    connection.ensure_connection()
    backend_pid = connection.connection.info.backend_pid
    page_a = client_a.get("/")
    assert _setting("app.college_id") in (None, "")
    page_b = client_b.get("/")
    assert _setting("app.college_id") in (None, "")
    assert connection.connection.info.backend_pid == backend_pid  # same connection reused
    assert b"Asha" in page_a.content and b"Bala" not in page_a.content
    assert b"Bala" in page_b.content and b"Asha" not in page_b.content
    # an anonymous request right after sees no user at all
    assert Client().get("/").status_code == 302


def test_session_pointing_at_another_college_does_not_log_in(committed_db: None) -> None:
    a, b = make_college("a"), make_college("b")
    make_user(a, "a.lecturer")
    client = Client()
    _login(client, "a.lecturer")
    session = client.session
    session["college_id"] = str(b.id)  # a forged or stale value
    session.save()
    response = client.get("/")
    assert response.status_code == 302  # the user row is invisible under college B


def test_a9_response_headers_and_cookies(committed_db: None) -> None:
    make_user(make_college("a"), "a.lecturer")
    client = Client()
    page = client.get(LOGIN)
    assert "default-src 'self'" in page["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in page["Content-Security-Policy"]
    assert page["X-Frame-Options"] == "DENY"
    assert page["X-Content-Type-Options"] == "nosniff"
    assert page["Referrer-Policy"] == "same-origin"
    response = client.post(LOGIN, {"username": "a.lecturer", "password": PASSWORD})
    for name in ("sessionid", "csrftoken"):
        cookie = response.cookies[name]
        assert cookie["httponly"], name
        assert cookie["samesite"] == "Lax", name


def test_a9_production_settings_demand_secure_cookies_and_hsts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import config.settings.base as base

    def load() -> object:
        importlib.reload(base)
        sys.modules.pop("config.settings.prod", None)
        return importlib.import_module("config.settings.prod")

    monkeypatch.setenv("DJANGO_SECRET_KEY", "x" * 60)
    monkeypatch.setenv("ALLOW_INSECURE_HTTP", "false")
    loaded = load()
    assert loaded.SESSION_COOKIE_SECURE is True  # type: ignore[attr-defined]
    assert loaded.CSRF_COOKIE_SECURE is True  # type: ignore[attr-defined]
    assert loaded.SECURE_SSL_REDIRECT is True  # type: ignore[attr-defined]
    assert loaded.SECURE_HSTS_SECONDS >= 31536000  # type: ignore[attr-defined]
    monkeypatch.setenv("DJANGO_SECRET_KEY", "")
    with pytest.raises(ImproperlyConfigured):
        load()
    monkeypatch.undo()
    sys.modules.pop("config.settings.prod", None)
    importlib.reload(base)
