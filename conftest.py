"""Shared pytest setup: a throwaway database that is used the way production is.

The database is created and dropped by the PostgreSQL superuser, migrated by the owner role,
and every test then connects as the non-owner app role. Row-level security is therefore
tested for real, never bypassed.
"""

import os
from collections.abc import Iterator

import psycopg
import pytest
from django.conf import settings
from django.core.management import call_command
from psycopg import sql


def _superuser_connection(dbname: str) -> psycopg.Connection:
    return psycopg.connect(
        host=settings.DATABASES["owner"]["HOST"],
        port=settings.DATABASES["owner"]["PORT"],
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=dbname,
        autocommit=True,
        connect_timeout=10,
    )


@pytest.fixture(scope="session")
def django_db_setup(django_db_blocker: pytest.FixtureDef) -> Iterator[None]:  # type: ignore[type-arg]
    name = sql.Identifier(settings.TEST_DB_NAME)
    owner = sql.Identifier(settings.DB_OWNER_USER)
    app = sql.Identifier(settings.DB_APP_USER)

    with _superuser_connection("postgres") as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(name, owner))
    with _superuser_connection(settings.TEST_DB_NAME) as conn:
        conn.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(owner))
        conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(app))

    with django_db_blocker.unblock():
        call_command("migrate", database="owner", verbosity=0, interactive=False)
    yield
    with django_db_blocker.unblock():
        from django.db import connections

        connections.close_all()
    with _superuser_connection("postgres") as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
