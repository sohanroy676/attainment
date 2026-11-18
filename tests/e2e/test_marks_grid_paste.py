"""v0.6.0 A11 (carried over): pasting a block from Excel into the marks grid in a real browser."""

import pytest
from playwright.sync_api import Page, sync_playwright

from apps.accounts.tests.helpers import PASSWORD
from apps.marks.models import MarkCell
from apps.marks.tests.helpers import make_env
from apps.tenancy.services import college_context

pytestmark = [pytest.mark.e2e]

PASTE = r"""(text) => {
    const data = new DataTransfer();
    data.setData('text/plain', text);
    document.activeElement.dispatchEvent(
        new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true})
    );
}"""


def _open_grid(page: Page, base: str, env) -> None:  # type: ignore[no-untyped-def]
    page.goto(f"{base}/accounts/login/")
    page.fill("input[name=username]", "a.lecturer_a")
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")
    page.goto(f"{base}/marks/{env.internal.pk}/{env.s.section_a.pk}/")


def test_a_block_pasted_from_excel_fills_the_grid_and_saves(
    committed_db: None, app_server: str
) -> None:
    env = make_env()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        _open_grid(page, app_server, env)
        inputs = page.locator("input[name^='cell:']")
        assert inputs.count() == 10  # five students, parts 1a and 1b
        inputs.first.focus()
        page.evaluate(PASTE, "3\t2\n4\t1\n0\t4\n")
        assert [inputs.nth(i).input_value() for i in range(6)] == ["3", "2", "4", "1", "0", "4"]
        assert inputs.nth(6).input_value() == ""  # nothing pasted beyond the block
        assert "Pasted 6 cells" in page.locator("#paste-notice").inner_text()
        # pasting is not saving: a reload shows an empty grid again
        page.reload()
        assert page.locator("input[name^='cell:']").first.input_value() == ""
        inputs = page.locator("input[name^='cell:']")
        inputs.first.focus()
        page.evaluate(PASTE, "3\t2\n4\t1\n0\t4\n")
        # an arrow key moves down one row, same column
        inputs.nth(1).focus()
        page.keyboard.press("ArrowDown")
        assert page.evaluate("document.activeElement.name") == inputs.nth(3).get_attribute("name")
        page.click("button:has-text('Save')")
        page.wait_for_selector("text=Saved 6 marks")
        browser.close()
    with college_context(env.college.id):
        values = sorted(str(c.value) for c in MarkCell.objects.all())
        assert values == ["0.00", "1.00", "2.00", "3.00", "4.00", "4.00"]


def test_pasting_more_than_fits_leaves_the_rest_out_and_says_so(
    committed_db: None, app_server: str
) -> None:
    env = make_env()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        _open_grid(page, app_server, env)
        inputs = page.locator("input[name^='cell:']")
        inputs.nth(9).focus()  # the last box of the last row
        page.evaluate(PASTE, "1\t2\n3\t4")
        assert inputs.nth(9).input_value() == "1"
        assert "3 did not fit the grid" in page.locator("#paste-notice").inner_text()
        browser.close()
