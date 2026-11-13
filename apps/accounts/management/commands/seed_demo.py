"""Create two demo colleges with one account per role. Safe to run again.

Demo data only: no real student data, example.org addresses. The password comes from
--password, then DEMO_PASSWORD, otherwise a random one is generated and printed once.
"""

import os
import secrets
import uuid
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role, ScopeType, User
from apps.accounts.services import assign_role, create_user
from apps.tenancy.models import College
from apps.tenancy.services import college_context, create_college

NAMESPACE = uuid.UUID("6f1c1f0e-5d0a-4c55-9a53-0c3b7d0e7a11")

COLLEGES = [("a", "Demo College A"), ("b", "Demo College B")]

# (username suffix, role, scope). Department, offering and section ids are placeholders until
# the academic structure exists (v0.4.0); they are stable so the accounts keep their scope.
ACCOUNTS: list[tuple[str, Role, ScopeType]] = [
    ("admin", Role.COLLEGE_ADMIN, ScopeType.COLLEGE),
    ("iqac", Role.IQAC, ScopeType.COLLEGE),
    ("hod", Role.HOD, ScopeType.DEPARTMENT),
    ("coordinator", Role.COORDINATOR, ScopeType.OFFERING),
    ("lecturer", Role.LECTURER, ScopeType.SECTION),
    ("exam", Role.EXAM_BRANCH, ScopeType.COLLEGE),
    ("principal", Role.PRINCIPAL, ScopeType.COLLEGE),
    ("auditor", Role.AUDITOR, ScopeType.COLLEGE),
]


class Command(BaseCommand):
    help = "Create two demo colleges and the demo accounts (idempotent)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--password", help="password for newly created demo accounts")

    def handle(self, *args: Any, **options: Any) -> None:
        password = options["password"] or os.environ.get("DEMO_PASSWORD") or ""
        generated = not password
        if generated:
            password = secrets.token_urlsafe(12) + "-Demo1"
        created: list[str] = []
        with transaction.atomic():
            for code, name in COLLEGES:
                college_id = uuid.uuid5(NAMESPACE, f"college:{code}")
                with college_context(college_id):
                    if not College.objects.filter(id=college_id).exists():
                        create_college(name, f"demo-{code}", college_id=college_id)
                    for suffix, role, scope in ACCOUNTS:
                        username = f"{code}.{suffix}"
                        if User.objects.filter(username=username).exists():
                            continue
                        user = create_user(
                            username,
                            password,
                            email=f"{username}@example.org",
                            full_name=f"{name} {role.label}",
                        )
                        scope_id = (
                            None
                            if scope == ScopeType.COLLEGE
                            else uuid.uuid5(NAMESPACE, f"{code}:{scope.value}")
                        )
                        assign_role(user, role, scope, scope_id, reason="demo seed")
                        created.append(username)
        if created:
            self.stdout.write(f"Created {len(created)} demo accounts: {', '.join(created)}")
            if generated:
                self.stdout.write(f"Password for the new accounts: {password}")
        else:
            self.stdout.write("Demo data already present; nothing changed.")
