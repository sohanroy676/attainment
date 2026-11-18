"""v1.0.0 A1: the acceptance suite, one named test for each of the 20 scenarios
(project statement section 15, design 16.2).

Each test goes through the real code paths (engine, services, screens). The data is synthetic.
Scenarios 1 and 2 are checked against hand-worked numbers here, and against the mentor's real
workbooks as well when the anonymised DS-A and DS-B files are present (otherwise that second half
is reported in `docs/test-reports/v1.0.0.md` as still owed, not as passed).
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client

from apps.academics.models import AcademicYear, CourseOffering, Section, Term
from apps.academics.tests.helpers import make_structure
from apps.accounts.tests.helpers import PASSWORD, make_college
from apps.assessments import services as papers
from apps.assessments.models import QuestionPart
from apps.imports import services as imports
from apps.imports.models import ImportBatch
from apps.marks import importer
from apps.marks import services as marks
from apps.marks.models import MarkCell
from apps.methodology import services as methods
from apps.reports import context
from apps.results import services as results
from apps.results.present import present
from apps.roster import services as roster
from apps.roster.models import Student
from apps.tenancy.services import college_context
from apps.workflow.tests.helpers import make_wf_env, signed
from engine.model import State
from engine.pipeline import run
from engine.schema import ChoiceRule
from engine.steps.choice import choice_select
from engine.steps.normalise import normalise_states
from engine.tests.builders import assessment, class_with_pass_rate, course, parts, simple_method
from engine.tests.test_second_method import _data as college_b_data
from engine.tests.test_second_method import _method as college_b_method
from engine.trace import Trace

D = Decimal
GOLDEN = Path(__file__).resolve().parents[2] / "engine" / "tests" / "golden"
ONE_TOOL = {"direct": "1", "indirect": "0"}
QW = {"behaviour": "question_wise", "pass_pct": 60, "boundary": ">="}


def _percent(out, tool: str = "T", co: str = "CO1") -> Decimal:  # type: ignore[no-untyped-def]
    value = out.result.tool_values[tool][co].percent
    assert value is not None
    return value


def _one_tool(**changes: object):  # type: ignore[no-untyped-def]
    return simple_method({"T": {**QW, **changes}}, {"T": "1"}, final=ONE_TOOL)


def _csv(rows: list[tuple[str, str]]) -> bytes:
    return ("roll_no,name\n" + "\n".join(f"{r},{n}" for r, n in rows) + "\n").encode()


def _import(section: Section, rows: list[tuple[str, str]], scope: str = "section") -> None:
    batch = imports.preview_roster(section, "roster.csv", _csv(rows), scope=scope)
    assert batch.status == ImportBatch.Status.PREVIEWED, batch.report
    imports.commit_roster(batch)


# 1 -----------------------------------------------------------------------------------------
@pytest.mark.integration
def test_scenario_01_reference_course_end_to_end(db: None) -> None:
    """A course from marks to a course attainment, hand-worked (2.92, CO1 2.84). With DS-A
    present the real Deep Learning numbers (R1 2.18 not attained, R2 2.32 attained) are checked
    by `pytest -m golden`."""
    w = make_wf_env()
    with college_context(w.college.id):
        shown = present(results.calculate(w.offering, w.programme))
        assert shown.course_text == "2.92" and shown.attained is True
        final = dict(next(t for t in shown.tables if t.title == "Course outcomes").rows)["Final"]
        assert [c.text for c in final] == ["2.84", "3.00"]
    if (GOLDEN / "ds_a" / "course.json").exists():
        from engine.tests.golden.test_golden import _run

        assert _run(overrides=False)[1].course is not None


# 2 -----------------------------------------------------------------------------------------
@pytest.mark.integration
def test_scenario_02_reference_batch_rolls_up_from_signed_courses(db: None) -> None:
    w = make_wf_env()
    batch = w.env.s.batch
    with college_context(w.college.id):
        results.set_batch_indirect(batch, {"PO1": "3", "PO2": "3"}, "test", w.r.iqac)
        signed(w)
        run_ = results.calculate_batch(batch, w.r.iqac)
        count, direct, *_ = run_.outputs["outcomes"]["PO1"]
        assert count == 1 and D(direct).quantize(D("0.0001")) == D("2.8933")  # (2*2.84+3)/3


# 3 -----------------------------------------------------------------------------------------
@pytest.mark.integration
def test_scenario_03_gaps_ranges_and_alphanumeric_ids(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        _import(s.section_a, [(str(n), f"Student {n}") for n in (1, 2, 3, 4, 6, 7, 8)])
        assert (
            Student.objects.count() == 7
            and roster.find_by_identifier("5", section=s.section_a) is None
        )
    other = make_college("b")
    t = make_structure(other)
    with college_context(other.id):
        _import(t.section_a, [(str(n), f"A{n}") for n in range(1, 101)])
        _import(t.section_b, [(str(n), f"B{n}") for n in range(1, 90)])
        assert roster.enrolled_students(t.offering, t.section_a).count() == 100
        assert roster.enrolled_students(t.offering, t.section_b).count() == 89
    third = make_college("c")
    u = make_structure(third)
    with college_context(third.id):
        _import(u.section_a, [(str(n), f"A{n}") for n in range(1, 67)], scope="batch")
        _import(u.section_b, [(str(n), f"B{n}") for n in range(67, 131)], scope="batch")
        _import(u.section_a, [("1602-23-748-001", "Alpha")], scope="batch")
        assert roster.find_by_identifier("1602-23-748-001", batch=u.batch) is not None


# 4 -----------------------------------------------------------------------------------------
@pytest.mark.integration
def test_scenario_04_same_roll_number_in_two_sections_is_two_students(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        _import(s.section_a, [("1", "Asha")])
        _import(s.section_b, [("1", "Bala")])
        assert Student.objects.count() == 2
        one = roster.find_by_identifier("1", section=s.section_a)
        two = roster.find_by_identifier("1", section=s.section_b)
        assert one is not None and two is not None and one.pk != two.pk


# 5 -----------------------------------------------------------------------------------------
@pytest.mark.integration
def test_scenario_05_withdrawal_and_section_change_keep_history(db: None) -> None:
    w = make_wf_env()
    env = w.env
    with college_context(w.college.id):
        base = results.calculate(w.offering, w.programme)
        mover, leaver = env.enrolments_a[0], env.enrolments_a[1]
        roster.move_section(mover, env.s.section_b, on=date(2025, 8, 1), reason="timetable")
        roster.withdraw(leaver, on=date(2025, 9, 1), reason="left the college")
        mover.refresh_from_db()
        assert mover.section == env.s.section_b  # where marks count follows the enrolment
        assert mover.student.sections.count() == 2  # the old membership is closed, not deleted
        assert leaver.student.enrolments.filter(status="withdrawn").count() == 1  # history kept
        after = results.calculate(w.offering, w.programme)
        assert after.input_hash != base.input_hash  # the inclusion rule changed the input
        built = results.build(w.offering, w.programme).offering_input
        counts = {name: len(sec.students) for name, sec in built.sections.items()}
        assert counts == {"A": 3, "B": 3}  # 5 - 1 withdrawn - 1 moved; 2 + 1 moved


# 6 -----------------------------------------------------------------------------------------
@pytest.mark.unit
def test_scenario_06_blank_zero_and_absent_are_three_states() -> None:
    paper = parts([("p", "1", 4, "CO1", "G")])
    rows = {"zero": {"p": 0}, "blank": {"p": None}, "gone": {"p": "A"}, "ok": {"p": 4}}
    kept = normalise_states(assessment("T", paper, rows), "exclude", Trace(), False)
    assert kept["blank"]["p"].state is State.BLANK  # blank is never turned into 0
    raw = assessment("T", paper, rows).marks
    assert raw["gone"]["p"].state is State.ABSENT  # three different states on entry
    assert kept["gone"]["p"].state is State.BLANK  # "exclude": absent is left out, not a 0
    assert kept["zero"]["p"].state is State.ENTERED and kept["zero"]["p"].value == 0
    as_zero = normalise_states(assessment("T", paper, rows), "zero", Trace(), False)
    assert as_zero["gone"]["p"].value == 0 and as_zero["blank"]["p"].state is State.BLANK
    skip = run(_one_tool(absent="exclude"), course([assessment("T", paper, rows)]))
    assert _percent(skip) == 50  # absent and blank left out: one fail, one pass
    # quiz: an absent item counts as 0 when the method says so
    quiz = parts([(f"i{k}", str(k), 5, None, None) for k in range(3)])
    quiz_rows = {"full": {"i0": 5, "i1": 5, "i2": 5}, "mostly": {"i0": 5, "i1": "A", "i2": "A"}}
    method = simple_method(
        {"T": {"behaviour": "per_student_average", "max": 5, "pass_pct": 60, "absent": "zero"}},
        {"T": "1"},
        final=ONE_TOOL,
    )
    assert _percent(run(method, course([assessment("T", quiz, quiz_rows)]))) == 50


# 7 -----------------------------------------------------------------------------------------
@pytest.mark.unit
def test_scenario_07_exactly_60_percent_passes_and_the_boundary_is_a_setting() -> None:
    paper = parts([("p", "1", 3, "CO1", None)])
    data = course([assessment("T", paper, {f"s{i}": {"p": "1.8"} for i in range(3)})])
    assert _percent(run(_one_tool(boundary=">="), data)) == 100
    assert _percent(run(_one_tool(boundary=">"), data)) == 0
    assert _percent(run(_one_tool(pass_pct=61), data)) == 0  # changing the pass mark changes it too


# 8 -----------------------------------------------------------------------------------------
@pytest.mark.unit
def test_scenario_08_best_five_of_seven_with_q17_best_two() -> None:
    spec = [(f"{n}{s}", str(n), 4, "CO1", "G") for n in range(11, 17) for s in "ab"]
    spec += [(f"17{s}", "17", 4, "CO1", "G") for s in "abc"]
    paper = parts(spec)

    def dropped(row: dict[str, int]) -> set[str]:
        a = assessment("SEE", paper, {"x": {p.id: row.get(p.id) for p in paper}})
        out = choice_select(
            a,
            normalise_states(a, "exclude", Trace(), False),
            {"G": ChoiceRule(best_n=5, best_k_parts={"17": 2})},
            Trace(),
        )
        return {p for p, c in out["x"].items() if c.state is State.DROPPED}

    full = {"11a": 4, "11b": 4, "12a": 3, "12b": 3, "13a": 2, "13b": 2, "14a": 2, "14b": 2,
            "15a": 1, "15b": 1, "17a": 4, "17b": 1, "17c": 3}  # fmt: skip
    assert dropped(full) == {"17b", "15a", "15b"}  # best 2 of Q17's parts; Q15 is the weakest
    four = {"11a": 4, "12a": 4, "13a": 4, "14a": 4}  # attempted only four: nothing is dropped
    assert dropped(four) == set()


# 9 -----------------------------------------------------------------------------------------
@pytest.mark.unit
def test_scenario_09_shared_co_across_two_internals_is_averaged() -> None:
    cfg = {"behaviour": "question_wise", "pass_pct": 60}
    method = simple_method(
        {"INT1": cfg, "INT2": cfg},
        {"INTERNAL": "1"},
        merge={"INTERNAL": {"from": ["INT1", "INT2"]}},
    )
    data = course([class_with_pass_rate("INT1", 10, 10), class_with_pass_rate("INT2", 5, 10)])
    assert run(method, data).result.merged["INTERNAL"]["CO1"].value == D("2.5")  # (3 + 2) / 2


# 10 ----------------------------------------------------------------------------------------
@pytest.mark.unit
def test_scenario_10_quiz_and_assignment_level_applies_to_every_co() -> None:
    quiz = parts([(f"i{k}", str(k), 5, None, None) for k in range(2)])
    rows = {f"s{i}": {"i0": 5, "i1": 5} for i in range(4)}
    method = simple_method(
        {"QUIZ": {"behaviour": "per_student_average", "max": 5, "pass_pct": 60}},
        {"QUIZ": "1"},
        final=ONE_TOOL,
    )
    out = run(method, course([assessment("QUIZ", quiz, rows)], cos=("CO1", "CO2", "CO3")))
    assert {co: out.result.tool_values["QUIZ"][co].level for co in ("CO1", "CO2", "CO3")} == {
        "CO1": D(3), "CO2": D(3), "CO3": D(3)
    }  # fmt: skip


# 11 ----------------------------------------------------------------------------------------
@pytest.mark.unit
def test_scenario_11_below_ten_percent_is_flagged_and_gets_no_level() -> None:
    paper = parts([("p", "1", 10, "CO1", None)])
    rows = {f"s{i}": {"p": 10 if i == 0 else 0} for i in range(20)}  # 5% pass
    out = run(_one_tool(), course([assessment("T", paper, rows)]))
    value = out.result.tool_values["T"]["CO1"]
    assert value.status == "blocked" and value.level is None and value.flag is not None
    assert out.result.complete is False  # stop for review, not a silent 0


# 12 ----------------------------------------------------------------------------------------
@pytest.mark.integration
def test_scenario_12_two_sections_average_to_the_course_result(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        out = results.calculate(w.offering, w.programme).outputs
        a, b = (out["sections"][n]["final"]["CO1"][0] for n in ("A", "B"))
        assert (D(a), D(b)) == (D("3"), D("2.68"))
        assert D(out["course"]["final"]["CO1"][0]) == (D(a) + D(b)) / 2 == D("2.84")


# 13 ----------------------------------------------------------------------------------------
@pytest.mark.integration
def test_scenario_13_override_needs_a_role_and_a_reason_and_shows_in_the_report(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        part = QuestionPart.objects.get(assessment=w.env.internal, code="1a")
        with pytest.raises(ValidationError, match="needs a reason"):
            papers.set_override(part, "2", "  ", w.r.hod)
        papers.set_override(part, "2", "as used by the college in 2025-26", w.r.hod)
        assert papers.approved_overrides(w.offering) == {}  # pending is never used
        papers.decide_override(part, w.r.iqac, approve=True)
        assert papers.approved_overrides(w.offering)[("INT1", "1a")][1].startswith("as used")
        results.calculate(w.offering, w.programme)
        report = context.course_report(w.offering, w.programme)
        assert report is not None
        assert ("INT1", "1a", "2", "as used by the college in 2025-26") in report.overrides
        with pytest.raises(PermissionDenied):
            papers.decide_override(part, w.env.lecturer_a, approve=True)


# 14 ----------------------------------------------------------------------------------------
@pytest.mark.integration
def test_scenario_14_a_new_method_version_applies_to_later_periods_only(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        v1 = methods.create_from_template("vasavi_theory")
        methods.activate(v1, date(2025, 6, 1))
        v2 = methods.new_draft_from(v1)
        raw = json.loads(v1.config_text)
        raw["missing_data"] = "renormalise"
        methods.update_draft(v2, json.dumps(raw))
        methods.activate(v2, date(2026, 6, 1))
        methods.assign_method("college", v1.method)
        year = AcademicYear.objects.create(
            label="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31)
        )
        later = CourseOffering.objects.create(
            course=s.course, term=Term.objects.create(academic_year=year, number=6)
        )
        assert methods.method_for_offering(s.offering)[0].number == 1  # earlier result keeps v1
        assert methods.method_for_offering(later)[0].number == 2


# 15 ----------------------------------------------------------------------------------------
@pytest.mark.integration
def test_scenario_15_incomplete_data_is_provisional(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        from apps.results.models import IndirectValue

        IndirectValue.objects.filter(offering=w.offering, co_code="CO2").delete()
        run_ = results.calculate(w.offering, w.programme)
        assert run_.status == "provisional"
        assert any("No indirect value has been entered for CO2" in line for line in run_.checklist)
        report = context.course_report(w.offering, w.programme)
        assert report is not None and report.footer.provisional


# 16 ----------------------------------------------------------------------------------------
@pytest.mark.unit
def test_scenario_16_a_second_method_is_only_configuration() -> None:
    out = run(college_b_method(), college_b_data())
    assert out.result.complete and out.result.course is not None  # no code change, no new step
    again = run(college_b_method(), college_b_data())
    assert again.result.course == out.result.course  # deterministic
    vasavi = json.loads((GOLDEN / "method_r1.json").read_text(encoding="utf-8"))
    assert college_b_method().model_dump(mode="json") != vasavi  # genuinely a different method


# 17 ----------------------------------------------------------------------------------------
@pytest.mark.integration
def test_scenario_17_a_saved_configuration_serves_the_next_term_without_setup(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        v1 = methods.create_from_template("vasavi_theory")
        methods.activate(v1, date(2025, 6, 1))
        methods.assign_method("college", v1.method)
        year = AcademicYear.objects.create(
            label="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31)
        )
        later = CourseOffering.objects.create(
            course=s.course, term=Term.objects.create(academic_year=year, number=6)
        )
        assert methods.method_for_offering(later)[0].pk == v1.pk  # nothing was configured for it


# 18 ----------------------------------------------------------------------------------------
@pytest.mark.integration
def test_scenario_18_a_bad_import_reports_the_rows_and_stores_nothing(db: None) -> None:
    from apps.marks.tests.helpers import make_env

    env = make_env()
    content = b"roll_no,1a,1b\n1,3,2\n99,1,1\n2,5,1\n"
    with college_context(env.college.id):
        batch = importer.preview_marks(
            env.internal, env.s.section_a, "m.csv", content, env.lecturer_a
        )
        assert batch.status == ImportBatch.Status.REJECTED
        errors = dict(batch.report["error_rows"])
        assert (
            "99 is not on this section's roster" in errors[3] and "above the maximum" in errors[4]
        )
        assert MarkCell.objects.count() == 0  # the valid row 2 was not written either


# 19 ----------------------------------------------------------------------------------------
@pytest.mark.integration
def test_scenario_19_one_college_cannot_see_anothers_records(committed_db: None) -> None:
    a = make_wf_env("a")
    b = make_wf_env("b")
    foreign = Client()
    assert (
        foreign.post("/accounts/login/", {"username": "b.iqac", "password": PASSWORD}).status_code
        == 302
    )
    for url in (
        f"/results/{a.offering.pk}/",
        f"/reports/course/{a.offering.pk}/analysis.html",
        f"/marks/{a.env.internal.pk}/{a.env.s.section_a.pk}/",
        f"/workflow/{a.offering.pk}/{a.programme.pk}/",
    ):
        assert foreign.get(url).status_code in (403, 404), url
    with college_context(b.college.id):
        assert not Student.objects.filter(pk=a.env.enrolments_a[0].student_id).exists()
        assert Student.objects.count() == 7  # only its own seven
    with college_context(None):
        assert Student.objects.count() == 0  # no college set: nothing is visible


# 20 ----------------------------------------------------------------------------------------
@pytest.mark.integration
def test_scenario_20_a_signed_report_does_not_change_when_later_marks_change(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        signed(w)
        frozen = results.signed_run(w.offering, w.programme)
        assert frozen is not None and frozen.signed
        before = context.course_report_for(w.offering, w.programme, frozen).footer.content_hash
        with pytest.raises(
            (ValidationError, PermissionDenied, DatabaseError)
        ):  # the marks are locked
            part = w.env.internal.parts.get(code="1a")
            cell = MarkCell.objects.filter(row__assessment=w.env.internal, part=part).first()
            with transaction.atomic():
                marks.save_cell(
                    cell.row, part, "value", D("0"), w.env.lecturer_a, cell.row_version, reason="x"
                )
        with (
            pytest.raises(DatabaseError, match="frozen"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "UPDATE results_calculationrun SET outputs = '{}'::jsonb WHERE id = %s",
                [str(frozen.pk)],
            )
        frozen.refresh_from_db()
        after = context.course_report_for(w.offering, w.programme, frozen).footer.content_hash
        assert before == after == frozen.content_hash
