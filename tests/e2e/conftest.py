"""A real HTTP server for the browser tests.

pytest-django's `live_server` flushes the database after each test, which the app role may not
do. This starts Django's live-server thread on its own and relies on `committed_db` (the owner
empties the tables afterwards), like the other tests that need real commits.
"""

from collections.abc import Iterator

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test.testcases import LiveServerThread


@pytest.fixture
def app_server() -> Iterator[str]:
    thread = LiveServerThread("localhost", StaticLiveServerTestCase.static_handler)
    thread.daemon = True
    thread.start()
    thread.is_ready.wait()
    if thread.error:
        raise thread.error
    try:
        yield f"http://localhost:{thread.port}"
    finally:
        thread.terminate()
