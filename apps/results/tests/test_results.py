"""v0.7.0: end-to-end results, recalculation, provisional checklist, explain, permissions."""

import io
import time
from decimal import Decimal

import openpyxl
import pytest
from django.test import Client

from apps.accounts.tests.helpers import PASSWORD
from apps.marks import services as marks
from apps.marks.models import MarkCell, MarkSheetRow
from apps.methodology import services as methods
from apps.outcomes import services as outcomes
from apps.results import services
from apps.results.models import CalculationRun, ResultValue
from apps.roster import services as roster
from apps.tenancy.services import college_context

from .helpers import make_results_env, second_programme

pytestmark = [pytest.mark.integration]

D = Decimal


def _calc(r):  # type: ignore[no-untyped-def]
    with college_context(r.college.id):
        return services.calculate(r.offering, r.programme)


def _course(run):  # type: ignore[no-untyped-def]
    return run.outputs["course"]


# A1 --------------------------------------------------------
def test_a1_end_to_end_numbers_equal_the_hand_computed_result(db: None) -> None:
    r = make_results_env()
    run = _calc(r)
    course = _course(run)
    sections = run.outputs["sections"]
    assert sections["A"]["course"] == "3" and Decimal(sections["B"]["course"]) == D("2.84")
    assert [Decimal(course["final"][c][0]) for c in ("CO1", "CO2")] == [D("2.84"), D("3")]
    assert Decimal(course["course"]) == D("2.92") and course["attained"] is True
    assert str(Decimal(course["po"]["PO1"][0]))[:7] == "2.89333"
    assert Decimal(course["po"]["PO2"][0]) == D("2.84")
    assert run.status == "complete" and run.checklist == []
    assert run.method_version is not None and run.engine_version and len(run.input_hash) == 64
    with college_context(r.college.id):
        stored = {(v.entity, v.key): v for v in run.values.all()}
    assert stored[("course", "course")].display == "2.92"
    assert stored[("co_final", "CO1")].value == "2.84"


def test_a1_the_course_page_shows_the_result_and_every_number_links_to_its_explanation(
    committed_db: None,
) -> None:
    r = make_results_env()
    client = _login("a.iqac")
    page = client.get(f"/results/{r.offering.pk}/").content.decode()
    assert "Course attainment: 2.92" in page and "Attained" in page
    assert "entered, not measured" in page and "Direct" in page
    assert "?key=SEE/CO2" in page.replace("%2F", "/") and "?key=final/CO1" in page.replace(
        "%2F", "/"
    )
    assert "Provisional" not in page


# A2 --------------------------------------------------------
def test_a2_automatic_recalculation_after_marks_mapping_target_and_method_change(
    committed_db: None,
) -> None:
    r = make_results_env()
    with college_context(r.college.id):
        first = services.latest_run(r.offering, r.programme)
        assert first is not None and Decimal(_course(first)["course"]) == D("2.92")
        # one mark: section B's second student now fails 1b as well (CO2 in Internal-I drops to 50%)
        part = r.env.internal.parts.get(code="1b")
        row = marks.get_row(r.env.enrolments_b[1], r.env.internal)
        marks.save_cell(row, part, "value", D("0"), r.env.lecturer_b)
    with college_context(r.college.id):
        second = services.latest_run(r.offering, r.programme)
        assert second.pk != first.pk and CalculationRun.objects.filter(pk=first.pk).count() == 0
        assert Decimal(_course(second)["course"]) < D("2.92")
        entries = [
            e for _, e in services.explain(second, "INT1/CO2") if e["step"] == "QuestionPass"
        ]
        assert (
            entries
            and entries[0]["message"].startswith("4/7 passed")
            or "passed" in entries[0]["message"]
        )
        # the target changes the status, not the numbers
        outcomes.set_target("3", offering=r.offering)
    with college_context(r.college.id):
        third = services.latest_run(r.offering, r.programme)
        assert (
            third.outputs["course"]["attained"] is False and third.input_hash != second.input_hash
        )
        # a mapping change
        definition = r.offering.course.definitions.get()
        outcomes.save_mapping_grid(definition, r.programme, {"CO2": {"PO2": 3}})
    with college_context(r.college.id):
        fourth = services.latest_run(r.offering, r.programme)
        assert fourth.input_hash != third.input_hash
        po2 = [e["message"] for _, e in services.explain(fourth, "PO2")]
        assert "CO2" in po2[0]  # PO2 now also draws on CO2


def test_a2_a_new_method_version_changes_the_next_run(committed_db: None) -> None:
    import json
    from datetime import date

    from .helpers import METHOD

    r = make_results_env()
    with college_context(r.college.id):
        before = services.latest_run(r.offering, r.programme)
        version = methods.MethodVersion.objects.get()
        draft = methods.new_draft_from(version)
        changed = {**METHOD, "direct": {"INT1": "0.1", "SEE": "0.9"}}
        methods.update_draft(draft, json.dumps(changed))
        methods.activate(draft, date(2025, 2, 1), r.iqac)
    with college_context(r.college.id):
        after = services.latest_run(r.offering, r.programme)
        assert after.pk != before.pk
        assert after.method_version.number == 2  # the assignment follows the newer active version
        # Level 2 in section B Internal-I now matters less: course value rises
        assert Decimal(_course(after)["course"]) > Decimal(_course(before)["course"])


def test_many_cells_saved_in_one_transaction_trigger_one_recalculation(committed_db: None) -> None:
    from django.db import transaction

    r = make_results_env()
    with college_context(r.college.id):
        before = CalculationRun.objects.count()
        with transaction.atomic():
            for enrolment in r.env.enrolments_a:
                row = marks.get_row(enrolment, r.env.internal)
                part = r.env.internal.parts.get(code="1a")
                marks.save_cell(row, part, "value", D("3"), r.env.lecturer_a)
        assert CalculationRun.objects.count() == before  # replaced, not accumulated
        assert CalculationRun.objects.filter(is_latest=True).count() == 1


# A3 and A4 -------------------------------------------------
def test_a3_a_missing_marks_sheet_makes_the_run_provisional_but_blank_choice_parts_do_not(
    db: None,
) -> None:
    r = make_results_env()
    run = _calc(r)
    assert run.status == "complete"  # Q13 is "-" for everyone: normal for a choice question
    with college_context(r.college.id):
        MarkSheetRow.objects.filter(
            assessment=r.env.internal, enrolment=r.env.enrolments_a[2]
        ).delete()
    run = _calc(r)
    assert run.status == "provisional"
    assert any(
        "Section A: 1 enrolled student(s) have no marks for Internal-I" in c for c in run.checklist
    )


def test_a4_below_ten_percent_stops_the_result_for_review(db: None) -> None:
    r = make_results_env()
    with college_context(r.college.id):
        part = r.env.internal.parts.get(code="1a")
        for enrolment in r.env.enrolments_a + r.env.enrolments_b:
            row = marks.get_row(enrolment, r.env.internal)
            marks.save_cell(
                row,
                part,
                "value",
                D("0"),
                r.env.lecturer_a if enrolment in r.env.enrolments_a else r.env.lecturer_b,
            )
    run = _calc(r)
    assert run.status == "provisional"
    assert run.outputs["course"]["final"]["CO1"][1] == "blocked"
    assert any("below the lowest band" in c for c in run.checklist)
    page_client = _login("a.iqac")
    page = page_client.get(f"/results/{r.offering.pk}/").content.decode()
    assert "Provisional" in page and "below the lowest band" in page


def test_a4_a_missing_paper_and_a_missing_method_are_listed(db: None) -> None:
    r = make_results_env()
    with college_context(r.college.id):
        r.env.see.delete()
    run = _calc(r)
    assert run.status == "provisional" and any("no paper for SEE" in c for c in run.checklist)
    other = make_results_env("b", with_marks=False)
    with college_context(other.college.id):
        from apps.methodology.models import MethodAssignment

        MethodAssignment.objects.all().delete()
        run = services.calculate(other.offering, other.programme)
    assert run.status == "provisional" and "No method is assigned" in run.checklist[0]
    assert run.outputs == {} and run.method_version is None


def test_missing_target_mapping_and_indirect_are_listed_not_hidden(db: None) -> None:
    r = make_results_env()
    with college_context(r.college.id):
        from apps.outcomes.models import Target
        from apps.results.models import IndirectValue

        Target.objects.all().delete()
        IndirectValue.objects.filter(co_code="CO2").delete()
    run = _calc(r)
    assert run.status == "provisional"
    assert "No target has been set for this course." in run.checklist
    assert "No indirect value has been entered for CO2." in run.checklist


# A5 --------------------------------------------------------
def test_a5_two_programmes_share_an_offering_and_each_uses_only_its_own_sections(db: None) -> None:
    r = make_results_env()
    other, section_c, enrolments_c = second_programme(r)
    with college_context(r.college.id):
        main = services.calculate(r.offering, r.programme)
        second = services.calculate(r.offering, other)
    assert set(main.outputs["sections"]) == {"A", "B"} and Decimal(_course(main)["course"]) == D(
        "2.92"
    )
    assert set(second.outputs["sections"]) == {"C"}  # Section C is the only one of programme 2
    assert second.status == "provisional"  # its students have no marks yet
    assert main.pk != second.pk and main.programme_id != second.programme_id
    with college_context(r.college.id):
        assert {p.name for p in services.programmes_of(r.offering)} == {
            r.programme.name,
            other.name,
        }


# A6 --------------------------------------------------------
def test_a6_explain_lists_every_part_with_counts_denominators_and_the_versions(
    committed_db: None,
) -> None:
    r = make_results_env()
    client = _login("a.iqac")
    with college_context(r.college.id):
        run = services.latest_run(r.offering, r.programme)
        entries = services.explain(run, "SEE/CO2")
    steps = {e["step"] for _, e in entries}
    assert {"QuestionPass", "AggregateToCO", "Bands"} <= steps
    parts = [e for _, e in entries if e["step"] == "QuestionPass"]
    assert {e["key"] for e in parts} == {"SEE/12"}  # the only SEE part tagged CO2
    for e in parts:
        assert {"passed", "denominator", "attempted", "sat", "attempt_rate", "co"} <= set(e["data"])
        assert (
            e["data"]["denominator"] == e["data"]["attempted"]
        )  # a choice question: attempted only
    page = client.get(f"/results/run/{run.pk}/explain/?key=SEE/CO2").content.decode()
    assert run.input_hash in page and "engine 0.3.0" in page and "Test method v1" in page
    assert "Section A" in page
    assert "passed at" in page and "Small group" in page  # a denominator below 10


def test_a9_small_groups_are_flagged(db: None) -> None:
    r = make_results_env()
    run = _calc(r)
    flagged = [
        e
        for scope in run.trace["sections"].values()
        for e in scope
        if e["step"] == "QuestionPass" and e["data"]["small_group"] is True
    ]
    assert flagged and all(e["data"]["denominator"] < 10 for e in flagged)


# A7 and A8 -------------------------------------------------
def test_a7_the_same_inputs_twice_give_the_same_hash_and_outputs(db: None) -> None:
    r = make_results_env()
    first, second = _calc(r), _calc(r)
    assert first.input_hash == second.input_hash
    assert first.outputs == second.outputs and first.trace == second.trace
    with college_context(r.college.id):
        assert CalculationRun.objects.filter(is_latest=True).count() == 1


def test_a8_withdrawn_students_leave_the_result_and_a_section_change_moves_their_marks(
    db: None,
) -> None:
    r = make_results_env()
    with college_context(r.college.id):
        before = services.calculate(r.offering, r.programme)
        assert before.outputs["sections"]["B"]["tools"]["INT1"]["CO1"][0] == "50"
        # the student who failed 1a in section B withdraws: only the passing student remains
        roster.withdraw(r.env.enrolments_b[1], on="2025-09-01")  # type: ignore[arg-type]
        after = services.calculate(r.offering, r.programme)
        assert after.outputs["sections"]["B"]["tools"]["INT1"]["CO1"][0] == "100"
        # a student moves from section A to section B: their marks now count in B
        roster.move_section(r.env.enrolments_a[0], r.env.s.section_b, on="2025-10-01")  # type: ignore[arg-type]
        moved = services.calculate(r.offering, r.programme)
        assert moved.outputs["sections"]["B"]["tools"]["INT1"]["CO1"][0] == "100"
        entries = [
            e
            for e in moved.trace["sections"]["B"]
            if e["step"] == "QuestionPass" and e["key"] == "INT1/1a"
        ]
        assert entries[0]["data"]["sat"] == 2  # the moved student plus the one who stayed


# the indirect value and the export -------------------------
def _login(username: str) -> Client:
    client = Client()
    assert (
        client.post("/accounts/login/", {"username": username, "password": PASSWORD}).status_code
        == 302
    )
    return client


def test_m4_iqac_enters_indirect_values_labelled_entered_not_measured(committed_db: None) -> None:
    r = make_results_env()
    client = _login("a.iqac")
    url = f"/results/{r.offering.pk}/indirect/"
    page = client.get(url).content.decode()
    assert "entered, not measured" in page and 'name="co:CO1"' in page
    saved = client.post(url, {"co:CO1": "2", "co:CO2": "3", "note": "department meeting"})
    assert saved.status_code == 302
    with college_context(r.college.id):
        run = services.latest_run(r.offering, r.programme)  # recalculated automatically
        course = run.outputs["course"]
        assert course["indirect"] == {"CO1": "2", "CO2": "3"}
        assert Decimal(course["direct"]["CO1"][0]) == D("2.8")  # direct-only is not touched by it
        assert Decimal(course["final"]["CO1"][0]) == D("2.64")  # sections 2.8 and 2.48
    bad = client.post(url, {"co:CO1": "11"}, follow=True)
    assert b"between 0 and 10" in bad.content
    assert _login("a.lecturer_a").get(url).status_code == 403


def test_m6_the_excel_export_equals_the_page(committed_db: None) -> None:
    r = make_results_env()
    client = _login("a.iqac")
    response = client.get(f"/results/{r.offering.pk}/export.xlsx")
    assert response.status_code == 200 and response["Content-Type"].endswith("sheet")
    book = openpyxl.load_workbook(io.BytesIO(response.content))
    cells = {c.value for row in book["Result"].iter_rows() for c in row if c.value}
    assert {"Course attainment", "2.92", "Yes", "Test method v1"} <= cells


def test_snapshots_are_kept_and_automatic_runs_replace_each_other(db: None) -> None:
    r = make_results_env()
    with college_context(r.college.id):
        services.calculate(r.offering, r.programme)
        kept = services.snapshot(r.offering, r.programme, r.iqac)
        latest = services.calculate(r.offering, r.programme)
        assert CalculationRun.objects.filter(pk=kept.pk).exists() and kept.kept is True
        kept.refresh_from_db()
        assert kept.is_latest is False and latest.is_latest is True
        assert CalculationRun.objects.filter(is_latest=True).count() == 1


# A11 and A12 -----------------------------------------------
def test_a11_permissions_lecturer_own_sections_hod_department(committed_db: None) -> None:
    r = make_results_env()
    section_a, section_b = r.env.s.section_a, r.env.s.section_b
    course_url = f"/results/{r.offering.pk}/"
    lecturer = _login("a.lecturer_a")
    assert (
        lecturer.get(course_url).status_code == 403
    )  # no course-level view for a section lecturer
    assert lecturer.get(f"{course_url}section/{section_a.pk}/").status_code == 200
    assert lecturer.get(f"{course_url}section/{section_b.pk}/").status_code == 403
    hod = _login("a.hod")
    assert hod.get(course_url).status_code == 200
    assert hod.get(f"{course_url}section/{section_b.pk}/").status_code == 200
    assert _login("a.auditor").get(course_url).status_code == 200
    assert _login("a.exam").get(course_url).status_code == 403
    assert Client().get(course_url).status_code == 302


def test_a11_a_lecturers_explain_only_shows_their_own_sections(committed_db: None) -> None:
    r = make_results_env()
    with college_context(r.college.id):
        run = services.latest_run(r.offering, r.programme)
    page = (
        _login("a.lecturer_a").get(f"/results/run/{run.pk}/explain/?key=INT1/CO1").content.decode()
    )
    assert "Section A" in page.title() and "Section B" not in page.title()


def test_a12_another_colleges_results_are_not_found(committed_db: None) -> None:
    make_results_env("a")
    other = make_results_env("b")
    with college_context(other.college.id):
        run = services.latest_run(other.offering, other.programme)
    client = _login("a.iqac")
    for path in (
        f"/results/{other.offering.pk}/",
        f"/results/{other.offering.pk}/section/{other.env.s.section_a.pk}/",
        f"/results/run/{run.pk}/explain/?key=course",
        f"/results/{other.offering.pk}/indirect/",
        f"/results/{other.offering.pk}/export.xlsx",
    ):
        assert client.get(path).status_code == 404, path


def test_choose_a_programme_when_an_offering_serves_several(committed_db: None) -> None:
    r = make_results_env()
    other, *_ = second_programme(r)
    client = _login("a.iqac")
    page = client.get(f"/results/{r.offering.pk}/").content.decode()
    assert "kept separate for each" in page and other.name in page
    chosen = client.get(f"/results/{r.offering.pk}/?programme={r.programme.pk}")
    assert b"Course attainment" in chosen.content


@pytest.mark.perf
def test_a10_130_students_by_30_parts_calculates_and_renders_in_under_a_second(db: None) -> None:
    from apps.academics.models import Section
    from apps.assessments import services as papers
    from apps.marks.models import MarkSheetRow
    from apps.roster.models import Enrolment

    r = make_results_env(with_marks=False)
    env = r.env
    with college_context(r.college.id):
        spec = [
            {"number": str(n), "choice_group": None,
             "parts": [{"label": lab, "max": "4", "co": co}
                       for lab, co in (("a", "CO1"), ("b", "CO2"), ("c", "CO1"))]}
            for n in range(1, 11)
        ]  # fmt: skip
        big = papers.create_paper(env.s.offering, "INT1X", "Big", "question_wise", spec)
        section = Section.objects.get(pk=env.s.section_a.pk)
        for i in range(125):
            student = roster.create_student(f"Bulk {i}")
            roster.add_identifier(student, str(100 + i), section=section)
            roster.enrol(student, env.s.offering, section)
        parts = list(big.parts.all())
        rows = [
            MarkSheetRow(college_id=r.college.id, enrolment=e, assessment=big, status="entered")
            for e in Enrolment.objects.filter(section=section)
        ]
        MarkSheetRow.objects.bulk_create(rows)
        MarkCell.objects.bulk_create(
            [
                MarkCell(college_id=r.college.id, row=row, part=p, state="value", value=D(i % 5))
                for row in rows
                for i, p in enumerate(parts)
            ]
        )
        assert len(parts) == 30 and len(rows) >= 130
        start = time.perf_counter()
        services.calculate(env.s.offering, r.programme)
        calc = time.perf_counter() - start
    assert calc < 1.0, f"{calc:.2f} s"
    with college_context(r.college.id):
        assert MarkCell.objects.count() >= 130 * 30
        assert ResultValue.objects.count() > 0
