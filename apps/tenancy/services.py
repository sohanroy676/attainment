"""The only place that sets who the current college is.

Other modules call these functions; they never touch the database setting themselves.
Every setting uses SET LOCAL semantics (set_config with is_local=true): it lives only until
the end of the current transaction, so it cannot leak to the next request on a reused
connection.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection, transaction

from .context import get_current_college_id, set_current_college_id
from .models import College

SESSION_KEY = "college_id"  # where login stores the user's college in the session


def _set_local(name: str, value: str) -> None:
    if not connection.in_atomic_block:
        raise RuntimeError(f"{name} can only be set inside a transaction (SET LOCAL)")
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, true)", [name, value])


def set_current_college(college_id: uuid.UUID | None) -> None:
    """Make `college_id` the current college for the ORM and for row-level security."""
    _set_local("app.college_id", "" if college_id is None else str(college_id))
    set_current_college_id(college_id)


def set_auth_identity(login: str = "", user_id: uuid.UUID | None = None) -> None:
    """Let exactly one user row become visible before the college is known.

    Used only by login and password reset, which must find a user by username, email or id
    before anybody is logged in. The users policy accepts these two settings and nothing else.
    """
    _set_local("app.auth_login", login)
    _set_local("app.auth_user_id", "" if user_id is None else str(user_id))


@contextmanager
def college_context(college_id: uuid.UUID | None) -> Iterator[None]:
    """Run a block as one college, then restore the previous one (jobs, commands, tests)."""
    previous = get_current_college_id()
    with transaction.atomic():
        set_current_college(college_id)
        try:
            yield
        finally:
            set_current_college(previous)


def create_college(name: str, code: str, college_id: uuid.UUID | None = None) -> College:
    """Create a college. Its id is chosen first so the row passes its own policy."""
    college_id = college_id or uuid.uuid4()
    with college_context(college_id):
        return College.objects.create(id=college_id, name=name, code=code)
