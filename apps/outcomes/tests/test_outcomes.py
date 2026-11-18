"""A1, A2, A9 and the CO-PO grid screen. Synthetic data; the DL map comes from the docs."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client

from apps.academics.tests.helpers import make_structure
from apps.accounts.models import Role
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import PASSWORD, make_college, make_user
from apps.audit.models import AuditEvent
from apps.outcomes import services
from apps.outcomes.models import COPOMap, CourseOutcome, ProgrammeOutcome, Target
from apps.tenancy.services import college_context

pytestmark = [pytest.mark.integration]

DL_MAP = {
    "CO1": {"PO1": 2, "PO3": 2, "PO4": 1, "PSO1": 1, "PSO2": 3, "PSO3": 3},
    "CO2": {"PO1": 2, "PO2": 2, "PO3": 2, "PO4": 2, "PO5": 2, "PSO1": 1, "PSO2": 3, "PSO3": 3},
    "CO3": {"PO1": 3, "PO2": 2, "PO3": 3, "PO4": 2, "PO5": 2, "PSO1": 2, "PSO2": 3, "PSO3": 3},
    "CO4": {"PO1": 3, "PO2": 2, "PO3": 2, "PO4": 2, "PO5": 1, "PSO1": 2, "PSO2": 3, "PSO3": 3},
    "CO5": {"PO1": 3, "PO2": 2, "PO5": 2, "PSO1": 2, "PSO2": 3, "PSO3": 3},
}


def _setup(college, n_cos: int = 5):  # type: ignore[no-untyped-def]
    s = make_structure(college)
    with college_context(college.id):
        services.create_programme_outcomes(
            s.programme,
            [("PO", f"PO{i}", f"Outcome {i}") for i in range(1, 6)]
            + [("PSO", f"PSO{i}", f"Specific {i}") for i in range(1, 4)]
            + [("PEO", "PEO1", "Objective 1")],
        )
        definition = services.create_definition(
            s.course, [(f"CO{i}", f"Outcome text {i}") for i in range(1, n_cos + 1)]
        )
    return s, definition


def test_a1_grid_saved_and_reloaded_blank_stays_blank_and_zero_stays_zero(db: None) -> None:
    college = make_college("a")
    s, definition = _setup(college)
    with college_context(college.id):
        changed = services.save_mapping_grid(
            definition, s.programme, {"CO1": {"PO1": 2, "PO2": 0, "PO3": None}, "CO2": {"PO1": 3}}
        )
        assert changed == 3  # PO3 was blank and stays blank: no change
        grid = services.mapping_grid(definition, s.programme)
        assert grid["CO1"] == {"PO1": 2, "PO2": 0}  # the 0 is kept; PO3 is simply not there
        assert "PO3" not in grid["CO1"] and grid["CO2"] == {"PO1": 3}
        assert COPOMap.objects.filter(strength=0).count() == 1
        engine = services.engine_mapping(definition, s.programme)
        assert engine["CO1"] == {"PO1": Decimal(2), "PO2": Decimal(0)}


def test_a1_values_outside_blank_0_1_2_3_are_rejected_and_nothing_is_saved(db: None) -> None:
    college = make_college("a")
    s, definition = _setup(college)
    with college_context(college.id):
        with pytest.raises(ValidationError) as caught:
            services.save_mapping_grid(
                definition, s.programme, {"CO1": {"PO1": 2, "PO2": 5}, "CO2": {"PO1": -1, "PO9": 1}}
            )
        text = " ".join(caught.value.messages)
        assert "CO1 / PO2: 5" in text and "CO2 / PO1: -1" in text and "PO9" in text
        assert COPOMap.objects.count() == 0  # all or nothing
        with pytest.raises(IntegrityError), transaction.atomic():
            co = CourseOutcome.objects.get(code="CO1")
            COPOMap.objects.create(
                co=co, outcome=ProgrammeOutcome.objects.get(code="PO1"), strength=4
            )


def test_clearing_a_cell_removes_the_row_and_is_audited(db: None) -> None:
    college = make_college("a")
    s, definition = _setup(college)
    with college_context(college.id):
        services.save_mapping_grid(definition, s.programme, {"CO1": {"PO1": 2}})
        services.save_mapping_grid(definition, s.programme, {"CO1": {"PO1": 3}})
        services.save_mapping_grid(definition, s.programme, {"CO1": {"PO1": None}})
        assert COPOMap.objects.count() == 0
        actions = list(
            AuditEvent.objects.filter(entity="outcomes.copomap").values_list("action", flat=True)
        )
        assert actions == [
            "outcomes.copomap.created",
            "outcomes.copomap.updated",
            "outcomes.copomap.deleted",
        ]


def test_a2_a_course_with_four_cos_is_accepted_and_co5_is_absent_everywhere(db: None) -> None:
    college = make_college("a")
    s, definition = _setup(college, n_cos=4)
    with college_context(college.id):
        assert [co.code for co in definition.outcomes.all()] == ["CO1", "CO2", "CO3", "CO4"]
        services.save_mapping_grid(definition, s.programme, {"CO4": {"PO1": 1}})
        assert "CO5" not in services.mapping_grid(definition, s.programme)
        with pytest.raises(ValidationError, match="CO5"):
            services.save_mapping_grid(definition, s.programme, {"CO5": {"PO1": 1}})


def test_course_outcome_codes_must_be_filled_in_and_different(db: None) -> None:
    college = make_college("a")
    s = make_structure(college)
    with college_context(college.id):
        with pytest.raises(ValidationError):
            services.create_definition(s.course, [("CO1", ""), ("CO1", "")])
        with pytest.raises(ValidationError):
            services.create_definition(s.course, [("", "x")])


def test_a_revised_syllabus_is_a_new_definition_version(db: None) -> None:
    college = make_college("a")
    s, first = _setup(college)
    with college_context(college.id):
        second = services.create_definition(s.course, [("CO1", "new"), ("CO2", "new")])
        assert (first.version, second.version) == (1, 2)
        assert second.outcomes.count() == 2 and first.outcomes.count() == 5  # the old stays whole


def test_the_deep_learning_map_gives_the_r1_po_values_through_the_engine(db: None) -> None:
    from engine.model import CoValue
    from engine.precision import quantize
    from engine.steps.map_outcomes import map_to_outcomes
    from engine.trace import Trace

    college = make_college("a")
    s, definition = _setup(college)
    with college_context(college.id):
        services.save_mapping_grid(definition, s.programme, DL_MAP)
        mapping = services.engine_mapping(definition, s.programme)
    final = {
        f"CO{i + 1}": CoValue(Decimal(v), "ok")
        for i, v in enumerate(["2.52", "2.52", "2.28", "2.04", "1.56"])
    }
    out = map_to_outcomes(final, mapping, "blank", Trace())
    assert {po: str(quantize(v.value, 2, "truncate")) for po, v in out.items() if v.value} == {
        "PO1": "2.13", "PO2": "2.10", "PO3": "2.33", "PO4": "2.31", "PO5": "2.10",
        "PSO1": "2.10", "PSO2": "2.18", "PSO3": "2.18",
    }  # fmt: skip


# A9 --------------------------------------------------------
def test_a9_targets_per_course_and_term_and_per_programme_outcome(db: None) -> None:
    college = make_college("a")
    s, _ = _setup(college)
    with college_context(college.id):
        course_target = services.set_target("2.2", offering=s.offering)
        assert course_target.value == Decimal("2.2")
        po1 = ProgrammeOutcome.objects.get(code="PO1")
        po_target = services.set_target("2.55", outcome=po1, batch=s.batch)
        assert Target.objects.count() == 2 and po_target.batch == s.batch
        updated = services.set_target("2.3", offering=s.offering)  # one target per offering
        assert updated.pk == course_target.pk and Target.objects.count() == 2
        actions = AuditEvent.objects.filter(entity="outcomes.target").values_list(
            "action", flat=True
        )
        assert sorted(actions) == [
            "outcomes.target.created",
            "outcomes.target.created",
            "outcomes.target.updated",
        ]


def test_a_target_needs_exactly_one_scope_and_a_sensible_value(db: None) -> None:
    college = make_college("a")
    s, _ = _setup(college)
    po1_holder = {}
    with college_context(college.id):
        po1_holder["po"] = ProgrammeOutcome.objects.get(code="PO1")
        for bad in (
            {"offering": s.offering, "outcome": po1_holder["po"], "batch": s.batch},
            {"outcome": po1_holder["po"]},  # an outcome target also needs its batch
            {},
        ):
            with pytest.raises(ValidationError):
                services.set_target("2", **bad)
        with pytest.raises(ValidationError):
            services.set_target("11", offering=s.offering)


# the grid screen -------------------------------------------
def _login(username: str) -> Client:
    client = Client()
    assert (
        client.post("/accounts/login/", {"username": username, "password": PASSWORD}).status_code
        == 302
    )
    return client


def test_m2_the_grid_screen_shows_blank_and_zero_differently_and_saves(committed_db: None) -> None:
    college = make_college("a")
    s, definition = _setup(college)
    iqac = make_user(college, "a.iqac")
    with college_context(college.id):
        assign_role(iqac, Role.IQAC)
        services.save_mapping_grid(definition, s.programme, {"CO1": {"PO1": 0}})
    client = _login("a.iqac")
    url = f"/outcomes/map/{definition.pk}/{s.programme.pk}/"
    page = client.get(url).content.decode()
    assert 'name="cell:CO1:PO1"' in page and "PEO1" not in page  # PEOs are not mapped
    assert '<option value="0" selected>' in page  # CO1/PO1 is an explicit 0
    posted = {f"cell:{co}:{po}": "" for co in ("CO1", "CO2") for po in ("PO1", "PO2")}
    posted.update({"cell:CO1:PO1": "", "cell:CO1:PO2": "3", "cell:CO2:PO1": "1"})
    response = client.post(url, posted)
    assert response.status_code == 302
    with college_context(college.id):
        assert services.mapping_grid(definition, s.programme)["CO1"] == {"PO2": 3}
    bad = client.post(url, {**posted, "cell:CO1:PO2": "7"}, follow=True)
    assert b"CO1 / PO2: 7" in bad.content


def test_only_those_who_may_edit_outcomes_can_open_the_grid(committed_db: None) -> None:
    college = make_college("a")
    s, definition = _setup(college)
    make_user(college, "a.nobody")
    url = f"/outcomes/map/{definition.pk}/{s.programme.pk}/"
    assert _login("a.nobody").get(url).status_code == 403
    assert Client().get(url).status_code == 302


def test_another_colleges_grid_is_not_found(committed_db: None) -> None:
    a, b = make_college("a"), make_college("b")
    sb, definition_b = _setup(b)
    iqac = make_user(a, "a.iqac")
    with college_context(a.id):
        assign_role(iqac, Role.IQAC)
    url = f"/outcomes/map/{definition_b.pk}/{sb.programme.pk}/"
    assert _login("a.iqac").get(url).status_code == 404
