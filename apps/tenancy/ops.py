"""Helpers for operations commands (verify, retention, backup checks).

The app role sees one college at a time, so a job that must visit every college asks the
database superuser for the list of college ids. That login (POSTGRES_USER and POSTGRES_PASSWORD)
exists only in the operations container's environment, never in the web app's.
"""

import os
import uuid

import psycopg
from django.conf import settings


def all_college_ids() -> list[uuid.UUID]:
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise RuntimeError("POSTGRES_PASSWORD is needed to list every college; pass --college.")
    database = settings.DATABASES["owner"]
    with psycopg.connect(
        host=database["HOST"],
        port=database["PORT"],
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=password,
        dbname=database["NAME"],
        connect_timeout=10,
    ) as connection:
        rows = connection.execute("SELECT id FROM tenancy_college ORDER BY code").fetchall()
    return [row[0] for row in rows]
