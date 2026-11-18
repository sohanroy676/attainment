"""v0.9.0: earlier batches, the three-batch comparison and the old-workbook comparison."""

import io
from decimal import Decimal

import openpyxl
import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from apps.academics.models import Batch
from apps.accounts.tests.helpers import PASSWORD
from apps.audit.models import AuditEvent
from apps.imports.historic import import_historic
from apps.imports.models import ImportBatch
from apps.imports.parsers import UnreadableFile
from apps.outcomes import services as outcomes
from apps.outcomes.models import ProgrammeOutcome
from apps.results import services
from apps.results.models import HistoricResult
from apps.tenancy.services import college_context
from apps.workflow.tests.helpers import make_wf_env, signed

pytestmark = [pytest.mark.integration]

D = Decimal
TOTALS = b"Outcome,Total\nPO1,2.71\nPO2,2.4\n"


def _earlier(w, name: str, start: int):  # type: ignore[no-untyped-def]
    with college_context(w.college.id):
        return Batch.objects.create(
            programme=w.programme, name=name, start_year=start, end_year=start + 4
        )


def _calculated(w):  # type: ignore[no-untyped-def]
    """The current batch, signed course, targets and indirect values, one batch run."""
    batch = w.env.s.batch
    with college_context(w.college.id):
        for code in ("PO1", "PO2"):
            po = ProgrammeOutcome.objects.get(programme=w.programme, code=code)
            outcomes.set_target("2.5", outcome=po, batch=batch)
        services.set_batch_indirect(batch, {"PO1": "3", "PO2": "3"}, "test", w.r.iqac)
        signed(w)
        services.calculate_batch(batch, w.r.iqac)
    return batch


def test_a5_three_batches_side_by_side_with_the_imported_values_as_filed(db: None) -> None:
    w = make_wf_env()
    batch = _calculated(w)
    old = _earlier(w, "2019-23", 2019)
    middle = _earlier(w, "2020-24", 2020)
    with college_context(w.college.id):
        import_historic(old, "old.csv", b"Outcome,Total\nPO1,2.50\nPO2,2.1\n", w.r.iqac)
        import_historic(middle, "mid.csv", TOTALS, w.r.iqac)
        columns = services.comparison_columns(batch)
        assert [c.batch.name for c in columns] == ["2019-23", "2020-24", "2021-25"]
        assert [c.source for c in columns] == ["imported", "imported", "calculated"]
        assert columns[0].values == {"PO1": "2.5", "PO2": "2.1"}
        assert columns[1].values == {"PO1": "2.71", "PO2": "2.4"}
        assert columns[2].values["PO1"] is not None


def test_only_earlier_batches_of_the_same_programme_are_compared(db: None) -> None:
    w = make_wf_env()
    batch = w.env.s.batch
    _earlier(w, "2019-23", 2019)
    _earlier(w, "2020-24", 2020)
    with college_context(w.college.id):
        later = Batch.objects.create(
            programme=w.programme, name="2022-26", start_year=2022, end_year=2026
        )
        assert [b.name for b in services.earlier_batches(batch)] == ["2019-23", "2020-24"]
        assert [b.name for b in services.earlier_batches(batch, count=1)] == ["2020-24"]
        assert services.earlier_batches(later)[-1].pk == batch.pk
        columns = services.comparison_columns(batch)
        assert [c.source for c in columns] == ["none", "none", "none"]


def test_a6_computed_against_the_old_workbook_at_the_shown_precision(db: None) -> None:
    w = make_wf_env()
    batch = _calculated(w)
    with college_context(w.college.id):
        computed = services.latest_batch_run(batch).outputs["outcomes"]
        total_po1 = D(computed["PO1"][3])
        same = str(total_po1.quantize(D("0.01"), rounding="ROUND_DOWN"))  # as the workbook typed it
        other = str(total_po1 + D("0.05"))
        import_historic(
            batch, "old.csv", f"Outcome,Total\nPO1,{same}\nPO2,{other}\n".encode(), w.r.iqac
        )
        rows = {(r.code, r.kind): r for r in services.compare_with_imported(batch)}
        assert rows[("PO1", "PO total")].differs is False
        assert rows[("PO2", "PO total")].differs is True
        assert rows[("PO2", "PO total")].imported == str(D(other).normalize())
        assert ("PO1", "PO direct") not in rows  # only the columns that were uploaded


def test_a_value_missing_on_one_side_is_marked(db: None) -> None:
    w = make_wf_env()
    batch = _calculated(w)
    with college_context(w.college.id):
        import_historic(batch, "old.csv", b"Outcome,Total\nPO1,2.5\n", w.r.iqac)
        rows = {r.code: r for r in services.compare_with_imported(batch)}
        assert set(rows) == {"PO1", "PO2"}
        assert rows["PO2"].differs and rows["PO2"].note == "only computed"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"Outcome,Total\nPO99,2\n", "not an outcome"),
        (b"Outcome,Total\nPO1,2\nPO1,3\n", "appears again"),
        (b"Outcome,Total\nPO1,abc\n", "not a number"),
        (b"Outcome,Total\nPO1,11\n", "outside 0 to 10"),
        (b"Outcome,Total\nPO1,-1\n", "outside 0 to 10"),
        (b"Outcome,Total\nPO1,NaN\n", "outside 0 to 10"),
        (b"Outcome,Total\nPO1,Infinity\n", "outside 0 to 10"),
        (b"Outcome,Total\nPO1,\n", "no values"),
    ],
)
def test_a_bad_file_is_refused_whole_and_nothing_is_saved(
    db: None, content: bytes, message: str
) -> None:
    w = make_wf_env()
    batch = w.env.s.batch
    with college_context(w.college.id):
        with pytest.raises(ValidationError, match=message):
            import_historic(batch, "old.csv", content, w.r.iqac)
        assert HistoricResult.objects.count() == 0
        assert ImportBatch.objects.filter(kind="historic").count() == 0


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("old.csv", b"", "empty"),
        ("old.csv", b"PO1,2\n", "must be 'Outcome'"),
        ("old.csv", b"Outcome,Score\nPO1,2\n", "'Direct' or a 'Total'"),
        ("old.txt", b"Outcome,Total\n", "csv or .xlsx"),
        ("old.xlsx", b"not a zip", "not a real Excel"),
        ("old.csv", b"\xff\xfe\x00bad", "UTF-8"),
        ("old.csv", b"x" * (10 * 1024 * 1024 + 1), "10 MB"),
    ],
)
def test_an_unreadable_file_stores_nothing(
    db: None, name: str, content: bytes, message: str
) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        with pytest.raises(UnreadableFile, match=message):
            import_historic(w.env.s.batch, name, content, w.r.iqac)
        assert HistoricResult.objects.count() == 0


def test_an_excel_file_is_read_for_values_and_a_bare_formula_is_refused(db: None) -> None:
    w = make_wf_env()
    batch = w.env.s.batch
    book = openpyxl.Workbook()
    book.active.append(["Outcome", "Direct", "Total"])
    book.active.append(["PO1", 2.6, 2.7])
    out = io.BytesIO()
    book.save(out)
    formula = openpyxl.Workbook()
    formula.active.append(["Outcome", "Total"])
    formula.active.append(["PO1", "=1+1"])
    bad = io.BytesIO()
    formula.save(bad)
    with college_context(w.college.id):
        import_historic(batch, "old.xlsx", out.getvalue(), w.r.iqac)
        assert services.historic_values(batch, "po_direct") == {"PO1": D("2.6")}
        assert services.historic_values(batch, "po_total") == {"PO1": D("2.7")}
        with pytest.raises(UnreadableFile, match="formula with no stored result"):
            import_historic(batch, "f.xlsx", bad.getvalue(), w.r.iqac)


def test_a_new_upload_replaces_the_old_values_and_the_file_is_kept(db: None) -> None:
    w = make_wf_env()
    batch = w.env.s.batch
    with college_context(w.college.id):
        first = import_historic(batch, "one.csv", b"Outcome,Total\nPO1,2\nPO2,3\n", w.r.iqac)
        second = import_historic(batch, "two.csv", b"Outcome,Total\nPO1,2.2\n", w.r.iqac)
        assert services.historic_values(batch, "po_total") == {"PO1": D("2.2")}
        assert bytes(first.file_content) == b"Outcome,Total\nPO1,2\nPO2,3\n"
        assert second.file_sha256 and first.file_sha256 != second.file_sha256
        assert HistoricResult.objects.get().source_id == second.pk
        deleted = AuditEvent.objects.filter(action="results.historicresult.deleted")
        assert deleted.count() == 2  # the replaced values stay in the audit log


def test_another_college_never_sees_imported_values(db: None) -> None:
    a = make_wf_env("a")
    b = make_wf_env("b")
    with college_context(a.college.id):
        import_historic(a.env.s.batch, "old.csv", TOTALS, a.r.iqac)
    with college_context(b.college.id):
        assert HistoricResult.objects.count() == 0
        assert ImportBatch.objects.filter(kind="historic").count() == 0


def _login(username: str) -> Client:
    client = Client()
    response = client.post("/accounts/login/", {"username": username, "password": PASSWORD})
    assert response.status_code == 302
    return client


def test_the_comparison_and_upload_pages(committed_db: None) -> None:
    w = make_wf_env()
    batch = w.env.s.batch
    _earlier(w, "2020-24", 2020)
    iqac = _login("a.iqac")
    upload = f"/imports/historic/{batch.pk}/"
    assert "Outcome" in iqac.get(upload).content.decode()
    from django.core.files.uploadedfile import SimpleUploadedFile

    sent = iqac.post(upload, {"file": SimpleUploadedFile("old.csv", TOTALS)})
    assert sent.status_code == 302 and sent["Location"].endswith(
        f"/results/batch/{batch.pk}/compare/"
    )
    bad = iqac.post(upload, {"file": SimpleUploadedFile("old.csv", b"Outcome,Total\nPO7,2\n")})
    assert bad.status_code == 200 and "not an outcome" in bad.content.decode()
    page = iqac.get(f"/results/batch/{batch.pk}/compare/").content.decode()
    assert "2020-24" in page and "2021-25" in page and "no result" in page
    assert "nothing to compare yet" in page  # this batch has not been calculated
    assert _login("a.hod").get(f"/results/batch/{batch.pk}/compare/").status_code == 200
    assert _login("a.hod").get(upload).status_code == 403
    assert _login("a.lecturer_a").get(f"/results/batch/{batch.pk}/compare/").status_code == 403
    assert iqac.post(upload, {}).status_code == 200  # no file chosen: asked again
