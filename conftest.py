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


@pytest.fixture(autouse=True)
def _reset_current_college() -> Iterator[None]:
    """No test may inherit the previous test's college."""
    from apps.tenancy.context import set_current_college_id

    set_current_college_id(None)
    yield
    set_current_college_id(None)


@pytest.fixture
def committed_db(django_db_blocker: pytest.FixtureDef) -> Iterator[None]:  # type: ignore[type-arg]
    """For tests that need real commits (connection reuse, per-request transactions).

    The app role cannot TRUNCATE, so the owner empties the tables afterwards.
    """
    from django.db import connections

    with django_db_blocker.unblock():
        yield
        connections.close_all()
        owner = settings.DATABASES["owner"]
        with psycopg.connect(
            host=owner["HOST"],
            port=owner["PORT"],
            user=owner["USER"],
            password=owner["PASSWORD"],
            dbname=owner["NAME"],
            autocommit=True,
        ) as conn:
            tables = [
                row[0]
                for row in conn.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename NOT IN ('django_migrations', 'django_content_type', "
                    "'auth_permission')"
                )
            ]
            if tables:
                names = sql.SQL(", ").join(sql.Identifier(t) for t in tables)
                conn.execute(sql.SQL("TRUNCATE {} CASCADE").format(names))
