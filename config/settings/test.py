"""Test run: dev settings and a dedicated database."""

from .dev import *  # noqa: F403
from .dev import DATABASES

TEST_DB_NAME = "attainment_test"
for _alias in DATABASES.values():
    _alias["NAME"] = TEST_DB_NAME
# Reuse connections so the leak test (A5) exercises a pooled connection.
DATABASES["default"]["CONN_MAX_AGE"] = 60
