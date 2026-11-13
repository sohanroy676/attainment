"""A3, A4, A8 (synthetic form) for question papers, and copying a paper."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.academics.models import Course, CourseOffering
from apps.academics.tests.helpers import make_structure
from apps.accounts.models import Role
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import make_college, make_user
from apps.assessments import services
from apps.assessments.models import Assessment, QuestionPart
from apps.outcomes import services as outcomes
from apps.tenancy.services import college_context

pytestmark = [pytest.mark.integration]

B = Assessment.Behaviour


def _course(college, n_cos: int = 5):  # type: ignore[no-untyped-def]
    s = make_structure(college)
    with college_context(college.id):
        outcomes.create_definition(s.course, [(f"CO{i}", "") for i in range(1, n_cos + 1)])
    return s


def _q(number: str, parts: list[tuple[str, str, str | None]], group: str | None = None) -> dict:  # type: ignore[type-arg]
    return {
        "number": number,
        "choice_group": group,
        "parts": [{"label": label, "max": mx, "co": co} for label, mx, co in parts],
    }


def _internal2_spec() -> list[dict]:  # type: ignore[type-arg]
    """Six questions of two parts each (3.5 marks each part); answer any 4."""
    return [
        _q(
            str(n),
            [("a", "3.5", f"CO{(n + 1) // 2 + 2}"), ("b", "3.5", f"CO{(n + 1) // 2 + 2}")],
            "G",
        )
        for n in range(1, 7)
    ]


def _see_spec() -> list[dict]:  # type: ignore[type-arg]
    compulsory = [_q(str(n), [("", "2", f"CO{(n - 1) % 5 + 1}")]) for n in range(1, 11)]
    choice = [
        _q(str(n), [("a", "4", f"CO{n % 5 + 1}"), ("b", "4", f"CO{n % 5 + 1}")], "G")
        for n in range(11, 17)
    ]
    choice.append(_q("17", [("a", "4", "CO3"), ("b", "4", "CO4"), ("c", "4", "CO5")], "G"))
    return compulsory + choice


def test_a3_a_sound_paper_validates_and_the_total_follows_the_choice_rules(db: None) -> None:
    college = make_college("a")
    s = _course(college)
    with college_context(college.id):
        paper = services.create_paper(
            s.offering, "INT2", "Internal-II", B.QUESTION_WISE, _internal2_spec(),
            groups={"G": {"best_n": 4}}, max_total="28",
        )  # fmt: skip
        assert services.validate_paper(paper) == []
        assert services.answerable_total(paper) == Decimal(28)  # best 4 of 6 questions x 7 marks


def test_a3_the_see_paper_best_5_of_q11_to_q17_and_best_2_of_q17(db: None) -> None:
    college = make_college("a")
    s = _course(college)
    with college_context(college.id):
        paper = services.create_paper(
            s.offering, "SEE", "SEE", B.QUESTION_WISE, _see_spec(),
            groups={"G": {"best_n": 5, "best_k_parts": {"17": 2}}},
        )  # fmt: skip
        assert paper.parts.count() == 25
        assert services.validate_paper(paper) == []
        # 10 compulsory x 2 = 20; best five choice questions: Q11..Q16 are 8 each, Q17 best 2 = 8
        assert services.answerable_total(paper) == Decimal(20 + 5 * 8)


def test_a3_problems_are_reported_in_plain_words(db: None) -> None:
    college = make_college("a")
    s = _course(college)
    with college_context(college.id):
        spec = [
            _q("1", [("a", "5", None)]),  # no CO tag
            _q("2", [("a", "5", "CO1")], "G"),
            _q("3", [("a", "5", "CO1"), ("b", "5", "CO1")], "G"),
        ]
        paper = services.create_paper(
            s.offering, "T", "Test", B.QUESTION_WISE, spec,
            groups={"G": {"best_n": 3, "best_k_parts": {"3": 4, "9": 1}}}, max_total="99",
        )  # fmt: skip
        problems = " | ".join(services.validate_paper(paper))
        assert "Part 1a has no CO tag" in problems
        assert "best 3 is more than its 2 questions" in problems
        assert "best 4 parts of question 3 is more than its 2 parts" in problems
        assert "question 9 is not in the group" in problems
        assert "total" not in problems  # totals are checked only once the structure is sound


def test_a3_total_mismatch_and_empty_paper(db: None) -> None:
    college = make_college("a")
    s = _course(college)
    with college_context(college.id):
        paper = services.create_paper(
            s.offering, "T", "Test", B.QUESTION_WISE, [_q("1", [("a", "5", "CO1")])], max_total="6"
        )
        assert "can score at most 5" in services.validate_paper(paper)[0]
        empty = services.create_paper(s.offering, "E", "Empty", B.QUESTION_WISE, [])
        assert services.validate_paper(empty) == ["The paper has no parts."]


def test_quiz_items_have_no_co_tag_and_that_is_fine(db: None) -> None:
    college = make_college("a")
    s = _course(college)
    with college_context(college.id):
        items = [_q(str(k), [("", "5", None)]) for k in (1, 2, 3)]
        paper = services.create_paper(s.offering, "QUIZ", "Quiz", B.PER_STUDENT_AVERAGE, items)
        assert services.validate_paper(paper) == []


def test_a_co_of_another_course_is_refused(db: None) -> None:
    college = make_college("a")
    s = _course(college, n_cos=2)
    with college_context(college.id):
        with pytest.raises(ValidationError, match="CO4"):
            services.create_paper(
                s.offering, "T", "Test", B.QUESTION_WISE, [_q("1", [("a", "5", "CO4")])]
            )
        with pytest.raises(ValidationError, match="unknown choice group"):
            services.create_paper(
                s.offering, "T2", "Test", B.QUESTION_WISE, [_q("1", [("a", "5", "CO1")], "Z")]
            )


# A4 -------------------------------------------------------------------------------------------
def _paper_with_part(college):  # type: ignore[no-untyped-def]
    s = _course(college)
    iqac = make_user(college, "a.iqac")
    coordinator = make_user(college, "a.coordinator")
    lecturer = make_user(college, "a.lecturer")
    with college_context(college.id):
        assign_role(iqac, Role.IQAC)
        assign_role(coordinator, Role.COORDINATOR)
        paper = services.create_paper(
            s.offering, "INT2", "Internal-II", B.QUESTION_WISE, [_q("1", [("a", "3.5", "CO1")])]
        )
        part = paper.parts.get()
    return s, paper, part, iqac, coordinator, lecturer


def test_a4_override_needs_a_reason_and_a_sensible_pass_mark(db: None) -> None:
    college = make_college("a")
    _, _, part, _, coordinator, _ = _paper_with_part(college)
    with college_context(college.id):
        with pytest.raises(ValidationError, match="reason"):
            services.set_override(part, "2", "   ", coordinator)
        with pytest.raises(ValidationError, match="between 0 and 3.50"):
            services.set_override(part, "4", "typo", coordinator)
        with pytest.raises(IntegrityError), transaction.atomic():
            QuestionPart.objects.filter(pk=part.pk).update(override_pass_mark=2)  # no reason


def test_a4_an_unapproved_override_is_not_used_by_the_engine(db: None) -> None:
    from engine.loader import load_course
    from engine.pipeline import run
    from engine.schema import load_method

    college = make_college("a")
    s, paper, part, iqac, coordinator, lecturer = _paper_with_part(college)
    method = load_method(json.dumps({
        "schema": "attainment-method/1", "name": "t",
        "levels": {"bands": [{"min_pct": 0, "level": 1}, ]},
        "tools": {"INT2": {"behaviour": "question_wise", "pass_pct": 60}},
        "direct": {"INT2": 1}, "final": {"direct": 1, "indirect": 0},
    }))  # fmt: skip

    def engine_percent(use: dict) -> Decimal:  # type: ignore[type-arg]
        with college_context(college.id):
            parts = services.engine_parts(paper)
        marks = {f"s{i}": {"1a": 2} for i in range(4)}
        overrides = [
            {"tool": t, "part": p, "pass_mark": str(v[0]), "reason": v[1]}
            for (t, p), v in use.items()
        ]
        text = json.dumps({"cos": ["CO1"], "students": list(marks), "overrides": overrides,
                           "assessments": {"INT2": {"parts": parts, "marks": marks}}})  # fmt: skip
        return run(method, load_course(text)).result.tool_values["INT2"]["CO1"].percent  # type: ignore[return-value]

    with college_context(college.id):
        services.set_override(part, "2", "college practice", coordinator)
        pending = services.approved_overrides(s.offering)
    assert pending == {}  # waiting for IQAC: not handed to the engine
    assert engine_percent(pending) == 0  # a mark of 2 fails the default 60% of 3.5 = 2.1

    with college_context(college.id):
        with pytest.raises(PermissionDenied):
            services.decide_override(part, lecturer, approve=True)  # a lecturer cannot approve
        with pytest.raises(PermissionDenied):
            services.decide_override(part, coordinator, approve=True)
        services.decide_override(part, iqac, approve=True)
        approved = services.approved_overrides(s.offering)
    assert approved == {("INT2", "1a"): (Decimal("2.00"), "college practice")}
    assert engine_percent(approved) == 100


def test_a4_rejected_or_changed_overrides_are_not_used(db: None) -> None:
    college = make_college("a")
    s, _, part, iqac, coordinator, _ = _paper_with_part(college)
    with college_context(college.id):
        services.set_override(part, "2", "first", coordinator)
        services.decide_override(part, iqac, approve=False)
        assert services.approved_overrides(s.offering) == {}
        with pytest.raises(ValidationError, match="waiting"):
            services.decide_override(part, iqac, approve=True)  # nothing is pending any more
        services.set_override(part, "2", "second try", coordinator)
        services.decide_override(part, iqac, approve=True)
        assert len(services.approved_overrides(s.offering)) == 1
        services.set_override(part, "1.5", "changed my mind", coordinator)
        assert services.approved_overrides(s.offering) == {}  # a new proposal needs approval again


# copying and importing ---------------------------------------------------------------------------
def test_copy_a_paper_to_next_years_offering_without_the_overrides(db: None) -> None:
    college = make_college("a")
    s, paper, part, iqac, coordinator, _ = _paper_with_part(college)
    with college_context(college.id):
        services.set_override(part, "2", "college practice", coordinator)
        services.decide_override(part, iqac, approve=True)
        # next year: the same course, a new term
        from apps.academics.models import AcademicYear, Term

        year = AcademicYear.objects.create(
            label="2026-27", start_date="2026-06-01", end_date="2027-05-31"
        )
        term = Term.objects.create(academic_year=year, number=6)
        next_offering = CourseOffering.objects.create(course=s.course, term=term)
        copy = services.copy_paper(paper, next_offering)
        copied = copy.parts.get()
        assert (
            copy.offering == next_offering and copied.code == "1a" and copied.max == Decimal("3.50")
        )
        assert copied.co.code == "CO1" and copied.override_status == "none"  # fresh approval needed
        assert services.approved_overrides(next_offering) == {}


def test_copy_needs_the_target_course_to_have_the_same_outcomes(db: None) -> None:
    college = make_college("a")
    s, paper, *_ = _paper_with_part(college)
    with college_context(college.id):
        other = Course.objects.create(title="Another course (synthetic)")
        offering = CourseOffering.objects.create(course=other, term=s.term)
        with pytest.raises(ValidationError, match="no CO1"):
            services.copy_paper(paper, offering)


def test_a8_engine_format_import_keeps_parts_maxima_co_tags_and_choice_rules(db: None) -> None:
    from engine.loader import load_course
    from engine.model import State
    from engine.schema import ChoiceRule
    from engine.steps.choice import choice_select
    from engine.steps.normalise import normalise_states
    from engine.trace import Trace

    college = make_college("a")
    s = _course(college)
    with college_context(college.id):
        built = services.create_paper(
            s.offering, "SEE", "SEE", B.QUESTION_WISE, _see_spec(),
            groups={"G": {"best_n": 5, "best_k_parts": {"17": 2}}},
        )  # fmt: skip
        parts = services.engine_parts(built)
        rules = services.engine_choice_rules(built)
        imported = services.import_engine_paper(
            s.offering, "SEE2", "SEE copy", B.QUESTION_WISE, parts, choice_rules=rules
        )
        assert imported.parts.count() == 25 and services.validate_paper(imported) == []
        assert [p.max for p in imported.parts.all()] == [p.max for p in built.parts.all()]
        assert (
            services.engine_choice_rules(imported)
            == rules
            == {"G": {"best_n": 5, "best_k_parts": {"17": 2}}}
        )
        # the stored paper drives the engine's ChoiceSelect: a student with 6 answers loses Q17
        row = {p["id"]: None for p in parts}
        for n in range(11, 17):
            row[f"{n}a"] = 4
        row["17a"] = 1
        body = {"parts": parts, "marks": {"x": row}}
        cos = [f"CO{i}" for i in range(1, 6)]
        text = json.dumps({"cos": cos, "students": ["x"], "assessments": {"SEE": body}})
        assessment = load_course(text).assessments["SEE"]
    trace = Trace()
    cells = choice_select(
        assessment, normalise_states(assessment, "exclude", trace, False),
        {code: ChoiceRule.model_validate(rule) for code, rule in rules.items()}, trace,
    )  # fmt: skip
    dropped = {p for p, c in cells["x"].items() if c.state is State.DROPPED}
    assert "17a" in dropped and "Q17" in trace.text()


DS_A = Path(__file__).resolve().parents[3] / "engine" / "tests" / "golden" / "ds_a" / "course.json"


@pytest.mark.skipif(not DS_A.exists(), reason="DS-A not present: run scripts/build_ds_a.py")
def test_a8_the_deep_learning_papers_import_with_14_12_and_25_parts(db: None) -> None:
    raw = json.loads(DS_A.read_text(encoding="utf-8"))
    college = make_college("a")
    s = _course(college)
    expected = {"INT1": 14, "INT2": 12, "SEE": 25}
    with college_context(college.id):
        for tool, count in expected.items():
            parts = raw["assessments"][tool]["parts"]
            groups = (
                {"G": {"best_n": 5, "best_k_parts": {"17": 2}}}
                if tool == "SEE"
                else {"G": {"best_n": 4}}
            )
            paper = services.import_engine_paper(
                s.offering, tool, tool, B.QUESTION_WISE, parts,
                choice_rules=groups if any(p.get("choice_group") for p in parts) else None,
            )  # fmt: skip
            assert paper.parts.count() == count
            assert [str(p.max) for p in paper.parts.all()] == [
                f"{float(p['max']):.2f}" for p in parts
            ]
            assert services.validate_paper(paper) == []
