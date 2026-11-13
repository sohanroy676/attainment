"""Import of COs and the CO-PO map from a sheet."""

import io

import openpyxl
import pytest
from django.core.exceptions import ValidationError

from apps.academics.tests.helpers import make_structure
from apps.accounts.tests.helpers import make_college
from apps.imports.copo import import_copo
from apps.imports.parsers import UnreadableFile
from apps.outcomes import services as outcomes
from apps.outcomes.models import CourseDefinitionVersion, CourseOutcome
from apps.tenancy.services import college_context

pytestmark = [pytest.mark.integration]


def _setup(college):  # type: ignore[no-untyped-def]
    s = make_structure(college)
    with college_context(college.id):
        outcomes.create_programme_outcomes(
            s.programme,
            [("PO", f"PO{i}", "") for i in range(1, 4)] + [("PSO", "PSO1", "")],
        )
    return s


CSV = (
    b"CO,Text,PO1,PO2,PO3,PSO1\n"
    b"CO1,Explain networks,2,,0,1\n"
    b"CO2,Train a model,3,2,,3\n"
    b"CO3,Evaluate,,,,\n"
    b"CO4,Deploy,1,1,1,1\n"
)


def test_four_cos_and_the_map_are_imported_with_blank_and_zero_kept_apart(db: None) -> None:
    college = make_college("a")
    s = _setup(college)
    with college_context(college.id):
        definition = import_copo(s.course, s.programme, "map.csv", CSV)
        assert [c.code for c in definition.outcomes.all()] == ["CO1", "CO2", "CO3", "CO4"]
        assert definition.outcomes.get(code="CO1").text == "Explain networks"
        grid = outcomes.mapping_grid(definition, s.programme)
        assert grid["CO1"] == {"PO1": 2, "PO3": 0, "PSO1": 1}  # blank PO2 absent, 0 kept
        assert grid["CO3"] == {}  # an all-blank row maps nothing


def test_an_excel_sheet_works_the_same_way(db: None) -> None:
    college = make_college("a")
    s = _setup(college)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in [["CO", "PO1", "PO2"], ["CO1", 3, None], ["CO2", 0, 1.0]]:
        sheet.append(row)
    out = io.BytesIO()
    workbook.save(out)
    with college_context(college.id):
        definition = import_copo(s.course, s.programme, "map.xlsx", out.getvalue())
        assert outcomes.mapping_grid(definition, s.programme) == {
            "CO1": {"PO1": 3},
            "CO2": {"PO1": 0, "PO2": 1},
        }


def test_problems_are_listed_by_cell_and_nothing_is_saved(db: None) -> None:
    college = make_college("a")
    s = _setup(college)
    bad = b"CO,PO1,PO9\nCO1,5,1\nCO2,2,\nCO2,1,\nCO3,x,\n"
    with college_context(college.id), pytest.raises(ValidationError) as caught:
        import_copo(s.course, s.programme, "map.csv", bad)
    text = " | ".join(caught.value.messages)
    assert "PO9 is not an outcome of this programme" in text
    assert "Row 2, PO1: '5' is not allowed" in text
    assert "Row 4: CO2 appears again" in text and "Row 5, PO1: 'x'" in text
    with college_context(college.id):
        assert CourseDefinitionVersion.objects.count() == 0 and CourseOutcome.objects.count() == 0


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("m.txt", b"x", "csv or .xlsx"),
        ("m.csv", b"", "empty"),
        ("m.csv", b"Code,PO1\nCO1,1\n", "must be 'CO'"),
    ],
)
def test_unreadable_sheets_are_refused(db: None, name: str, content: bytes, message: str) -> None:
    college = make_college("a")
    s = _setup(college)
    with college_context(college.id), pytest.raises(UnreadableFile, match=message):
        import_copo(s.course, s.programme, name, content)


def test_a_sheet_without_any_co_is_refused(db: None) -> None:
    college = make_college("a")
    s = _setup(college)
    with college_context(college.id), pytest.raises(ValidationError, match="no course outcomes"):
        import_copo(s.course, s.programme, "m.csv", b"CO,PO1\n")
