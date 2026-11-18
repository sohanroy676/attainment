from typing import Any

from django.apps import AppConfig
from django.conf import settings
from django.db import connections
from django.db.models.signals import post_migrate
from psycopg import sql

# Tables the app role may read and add to but never change (see design section 12).
APPEND_ONLY_TABLES = (
    "audit_auditevent",
    "marks_markchange",
    "workflow_signature",
    "workflow_reopening",
)


def grant_app_role(using: str, **kwargs: Any) -> None:
    """After migrating as the owner, give the app role data access, and nothing more.

    The app role gets SELECT/INSERT/UPDATE/DELETE on tables and no TRUNCATE, no DDL.
    Append-only tables lose UPDATE and DELETE again.
    """
    connection = connections[using]
    app_role = settings.DB_APP_USER
    if connection.settings_dict["USER"] == app_role:
        return
    role = sql.Identifier(app_role)
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [app_role])
        if cursor.fetchone() is None:
            return
        cursor.execute(
            sql.SQL(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
            ).format(role)
        )
        cursor.execute(
            sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(role)
        )
        for table in APPEND_ONLY_TABLES:
            cursor.execute("SELECT to_regclass(%s)", [f"public.{table}"])
            row = cursor.fetchone()
            if row is not None and row[0] is not None:
                cursor.execute(
                    sql.SQL("REVOKE UPDATE, DELETE ON {} FROM {}").format(
                        sql.Identifier(table), role
                    )
                )


class TenancyConfig(AppConfig):
    name = "apps.tenancy"
    label = "tenancy"

    def ready(self) -> None:
        post_migrate.connect(grant_app_role, dispatch_uid="tenancy.grant_app_role")
