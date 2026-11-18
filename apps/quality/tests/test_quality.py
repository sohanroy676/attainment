"""v0.9.0: observations, action plans, actions taken and proof files (synthetic data only)."""

from datetime import date, timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.academics.models import AcademicYear, Course, CourseOffering, Section, Term
from apps.accounts.models import Role, ScopeType
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import PASSWORD, make_user
from apps.audit.models import AuditEvent
from apps.outcomes import services as outcomes
from apps.quality import services
from apps.quality.models import ActionPlan, ActionTaken, Evidence, Observation
from apps.results import services as results
from apps.tenancy.services import college_context
from apps.workflow.tests.helpers import make_wf_env

pytestmark = [pytest.mark.integration]

PDF = b"%PDF-1.4\n%synthetic proof\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def _next_year(w):  # type: ignore[no-untyped-def]
    """The same course the next year, with a lecturer who teaches its section A."""
    with college_context(w.college.id):
        year = AcademicYear.objects.create(
            label="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31)
        )
        term = Term.objects.create(academic_year=year, number=6)
        later = CourseOffering.objects.create(course=w.offering.course, term=term)
        section = Section.objects.create(
            offering=later, name="A", programme=w.programme, batch=w.env.s.batch
        )
        teacher = make_user(w.college, "a.lecturer2")
        assign_role(teacher, Role.LECTURER, ScopeType.SECTION, section.pk)
    return later, section, teacher


def test_the_gap_view_fills_in_a_first_draft(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        outcomes.set_target("3", offering=w.offering)
        results.calculate(w.offering, w.programme)
        draft = services.prefill(w.offering)
        assert "CO1 is below the target (2.84 against 3)." in draft
        assert "Weak question: INT1 part 1a (CO1), 85.71% of students passed." in draft
        assert "CO2" not in draft.split("Weak question")[0]  # CO2 meets the target


def test_there_is_no_draft_before_any_result(db: None) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        assert services.prefill(w.offering) == ""


def test_who_may_write_and_who_may_only_read(db: None) -> None:
    w = make_wf_env()
    env = w.env
    with college_context(w.college.id):
        for who in (env.lecturer_a, w.coordinator, w.r.hod):
            row = services.add_observation(w.offering, "Students struggled with Q1a", who)
            assert row.written_by_id == who.pk
        for who in (w.r.iqac, w.principal, env.auditor):  # the table says view only
            assert services.may_view(who, w.offering) and not services.may_edit(who, w.offering)
            with pytest.raises(PermissionDenied):
                services.add_observation(w.offering, "x", who)
            with pytest.raises(PermissionDenied):
                services.add_plan(w.offering, "x", who)
        stranger = make_user(w.college, "a.stranger")
        assert not services.may_view(stranger, w.offering)
        assert Observation.objects.count() == 3


def test_a_lecturer_of_another_section_has_no_access_to_this_one(db: None) -> None:
    w = make_wf_env()
    later, _section, teacher = _next_year(w)
    with college_context(w.college.id):
        assert services.may_edit(teacher, later)
        assert not services.may_view(teacher, w.offering)  # last year's offering is not theirs
        assert not services.may_edit(w.env.lecturer_a, later)


@pytest.mark.parametrize("text", ["", "   ", "x" * 5001])
def test_empty_and_oversized_text_is_refused(db: None, text: str) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        with pytest.raises(ValidationError):
            services.add_observation(w.offering, text, w.r.hod)
        with pytest.raises(ValidationError):
            services.add_plan(w.offering, text, w.r.hod)
        assert not Observation.objects.exists() and not ActionPlan.objects.exists()


def test_a_plan_answers_an_observation_of_the_same_offering_only(db: None) -> None:
    w = make_wf_env()
    later, _s, _t = _next_year(w)
    with college_context(w.college.id):
        seen = services.add_observation(w.offering, "CO1 is weak", w.r.hod)
        plan = services.add_plan(
            w.offering, "Add a tutorial on CO1", w.r.hod, due_date=date(2026, 12, 1),
            observation=seen,
        )  # fmt: skip
        assert plan.observation_id == seen.pk and plan.owner_id == w.r.hod.pk
        other = services.add_observation(later, "elsewhere", w.r.hod)
        with pytest.raises(ValidationError, match="another course offering"):
            services.add_plan(w.offering, "x", w.r.hod, observation=other)


def test_a8_last_years_plan_shows_on_the_new_offering(db: None) -> None:
    w = make_wf_env()
    later, _s, _t = _next_year(w)
    with college_context(w.college.id):
        old = services.add_plan(w.offering, "Add a tutorial on CO1", w.r.hod)
        services.add_plan(later, "This year's own plan", w.r.hod)
        elsewhere = Course.objects.create(title="Another course")
        year = AcademicYear.objects.get(label="2026-27")
        unrelated = CourseOffering.objects.create(
            course=elsewhere, term=Term.objects.create(academic_year=year, number=2)
        )
        Section.objects.create(
            offering=unrelated, name="A", programme=w.programme, batch=w.env.s.batch
        )
        services.add_plan(unrelated, "Not for this course", w.r.hod)
        assert [p.pk for p in services.previous_plans(later)] == [old.pk]
        assert services.previous_plans(w.offering) == []  # nothing earlier than the first year


def test_a8_an_action_is_recorded_with_a_date_and_proof(db: None) -> None:
    w = make_wf_env()
    later, _s, teacher = _next_year(w)
    with college_context(w.college.id):
        plan = services.add_plan(w.offering, "Add a tutorial on CO1", w.r.hod)
        action = services.add_action(plan, later, "Held two tutorials", date(2026, 8, 3), teacher)
        saved = services.add_evidence(
            action, [("attendance.pdf", PDF), ("photo.PNG", PNG), ("scan.jpeg", JPEG)], teacher
        )
        assert [(e.name, e.content_type, e.size) for e in saved] == [
            ("attendance.pdf", "application/pdf", len(PDF)),
            ("photo.PNG", "image/png", len(PNG)),
            ("scan.jpeg", "image/jpeg", len(JPEG)),
        ]
        assert all(len(e.sha256) == 64 for e in saved)
        assert bytes(Evidence.objects.get(name="attendance.pdf").content) == PDF
        assert action.plan_id == plan.pk and action.done_on == date(2026, 8, 3)
        assert services.previous_plans(later)[0].actions.get().evidence.count() == 3


def test_an_action_must_follow_its_plan_on_a_later_offering_of_the_same_course(db: None) -> None:
    w = make_wf_env()
    later, _s, teacher = _next_year(w)
    with college_context(w.college.id):
        plan = services.add_plan(w.offering, "Plan", w.r.hod)
        this_year = services.add_plan(later, "Plan", w.r.hod)
        with pytest.raises(ValidationError, match="later offering"):
            services.add_action(plan, w.offering, "same year", date(2026, 1, 1), w.r.hod)
        with pytest.raises(ValidationError, match="later offering"):
            services.add_action(this_year, w.offering, "backwards", date(2026, 1, 1), w.r.hod)
        other = Course.objects.create(title="Another course")
        foreign = CourseOffering.objects.create(course=other, term=later.term)
        Section.objects.create(
            offering=foreign, name="A", programme=w.programme, batch=w.env.s.batch
        )  # so the HoD holds the right there and only the course check can refuse
        with pytest.raises(ValidationError, match="later offering"):
            services.add_action(plan, foreign, "wrong course", date(2026, 8, 1), w.r.hod)
        assert not ActionTaken.objects.exists()


def test_an_action_date_cannot_be_in_the_future_and_the_text_is_needed(db: None) -> None:
    w = make_wf_env()
    later, _s, teacher = _next_year(w)
    with college_context(w.college.id):
        plan = services.add_plan(w.offering, "Plan", w.r.hod)
        tomorrow = timezone.localdate() + timedelta(days=1)
        with pytest.raises(ValidationError, match="future"):
            services.add_action(plan, later, "Done", tomorrow, teacher)
        with pytest.raises(ValidationError, match="action taken"):
            services.add_action(plan, later, "  ", date(2026, 8, 1), teacher)
        services.add_action(plan, later, "Done today", timezone.localdate(), teacher)
        with pytest.raises(PermissionDenied):
            services.add_action(plan, later, "Done", date(2026, 8, 1), w.env.lecturer_a)


def _action(w, later, teacher):  # type: ignore[no-untyped-def]
    plan = services.add_plan(w.offering, "Plan", w.r.hod)
    return services.add_action(plan, later, "Done", date(2026, 8, 1), teacher)


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("proof.exe", b"MZ" + b"\x00" * 10, "only PDF, PNG and JPEG"),
        ("proof.pdf.exe", PDF, "only PDF, PNG and JPEG"),
        ("proof", PDF, "only PDF, PNG and JPEG"),
        ("proof.html", b"<script>alert(1)</script>", "only PDF, PNG and JPEG"),
        ("proof.svg", b"<svg onload=alert(1)/>", "only PDF, PNG and JPEG"),
        ("proof.pdf", b"<html><script>alert(1)</script></html>", "not really a PDF"),
        ("proof.pdf", PNG, "not really a PDF"),
        ("proof.png", PDF, "not really a PNG"),
        ("proof.jpg", PNG, "not really a JPG"),
        ("proof.pdf", b"", "empty"),
        ("proof.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024), "larger than 5 MB"),
    ],
)
def test_a8_proof_files_are_checked_by_their_own_bytes(
    db: None, name: str, content: bytes, message: str
) -> None:
    w = make_wf_env()
    later, _s, teacher = _next_year(w)
    with college_context(w.college.id):
        action = _action(w, later, teacher)
        with pytest.raises(ValidationError, match=message):
            services.add_evidence(action, [(name, content)], teacher)
        assert Evidence.objects.count() == 0


def test_an_action_with_a_refused_proof_file_is_not_saved_at_all(db: None) -> None:
    w = make_wf_env()
    later, _s, teacher = _next_year(w)
    with college_context(w.college.id):
        plan = services.add_plan(w.offering, "Plan", w.r.hod)
        with pytest.raises(ValidationError):
            services.record_action(
                plan, later, "Done", date(2026, 8, 1), teacher, [("a.pdf", PDF), ("b.exe", b"MZ")]
            )
        assert ActionTaken.objects.count() == 0 and Evidence.objects.count() == 0
        assert not AuditEvent.objects.filter(action="quality.actiontaken.created").exists()
        done = services.record_action(
            plan, later, "Done", date(2026, 8, 1), teacher, [("a.pdf", PDF)]
        )
        assert done.evidence.count() == 1


def test_a_file_of_exactly_the_limit_is_accepted(db: None) -> None:
    w = make_wf_env()
    later, _s, teacher = _next_year(w)
    with college_context(w.college.id):
        action = _action(w, later, teacher)
        big = b"%PDF-" + b"0" * (5 * 1024 * 1024 - 5)
        assert len(big) == 5 * 1024 * 1024
        assert services.add_evidence(action, [("big.pdf", big)], teacher)[0].size == len(big)


def test_one_bad_file_rejects_the_whole_upload(db: None) -> None:
    w = make_wf_env()
    later, _s, teacher = _next_year(w)
    with college_context(w.college.id):
        action = _action(w, later, teacher)
        with pytest.raises(ValidationError):
            services.add_evidence(action, [("good.pdf", PDF), ("bad.pdf", b"nope")], teacher)
        assert Evidence.objects.count() == 0
        with pytest.raises(ValidationError, match="choose a file"):
            services.add_evidence(action, [], teacher)


def test_names_are_cleaned_and_only_the_file_name_is_kept(db: None) -> None:
    assert services.safe_name("..\\..\\windows\\evil.pdf") == "evil.pdf"
    assert services.safe_name("/etc/passwd.pdf") == "passwd.pdf"
    assert services.safe_name("a\x00b\x1f.pdf") == "ab.pdf"
    assert services.safe_name("   ") == "file"
    assert services.safe_name("x" * 300 + ".pdf") == "x" * 120


def test_the_number_of_files_per_action_and_the_college_total_are_capped(
    db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = make_wf_env()
    later, _s, teacher = _next_year(w)
    with college_context(w.college.id):
        action = _action(w, later, teacher)
        services.add_evidence(action, [(f"p{i}.pdf", PDF) for i in range(10)], teacher)
        with pytest.raises(ValidationError, match="at most 10"):
            services.add_evidence(action, [("one-more.pdf", PDF)], teacher)
        second = _action(w, later, teacher)
        used = services.college_bytes_used()
        monkeypatch.setattr(services, "MAX_COLLEGE_BYTES", used + len(PDF) - 1)
        with pytest.raises(ValidationError, match="storage is full"):
            services.add_evidence(second, [("late.pdf", PDF)], teacher)
        monkeypatch.setattr(services, "MAX_COLLEGE_BYTES", used + len(PDF))
        services.add_evidence(second, [("fits.pdf", PDF)], teacher)


def test_the_audit_log_records_proof_files_without_their_content_or_name(db: None) -> None:
    w = make_wf_env()
    later, _s, teacher = _next_year(w)
    with college_context(w.college.id):
        action = _action(w, later, teacher)
        services.add_evidence(action, [("secret-name.pdf", PDF)], teacher)
        event = AuditEvent.objects.get(action="quality.evidence.created")
        assert event.after["size"] == len(PDF) and event.after["content_type"] == "application/pdf"
        assert "secret-name" not in str(event.after) + str(event.before)
        assert AuditEvent.objects.filter(action="quality.actiontaken.created").exists()


def test_another_college_sees_nothing_of_the_loop(db: None) -> None:
    a = make_wf_env("a")
    b = make_wf_env("b")
    later, _s, teacher = _next_year(a)
    with college_context(a.college.id):
        action = _action(a, later, teacher)
        services.add_evidence(action, [("p.pdf", PDF)], teacher)
    with college_context(b.college.id):
        for model in (Observation, ActionPlan, ActionTaken, Evidence):
            assert model.objects.count() == 0


def _login(username: str) -> Client:
    client = Client()
    response = client.post("/accounts/login/", {"username": username, "password": PASSWORD})
    assert response.status_code == 302
    return client


def test_m4_the_pages_carry_a_plan_to_next_year_and_serve_the_proof(committed_db: None) -> None:
    w = make_wf_env()
    later, _s, _t = _next_year(w)
    with college_context(w.college.id):
        outcomes.set_target("3", offering=w.offering)
        results.calculate(w.offering, w.programme)
    hod = _login("a.hod")
    page = hod.get(f"/quality/{w.offering.pk}/").content.decode()
    assert "CO1 is below the target" in page  # the draft from the gap view
    assert (
        hod.post(f"/quality/{w.offering.pk}/observation/", {"text": "CO1 was weak"}).status_code
        == 302
    )
    assert (
        hod.post(
            f"/quality/{w.offering.pk}/plan/",
            {"text": "Add a CO1 tutorial", "due_date": "2026-12-01"},
        ).status_code
        == 302
    )
    teacher = _login("a.lecturer2")
    page = teacher.get(f"/quality/{later.pk}/").content.decode()
    assert "Add a CO1 tutorial" in page and "No action recorded yet" in page
    with college_context(w.college.id):
        plan = ActionPlan.objects.get()
    done = teacher.post(
        f"/quality/{later.pk}/action/{plan.pk}/",
        {
            "text": "Held two tutorials", "done_on": "2026-08-03",
            "files": [SimpleUploadedFile("sheet.pdf", PDF, content_type="text/html")],
        },
    )  # fmt: skip
    assert done.status_code == 302
    with college_context(w.college.id):
        evidence = Evidence.objects.get()
        assert evidence.content_type == "application/pdf"  # decided by the bytes, not the browser
    assert "sheet.pdf" in teacher.get(f"/quality/{later.pk}/").content.decode()
    download = teacher.get(f"/quality/evidence/{evidence.pk}/")
    assert download.status_code == 200 and download.content == PDF
    assert download["Content-Type"] == "application/pdf"
    assert download["Content-Disposition"].startswith("attachment")
    assert "sandbox" in download["Content-Security-Policy"]


def test_the_pages_refuse_the_wrong_people_and_bad_input(committed_db: None) -> None:
    w = make_wf_env()
    later, _s, teacher = _next_year(w)
    with college_context(w.college.id):
        action = _action(w, later, teacher)
        evidence = services.add_evidence(action, [("p.pdf", PDF)], teacher)[0]
        plan = ActionPlan.objects.get()
    assert _login("a.lecturer_b").get(f"/quality/{later.pk}/").status_code == 403
    assert _login("a.lecturer_b").get(f"/quality/evidence/{evidence.pk}/").status_code == 403
    assert Client().get(f"/quality/{later.pk}/").status_code == 302
    iqac = _login("a.iqac")  # may read, may not write
    assert iqac.get(f"/quality/{later.pk}/").status_code == 200
    assert iqac.post(f"/quality/{later.pk}/observation/", {"text": "x"}).status_code == 302
    other = make_wf_env("b")
    assert other.college.id != w.college.id
    foreign = _login("b.iqac")
    assert foreign.get(f"/quality/{later.pk}/").status_code == 404
    assert foreign.get(f"/quality/evidence/{evidence.pk}/").status_code == 404
    with college_context(w.college.id):
        assert Observation.objects.count() == 0  # the IQAC post was refused
    bad = _login("a.lecturer2")
    url = f"/quality/{later.pk}/action/{plan.pk}/"
    assert bad.post(url, {"text": "x", "done_on": "not a date"}).status_code == 302
    assert bad.post(url, {"text": "x"}).status_code == 302
    assert (
        bad.post(
            url,
            {"text": "x", "done_on": "2026-08-01", "files": [SimpleUploadedFile("a.exe", b"MZ")]},
        ).status_code
        == 302
    )
    with college_context(w.college.id):
        assert ActionTaken.objects.count() == 1  # only the one made in setup
        assert Evidence.objects.count() == 1
    assert bad.get(f"/quality/{later.pk}/observation/").status_code == 405
