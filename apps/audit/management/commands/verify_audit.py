"""Check the audit hash chain of one or every college. Exit status 1 when a chain is broken.

    python manage.py verify_audit --all
    python manage.py verify_audit --college <id> [--college <id> ...]

A schedule runs this nightly; a non-zero exit is the alert (design section 12).
"""

import uuid
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.audit import services
from apps.audit.models import AuditEvent
from apps.tenancy import ops
from apps.tenancy.services import college_context


class Command(BaseCommand):
    help = "Recompute the audit hash chain and report any college whose chain is broken."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--college", action="append", default=[], help="a college id")
        parser.add_argument("--all", action="store_true", help="every college (needs POSTGRES_*)")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["all"]:
            ids = ops.all_college_ids()
        elif options["college"]:
            try:
                ids = [uuid.UUID(value) for value in options["college"]]
            except ValueError as error:
                raise CommandError("A college id is a UUID.") from error
        else:
            raise CommandError("Give --all or at least one --college.")
        broken = []
        for college_id in ids:
            with college_context(college_id):
                intact = services.verify_chain()
                count = AuditEvent.objects.count()
            self.stdout.write(f"{college_id}: {'OK' if intact else 'BROKEN'} ({count} events)")
            if not intact:
                broken.append(college_id)
        if broken:
            raise CommandError(f"The audit chain is broken for {len(broken)} college(s).")
