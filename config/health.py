"""/healthz: reports whether the database is reachable and migrations are current."""

from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.http import HttpRequest, JsonResponse


def _database_reachable() -> bool:
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return False
    return True


def _migrations_current() -> bool:
    try:
        with transaction.atomic():
            executor = MigrationExecutor(connection)
            return not executor.migration_plan(executor.loader.graph.leaf_nodes())
    except DatabaseError:
        return False


def healthz(request: HttpRequest) -> JsonResponse:
    database = _database_reachable()
    migrations = database and _migrations_current()
    body = {
        "status": "ok" if migrations else "unavailable",
        "database": "reachable" if database else "unreachable",
        "migrations": "current" if migrations else "pending",
    }
    return JsonResponse(body, status=200 if migrations else 503)
