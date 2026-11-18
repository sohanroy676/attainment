"""A small marks environment for tests: a course with an internal paper and a SEE paper."""

from dataclasses import dataclass

from apps.academics.models import CourseOffering, Section
from apps.academics.services import assign_faculty
from apps.academics.tests.helpers import Structure, make_structure
from apps.accounts.models import Role, User
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import make_college, make_user
from apps.assessments import services as papers
from apps.assessments.models import Assessment
from apps.outcomes import services as outcomes
from apps.roster import services as roster
from apps.roster.models import Enrolment
from apps.tenancy.models import College
from apps.tenancy.services import college_context

B = Assessment.Behaviour


@dataclass
class Env:
    college: College
    s: Structure
    internal: Assessment
    see: Assessment
    lecturer_a: User
    lecturer_b: User
    exam: User
    auditor: User
    enrolments_a: list[Enrolment]
    enrolments_b: list[Enrolment]


def _q(number, parts, group=None):  # type: ignore[no-untyped-def]
    return {
        "number": number,
        "choice_group": group,
        "parts": [{"label": lab, "max": mx, "co": co} for lab, mx, co in parts],
    }


def make_env(code: str = "a", students_a: int = 5, students_b: int = 2) -> Env:
    college = make_college(code)
    s = make_structure(college)
    lecturer_a = make_user(college, f"{code}.lecturer_a")
    lecturer_b = make_user(college, f"{code}.lecturer_b")
    exam = make_user(college, f"{code}.exam")
    auditor = make_user(college, f"{code}.auditor")
    with college_context(college.id):
        outcomes.create_definition(s.course, [("CO1", ""), ("CO2", "")])
        internal = papers.create_paper(
            s.offering, "INT1", "Internal-I", B.QUESTION_WISE,
            [_q("1", [("a", "4", "CO1"), ("b", "4", "CO2")])],
        )  # fmt: skip
        see = papers.create_paper(
            s.offering, "SEE", "SEE", B.QUESTION_WISE,
            [_q("1", [("", "4", "CO1")])]
            + [_q(str(n), [("", "4", "CO1" if n % 2 else "CO2")], "G") for n in (11, 12, 13)],
            groups={"G": {"best_n": 2}},
        )  # fmt: skip
        assign_faculty(lecturer_a, s.offering, s.section_a)
        assign_faculty(lecturer_b, s.offering, s.section_b)
        assign_role(exam, Role.EXAM_BRANCH)
        assign_role(auditor, Role.AUDITOR)
        enrolments_a = _roster(s.section_a, s.offering, students_a, "A")
        enrolments_b = _roster(s.section_b, s.offering, students_b, "B")
    return Env(
        college, s, internal, see, lecturer_a, lecturer_b, exam, auditor, enrolments_a, enrolments_b
    )


def _roster(section: Section, offering: CourseOffering, n: int, tag: str) -> list[Enrolment]:
    made = []
    for roll in range(1, n + 1):
        student = roster.create_student(f"Student {tag}{roll}")
        roster.add_identifier(student, str(roll), section=section)
        made.append(roster.enrol(student, offering, section))
    return made
