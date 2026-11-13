"""Row-level security for migrations (design 13.1).

Every tenant table gets ENABLE and FORCE (so even the owner is bound) and one policy that
matches only the current college. With no college set the policy matches nothing.
"""

from django.db import migrations

CURRENT_COLLEGE = "NULLIF(current_setting('app.college_id', true), '')::uuid"
POLICY_NAME = "tenant_isolation"


def tenant_rls(
    table: str,
    column: str = "college_id",
    also_visible: str = "",
) -> migrations.RunSQL:
    """Enable and force RLS on `table`.

    `also_visible` is an extra SQL condition for reading only (used by the users table for the
    narrow pre-login lookup). Writes always require the current college.
    """
    own = f"{column} = {CURRENT_COLLEGE}"
    using = f"({own}) OR ({also_visible})" if also_visible else own
    forward = f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY {POLICY_NAME} ON {table} USING ({using}) WITH CHECK ({own});
    """
    reverse = f"""
        DROP POLICY {POLICY_NAME} ON {table};
        ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
    """
    return migrations.RunSQL(forward, reverse)
