"""A3 and the isolation tests for the tenancy tables. All run as the non-owner app role."""

import pytest
from django.apps import apps
from django.db import DatabaseError, connection, transaction

from apps.tenancy.models import College, TenantModel
from apps.tenancy.services import college_context, create_college, set_current_college

pytestmark = [pytest.mark.integration, pytest.mark.isolation]

# Tables that belong to no college: framework, login throttling, migrations.
GLOBAL_TABLE_PREFIXES = ("django_", "auth_", "axes_")


def _scalar(sql: str, params: list[object] | None = None) -> object:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]  # type: ignore[index]


def test_a3_every_tenant_table_has_college_id_and_a_forced_policy(db: None) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   (SELECT count(*) FROM pg_policies p
                     WHERE p.schemaname = 'public' AND p.tablename = c.relname),
                   EXISTS (SELECT 1 FROM information_schema.columns k
                            WHERE k.table_schema = 'public' AND k.table_name = c.relname
                              AND k.column_name = 'college_id')
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relkind = 'r'
            """
        )
        rows = cursor.fetchall()
    assert rows
    problems = []
    for table, rls, forced, policies, has_college in rows:
        if table.startswith(GLOBAL_TABLE_PREFIXES):
            continue
        if not (has_college or table == "tenancy_college"):
            problems.append(f"{table}: no college_id column")
        if not (rls and forced and policies >= 1):
            problems.append(f"{table}: row-level security missing or not forced")
    assert not problems, problems


def test_every_tenant_model_is_covered(db: None) -> None:
    tenant_tables = {
        model._meta.db_table
        for model in apps.get_models()
        if issubclass(model, TenantModel) and not model._meta.abstract
    }
    for table in tenant_tables:
        assert _scalar("SELECT relforcerowsecurity FROM pg_class WHERE relname = %s", [table])


def test_app_role_is_not_owner_and_cannot_bypass(db: None) -> None:
    row = _scalar(
        "SELECT rolsuper OR rolbypassrls OR rolcreatedb FROM pg_roles WHERE rolname = current_user"
    )
    assert row is False
    assert _scalar(
        "SELECT tableowner <> current_user FROM pg_tables WHERE tablename = 'tenancy_college'"
    )


def test_with_no_college_set_nothing_is_visible(db: None) -> None:
    create_college("College A", "a")
    assert _scalar("SELECT count(*) FROM tenancy_college") == 0
    assert College.objects.count() == 0


def test_a4_each_college_sees_only_itself_by_orm_and_raw_sql(db: None) -> None:
    a = create_college("College A", "a")
    b = create_college("College B", "b")
    with college_context(a.id):
        assert _scalar("SELECT count(*) FROM tenancy_college") == 1
        assert list(College.objects.values_list("code", flat=True)) == ["a"]
        assert _scalar("SELECT count(*) FROM tenancy_college WHERE id = %s", [str(b.id)]) == 0
    with college_context(b.id):
        assert list(College.objects.values_list("code", flat=True)) == ["b"]


def test_a_college_cannot_write_another_colleges_row(db: None) -> None:
    a = create_college("College A", "a")
    b = create_college("College B", "b")
    with college_context(a.id):
        assert (
            _scalar(
                "WITH u AS (UPDATE tenancy_college SET name = 'x' WHERE id = %s RETURNING 1) "
                "SELECT count(*) FROM u",
                [str(b.id)],
            )
            == 0
        )
        with pytest.raises(DatabaseError), transaction.atomic():
            College.objects.create(name="Intruder", code="intruder")  # new id is not A's


def test_setting_the_college_outside_a_transaction_is_refused(committed_db: None) -> None:
    # autocommit: a SET LOCAL here would silently do nothing, so it must fail loudly
    with pytest.raises(RuntimeError):
        set_current_college(None)
