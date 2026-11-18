"""Create a real college and its first administrator.

    python manage.py create_college "Name of the College" short-code first.admin

The administrator's password is generated and printed once (or read from ADMIN_PASSWORD).
Everything else (users, structure, roster) is then set up in the application.
"""

import os
import secrets
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import IntegrityError, transaction

from apps.accounts.models import Role
from apps.accounts.services import assign_role, create_user
from apps.tenancy.services import college_context, create_college


class Command(BaseCommand):
    help = "Create a college and its first college administrator."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("name", help="the college's full name")
        parser.add_argument("code", help="a short code: letters, digits and hyphens")
        parser.add_argument("admin_username", help="the first administrator's username")
        parser.add_argument("--email", default="", help="the administrator's email address")

    def handle(self, *args: Any, **options: Any) -> None:
        password = os.environ.get("ADMIN_PASSWORD") or ""
        generated = not password
        if generated:
            password = secrets.token_urlsafe(14) + "-Aa1"
        try:
            with transaction.atomic():
                college = create_college(options["name"], options["code"])
                with college_context(college.id):
                    admin = create_user(
                        options["admin_username"], password, email=options["email"],
                        full_name="College administrator",
                    )  # fmt: skip
                    assign_role(admin, Role.COLLEGE_ADMIN, reason="first administrator")
        except (ValidationError, IntegrityError) as error:
            raise CommandError(f"The college was not created: {error}") from error
        self.stdout.write(f"Created {college.name} ({college.code}), id {college.id}.")
        if generated:
            self.stdout.write(f"Password for {options['admin_username']}: {password}")
            self.stdout.write("Log in and change it; it is shown only now.")
