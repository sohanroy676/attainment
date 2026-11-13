from unittest import mock

import pytest
from django.test import Client

pytestmark = pytest.mark.integration


def test_healthz_reports_database_and_migrations(db: None) -> None:
    response = Client().get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable", "migrations": "current"}


def test_healthz_is_unavailable_when_database_is_down(db: None) -> None:
    with mock.patch("config.health._database_reachable", return_value=False):
        response = Client().get("/healthz")
    assert response.status_code == 503
    assert response.json()["database"] == "unreachable"


def test_healthz_is_unavailable_when_migrations_are_pending(db: None) -> None:
    with mock.patch("config.health._migrations_current", return_value=False):
        response = Client().get("/healthz")
    assert response.status_code == 503
    assert response.json()["migrations"] == "pending"
