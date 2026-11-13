import uuid
from collections.abc import Callable

from django.db import transaction
from django.http import HttpRequest, HttpResponse

from .context import set_current_college_id
from .services import set_current_college

SESSION_KEY = "college_id"


class TenantMiddleware:
    """Opens the request transaction and sets the current college inside it (SET LOCAL).

    The college comes from the signed server-side session written at login, never from the
    URL or a header. The transaction wraps everything after this middleware, including the
    user lookup, so the setting dies with the transaction and cannot leak to the next request.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        college_id = self._college_from_session(request)
        try:
            with transaction.atomic():
                set_current_college(college_id)
                response = self.get_response(request)
                if response.status_code >= 500:
                    transaction.set_rollback(True)
                return response
        finally:
            set_current_college_id(None)

    @staticmethod
    def _college_from_session(request: HttpRequest) -> uuid.UUID | None:
        raw = request.session.get(SESSION_KEY)
        if not raw:
            return None
        try:
            return uuid.UUID(str(raw))
        except ValueError:
            return None
