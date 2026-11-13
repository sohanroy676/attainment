"""An end-to-end results environment with hand-computable numbers (synthetic data).

Section A (5 students) passes everything: every tool and CO is Level 3. Section B (2 students):
Internal-I part 1a is passed by half (50%, Level 2); everything else Level 3. Method: INT1 0.4 and
SEE 0.6, final 0.8 direct + 0.2 indirect (entered 3). Worked by hand:
  section A: CO1 3, CO2 3 -> course 3
  section B: direct CO1 = 0.4 x 2 + 0.6 x 3 = 2.6, final 2.68; CO2 final 3 -> course 2.84
  course (mean of sections): CO1 2.84, CO2 3 -> 2.92
  PO1 = (2 x 2.84 + 1 x 3) / 3 = 2.89333...   PO2 = CO1 = 2.84
"""

import json
from dataclasses import dataclass
from datetime import date

from django.db import transaction

from apps.academics.models import Batch, CourseOffering, Programme, Section
from apps.accounts.models import Role, User
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import make_user
from apps.marks import services as marks
from apps.marks.tests.helpers import Env, make_env
from apps.methodology import services as methods
from apps.outcomes import services as outcomes
from apps.results import services as results
from apps.tenancy.services import college_context

METHOD = {
    "schema": "attainment-method/1",
    "name": "Test method",
    "levels": {
        "bands": [
            {"min_pct": 60, "level": 3},
            {"min_pct": 50, "level": 2},
            {"min_pct": 10, "level": 1},
        ]
    },
    "tools": {
        "INT1": {"behaviour": "question_wise", "pass_pct": 60},
        "SEE": {
            "behaviour": "question_wise",
            "pass_pct": 60,
            "choice": {"G": {"best_n": 2}},
        },
    },
    "direct": {"INT1": "0.4", "SEE": "0.6"},
    "final": {"direct": "0.8", "indirect": "0.2"},
}


@dataclass
class REnv:
    env: Env
    iqac: User
    hod: User
    programme: Programme

    @property
    def college(self):  # type: ignore[no-untyped-def]
        return self.env.college

    @property
    def offering(self) -> CourseOffering:
        return self.env.s.offering


def _fill(env: Env, enrolments, assessment, columns: dict[str, list[str]]) -> None:  # type: ignore[no-untyped-def]
    """columns: part code -> one text per enrolment."""
    for code, texts in columns.items():
        part = assessment.parts.get(code=code)
        for enrolment, text in zip(enrolments, texts, strict=True):
            state, value = marks.parse_mark_text(text, part.max)
            row = marks.get_row(enrolment, assessment, create=True)
            actor = (
                env.exam
                if assessment.tool == "SEE"
                else (env.lecturer_a if enrolment in env.enrolments_a else env.lecturer_b)
            )
            marks.save_cell(row, part, state, value, actor)


def make_results_env(code: str = "a", with_marks: bool = True) -> REnv:
    env = make_env(code)
    iqac = make_user(env.college, f"{code}.iqac")
    hod = make_user(env.college, f"{code}.hod")
    with transaction.atomic(), college_context(env.college.id):
        assign_role(iqac, Role.IQAC)
        assign_role(hod, Role.HOD, "department", env.s.department.pk)
        programme = env.s.programme
        outcomes.create_programme_outcomes(programme, [("PO", "PO1", ""), ("PO", "PO2", "")])
        definition = env.s.course.definitions.get()
        outcomes.save_mapping_grid(
            definition, programme, {"CO1": {"PO1": 2, "PO2": 3}, "CO2": {"PO1": 1}}
        )
        outcomes.set_target("2.2", offering=env.s.offering)
        results.set_indirect(env.s.offering, {"CO1": "3", "CO2": "3"}, "test", iqac)
        method = methods.create_method("Test method")
        version = methods.create_draft(method, json.dumps(METHOD))
        methods.activate(version, date(2025, 1, 1), iqac)
        methods.assign_method("college", method)
        if with_marks:
            _fill(env, env.enrolments_a, env.internal, {"1a": ["4"] * 5, "1b": ["4"] * 5})
            _fill(env, env.enrolments_b, env.internal, {"1a": ["4", "0"], "1b": ["4", "4"]})
            for enrolments in (env.enrolments_a, env.enrolments_b):
                n = len(enrolments)
                _fill(
                    env, enrolments, env.see,
                    {"1": ["4"] * n, "11": ["4"] * n, "12": ["4"] * n, "13": ["-"] * n},
                )  # fmt: skip
    return REnv(env, iqac, hod, programme)


def second_programme(r: REnv):  # type: ignore[no-untyped-def]
    """A second programme served by the same offering, with one section C of two students."""
    from apps.academics.models import Department
    from apps.roster import services as roster

    env = r.env
    with college_context(env.college.id):
        dept = Department.objects.get(code="CSE")
        other = Programme.objects.create(department=dept, name="B.E. AIML", level="UG")
        batch = Batch.objects.create(
            programme=other, name="2021-25", start_year=2021, end_year=2025
        )
        section = Section.objects.create(
            offering=env.s.offering, name="C", programme=other, batch=batch
        )
        enrolments = []
        for roll in (1, 2):
            student = roster.create_student(f"Student C{roll}")
            roster.add_identifier(student, str(roll), section=section)
            enrolments.append(roster.enrol(student, env.s.offering, section))
    return other, section, enrolments
