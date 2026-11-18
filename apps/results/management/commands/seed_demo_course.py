"""Add a synthetic course with marks to the two demo colleges made by `seed_demo`.

    python manage.py seed_demo
    python manage.py seed_demo_course

Demo college A: a theory course in two sections, 40 + 27 students, roll numbers 1.. in each
section. Demo college B: the same course shape with 66 + 64 students numbered 1-66 and 67-130
across the batch. Everything is invented from a fixed random seed: no real names, roll numbers
or marks. The demo accounts keep the scopes `seed_demo` gave them because the structure is
created with the same ids. Safe to run again (it does nothing if the course exists).
"""

import random
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academics.models import (
    AcademicYear,
    Batch,
    Course,
    CourseCode,
    CourseOffering,
    Department,
    Programme,
    Section,
    Term,
)
from apps.accounts.management.commands.seed_demo import NAMESPACE
from apps.accounts.models import User
from apps.assessments import services as papers
from apps.assessments.models import Assessment
from apps.marks import services as marks
from apps.methodology import services as methods
from apps.outcomes import services as outcomes
from apps.results import services as results
from apps.roster import services as roster
from apps.tenancy.models import College
from apps.tenancy.services import college_context

Behaviour = Assessment.Behaviour
COS = ["CO1", "CO2", "CO3", "CO4", "CO5"]
POS = [("PO", f"PO{n}", "") for n in range(1, 13)] + [("PSO", f"PSO{n}", "") for n in range(1, 4)]
MAPPING = {
    "CO1": {"PO1": 3, "PO2": 2, "PSO1": 3},
    "CO2": {"PO2": 3, "PO3": 2, "PSO1": 2},
    "CO3": {"PO3": 3, "PO5": 2, "PSO2": 3},
    "CO4": {"PO4": 2, "PO5": 3, "PSO2": 2},
    "CO5": {"PO1": 1, "PO12": 3, "PSO3": 3},
}
SCHEMES = {
    "a": {"sections": [("A", 40), ("B", 27)], "scope": "section"},
    "b": {"sections": [("A", 66), ("B", 64)], "scope": "batch"},
}


def _q(number: str, parts: list[tuple[str, str, str | None]], group: str | None = None) -> dict:  # type: ignore[type-arg]
    return {
        "number": number,
        "choice_group": group,
        "parts": [{"label": label, "max": mx, "co": co} for label, mx, co in parts],
    }


def _internal1() -> list[dict]:  # type: ignore[type-arg]
    return [
        _q("1", [("a", "2", "CO1"), ("b", "3", "CO1")]),
        _q("2", [("a", "2", "CO2"), ("b", "3", "CO2")]),
        _q("3", [("a", "3", "CO3"), ("b", "2", "CO3")]),
    ]


def _internal2() -> list[dict]:  # type: ignore[type-arg]
    cos = ["CO3", "CO3", "CO4", "CO4", "CO5", "CO5"]
    return [_q(str(n), [("", "4", cos[n - 1])], "G") for n in range(1, 7)]


def _see() -> list[dict]:  # type: ignore[type-arg]
    compulsory = [_q(str(n), [("", "2", COS[n - 1])]) for n in range(1, 6)]
    optional = [
        _q(str(n), [("a", "4", COS[n % 5]), ("b", "4", COS[n % 5])], "G") for n in range(11, 17)
    ]
    q17 = _q("17", [("a", "4", "CO5"), ("b", "4", "CO5"), ("c", "4", "CO5")], "G")
    return [*compulsory, *optional, q17]


def _items(count: int) -> list[dict]:  # type: ignore[type-arg]
    return [_q(str(k), [("", "5", None)]) for k in range(1, count + 1)]


class Command(BaseCommand):
    help = "Create a synthetic course with marks in the two demo colleges."

    def handle(self, *args: Any, **options: Any) -> None:
        done = []
        for code in ("a", "b"):
            college_id = uuid.uuid5(NAMESPACE, f"college:{code}")
            if not College.objects.filter(id=college_id).exists():
                with college_context(college_id):
                    exists = College.objects.filter(id=college_id).exists()
                if not exists:
                    raise CommandError("Run `manage.py seed_demo` first.")
            with college_context(college_id):
                if Course.objects.filter(title__startswith="Deep Learning").exists():
                    self.stdout.write(f"Demo college {code.upper()} already has the course.")
                    continue
                self._seed(code)
            offering_id = uuid.uuid5(NAMESPACE, f"{code}:offering")
            self.stdout.write(f"  college {code.upper()}: /results/{offering_id}/ (user {code}.iqac)")
            done.append(code.upper())
        if done:
            self.stdout.write(f"Added the demo course to college(s) {', '.join(done)}.")

    def _seed(self, code: str) -> None:
        rng = random.Random(f"demo-{code}")  # noqa: S311 - invented demo marks, not security
        scheme = SCHEMES[code]
        user = {s: User.objects.get(username=f"{code}.{s}") for s in
                ("iqac", "hod", "coordinator", "lecturer", "exam", "principal")}  # fmt: skip
        placeholder = lambda scope: uuid.uuid5(NAMESPACE, f"{code}:{scope}")  # noqa: E731
        with transaction.atomic():
            department = Department.objects.create(
                id=placeholder("department"), name="Computer Science and Engineering", code="CSE"
            )
            programme = Programme.objects.create(department=department, name="B.E. CSE", level="UG")
            batch = Batch.objects.create(
                programme=programme, name="2021-25", start_year=2021, end_year=2025
            )
            year = AcademicYear.objects.create(
                label="2025-26", start_date=date(2025, 6, 1), end_date=date(2026, 5, 31)
            )
            term = Term.objects.create(academic_year=year, number=7)
            course = Course.objects.create(title="Deep Learning (demo)", credits=Decimal("3"))
            CourseCode.objects.create(course=course, code="CS701")
            offering = CourseOffering.objects.create(
                id=placeholder("offering"),
                course=course,
                term=term,
                coordinator=user["coordinator"],
            )
            sections = []
            for position, (name, size) in enumerate(scheme["sections"]):
                section = Section.objects.create(
                    id=placeholder("section") if position == 0 else uuid.uuid4(),
                    offering=offering, name=name, programme=programme, batch=batch,
                )  # fmt: skip
                sections.append((section, size))
            self._roster(sections, batch, offering, scheme["scope"])

            outcomes.create_programme_outcomes(programme, POS)
            definition = outcomes.create_definition(course, [(co, f"Outcome {co}") for co in COS])
            outcomes.save_mapping_grid(definition, programme, MAPPING)
            outcomes.set_target("2.2", offering=offering)
            for kind_code in [c for _, c, _ in POS]:
                po = outcomes.ProgrammeOutcome.objects.get(programme=programme, code=kind_code)
                outcomes.set_target("2.5", outcome=po, batch=batch)
            version = methods.create_from_template("vasavi_theory")
            methods.activate(version, date(2025, 6, 1), user["iqac"])
            methods.assign_method("college", version.method)
            results.set_indirect(offering, dict.fromkeys(COS, "3"), "demo value", user["iqac"])
            results.set_batch_indirect(batch, {c: "3" for _, c, _ in POS}, "demo", user["iqac"])
            self._marks(rng, offering, sections, user)
        results.calculate(offering, programme)

    def _roster(self, sections, batch, offering, scope) -> None:  # type: ignore[no-untyped-def]
        number = 0
        for section, size in sections:
            for index in range(1, size + 1):
                number += 1
                student = roster.create_student(f"Demo Student {section.name}{index:03d}")
                if scope == "batch":
                    roster.add_identifier(student, str(number), batch=batch)
                else:
                    roster.add_identifier(student, str(index), section=section)
                roster.join_batch(student, batch)
                roster.enrol(student, offering, section)

    def _marks(self, rng, offering, sections, user) -> None:  # type: ignore[no-untyped-def]
        specs = [
            ("INT1", "Internal-I", Behaviour.QUESTION_WISE, _internal1(), None),
            ("INT2", "Internal-II", Behaviour.QUESTION_WISE, _internal2(), {"G": {"best_n": 4}}),
            ("SEE", "Semester examination", Behaviour.QUESTION_WISE, _see(),
             {"G": {"best_n": 5, "best_k_parts": {"17": 2}}}),
            ("QUIZ", "Quiz", Behaviour.PER_STUDENT_AVERAGE, _items(4), None),
            ("ASSIGN", "Assignment", Behaviour.PER_STUDENT_AVERAGE, _items(4), None),
        ]  # fmt: skip
        for tool, name, behaviour, questions, groups in specs:
            paper = papers.create_paper(offering, tool, name, behaviour, questions, groups=groups)
            parts = list(paper.parts.select_related("question"))
            for index, (section, _) in enumerate(sections):
                actor = (
                    user["exam"]
                    if tool == "SEE"
                    else user["lecturer"]
                    if index == 0
                    else user["coordinator"]
                )
                for enrolment in roster.enrolments_in(section):
                    sheet = marks.get_row(enrolment, paper, create=True)
                    self._fill_row(rng, tool, sheet, parts, actor)

    def _fill_row(self, rng, tool, sheet, parts, actor) -> None:  # type: ignore[no-untyped-def]
        """One student's marks: a skill level for the student, noise per part, choices skipped
        where the paper lets them, and a few absentees."""
        skill = rng.uniform(0.35, 0.95)
        optional = sorted(
            {p.question.number for p in parts if p.question.choice_group_id is not None}, key=int
        )
        skipped: set[str] = set()
        if tool == "INT2":  # answers four of six
            skipped = set(rng.sample(optional, 2))
        elif tool == "SEE":  # answers five to seven of seven
            skipped = set(rng.sample(optional, rng.choice([0, 1, 2])))
        if rng.random() < 0.03:  # a few students were absent
            for part in parts:
                marks.save_cell(sheet, part, "absent", None, actor)
            return
        for part in parts:
            if part.question.number in skipped:
                continue  # not attempted: left blank
            fraction = min(1.0, max(0.0, skill + rng.uniform(-0.2, 0.2)))
            mark = (part.max * Decimal(str(round(fraction, 2)))).quantize(Decimal("0.5"))
            marks.save_cell(sheet, part, "value", min(mark, part.max), actor)
