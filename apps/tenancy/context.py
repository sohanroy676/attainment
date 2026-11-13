"""The current college for this request, held in a context variable.

The application layer filters by this value (see managers.py). The database layer reads the
same value from the transaction setting `app.college_id` (see services.py). Both are set
together by services.set_current_college, so they cannot drift apart.
"""

import uuid
from contextvars import ContextVar

_current_college_id: ContextVar[uuid.UUID | None] = ContextVar("current_college_id", default=None)


def get_current_college_id() -> uuid.UUID | None:
    return _current_college_id.get()


def set_current_college_id(college_id: uuid.UUID | None) -> None:
    _current_college_id.set(college_id)
