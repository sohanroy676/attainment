"""The retention tool: list, give notice, anonymise.

    python manage.py retention list      --all
    python manage.py retention notify    --college <id>
    python manage.py retention anonymise --all

`--today YYYY-MM-DD` is for rehearsals and tests. Anonymising touches only students whose notice
period has run out (see `apps.privacy.services`).
"""

import uuid
from datetime import date
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.privacy import services
from apps.tenancy import ops
from apps.tenancy.services import college_context


class Command(BaseCommand):
    help = "List students past the retention period, put them on notice, or anonymise them."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("action", choices=["list", "notify", "anonymise"])
        parser.add_argument("--college", action="append", default=[], help="a college id")
        parser.add_argument("--all", action="store_true", help="every college (needs POSTGRES_*)")
        parser.add_argument("--today", help="pretend today is this date (YYYY-MM-DD)")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            today = date.fromisoformat(options["today"]) if options["today"] else date.today()
            ids = (
                ops.all_college_ids()
                if options["all"]
                else [uuid.UUID(v) for v in options["college"]]
            )
        except ValueError as error:
            raise CommandError(f"Bad value: {error}") from error
        if not ids:
            raise CommandError("Give --all or at least one --college.")
        for college_id in ids:
            with college_context(college_id):
                self._run(options["action"], today, college_id)

    def _run(self, action: str, today: date, college_id: uuid.UUID) -> None:
        if action == "list":
            for row in services.retention_list(today):
                self.stdout.write(
                    f"{college_id} {row.student.pk} {','.join(row.batches)} "
                    f"{row.state} ready_on={row.ready_on or '-'}"
                )
        elif action == "notify":
            self.stdout.write(f"{college_id}: {services.notify(today)} student(s) put on notice")
        else:
            self.stdout.write(f"{college_id}: {services.anonymise_due(today)} anonymised")
