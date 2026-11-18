"""v0.11.0 A11: a static accessibility scan of the key pages.

This is not a full audit (it does not judge colour contrast or keyboard order; that is manual
test M5 with a real reader). It catches the failures a script can see: a page with no language,
title, heading or main area, a form control with no label, a button or link with no name, an
image with no text, a table with no header cell, and a repeated id.
"""

from html.parser import HTMLParser

import pytest
from django.test import Client

from apps.accounts.models import Role
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import PASSWORD, make_user
from apps.tenancy.services import college_context

from .test_v090_isolation import _build

pytestmark = [pytest.mark.integration]

CONTROLS = {"input", "select", "textarea"}
SKIPPED_INPUT_TYPES = {"hidden", "submit", "button", "reset", "image"}


class Scan(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.lang = ""
        self.title = ""
        self.h1 = 0
        self.main = 0
        self.ids: list[str] = []
        self.label_for: set[str] = set()
        self.controls: list[dict[str, str | None]] = []
        self.problems: list[str] = []
        self._stack: list[str] = []
        self._text: dict[str, str] = {}
        self._label_depth = 0
        self._button: dict[str, str | None] | None = None
        self._link: dict[str, str | None] | None = None
        self._button_text = ""
        self._link_text = ""
        self._table_has_th: list[bool] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        self._stack.append(tag)
        if tag == "html":
            self.lang = a.get("lang") or ""
        elif tag == "h1":
            self.h1 += 1
        elif tag == "main":
            self.main += 1
        elif tag == "label":
            self._label_depth += 1
            if a.get("for"):
                self.label_for.add(a["for"] or "")
        elif tag in CONTROLS and (a.get("type") or "text") not in SKIPPED_INPUT_TYPES:
            a["_in_label"] = "1" if self._label_depth else None
            a["_tag"] = tag
            self.controls.append(a)
        elif tag == "button":
            self._button, self._button_text = a, ""
        elif tag == "a" and "href" in a:
            self._link, self._link_text = a, ""
        elif tag == "img" and not (a.get("alt") is not None):
            self.problems.append("an image has no alt text")
        elif tag == "table":
            self._table_has_th.append(False)
        elif tag == "th" and self._table_has_th:
            self._table_has_th[-1] = True
        if a.get("id"):
            self.ids.append(a["id"] or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "label":
            self._label_depth = max(0, self._label_depth - 1)
        elif tag == "button" and self._button is not None:
            if not (self._button_text.strip() or self._button.get("aria-label")):
                self.problems.append("a button has no name")
            self._button = None
        elif tag == "a" and self._link is not None:
            if not (
                self._link_text.strip() or self._link.get("aria-label") or self._link.get("title")
            ):
                self.problems.append(f"a link to {self._link.get('href')} has no text")
            self._link = None
        elif tag == "table" and self._table_has_th and not self._table_has_th.pop():
            self.problems.append("a table has no header cell")
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._stack and self._stack[-1] == "title":
            self.title += data
        if self._button is not None:
            self._button_text += data
        if self._link is not None:
            self._link_text += data


def scan(html: str) -> list[str]:
    s = Scan()
    s.feed(html)
    problems = list(s.problems)
    if not s.lang:
        problems.append("the page has no language")
    if not s.title.strip():
        problems.append("the page has no title")
    if s.h1 != 1:
        problems.append(f"the page has {s.h1} h1 headings, not one")
    if not s.main:
        problems.append("the page has no main area")
    for c in s.controls:
        named = (
            c.get("aria-label") or c.get("aria-labelledby") or c.get("title") or c.get("_in_label")
        )
        if not (named or (c.get("id") and c["id"] in s.label_for)):
            problems.append(f"a {c['_tag']} named {c.get('name')} has no label")
    problems += [f"the id {i} is used twice" for i in {i for i in s.ids if s.ids.count(i) > 1}]
    return sorted(set(problems))


def test_the_scanner_catches_each_failure() -> None:
    bad = (
        "<html><head></head><body><h1>a</h1><h1>b</h1><input name=x><img src=x>"
        "<button></button><a href=/y></a><table><tr><td>1</td></tr></table>"
        "<p id=d></p><p id=d></p></body></html>"
    )
    found = " | ".join(scan(bad))
    for expected in (
        "no language", "no title", "2 h1", "no main", "no label", "no alt", "button has no name",
        "link to /y", "no header cell", "id d is used twice",
    ):  # fmt: skip
        assert expected in found, expected
    good = (
        '<html lang="en"><head><title>t</title></head><body><main><h1>a</h1>'
        '<label for="n">Name</label><input id="n" name="n"><label>Roll <input name="r"></label>'
        '<input name="k" aria-label="Mark"><button>Save</button><a href="/y">y</a>'
        '<img src="x" alt=""><table><tr><th>h</th></tr></table></main></body></html>'
    )
    assert scan(good) == []


def test_a11_the_key_pages_have_no_failures_a_script_can_see(committed_db: None) -> None:
    a, batch, later, plan, _proof = _build()
    admin = make_user(a.college, "a.admin")
    with college_context(a.college.id):
        assign_role(admin, Role.COLLEGE_ADMIN)
    off, section = a.offering.pk, a.env.s.section_a.pk
    pages = {
        "a.iqac": [
            f"/results/{off}/", f"/results/{off}/gaps/", f"/results/{off}/indirect/",
            f"/results/batch/{batch.pk}/", f"/results/batch/{batch.pk}/compare/",
            f"/results/batch/{batch.pk}/gaps/", f"/results/batch/{batch.pk}/inputs/",
            f"/reports/course/{off}/", f"/reports/batch/{batch.pk}/",
            f"/reports/course/{off}/analysis.html", f"/reports/batch/{batch.pk}/report.html",
            f"/workflow/batch/{batch.pk}/", f"/imports/historic/{batch.pk}/", "/",
        ],
        "a.lecturer_a": [
            f"/marks/{a.env.internal.pk}/{section}/",
        ],
        "a.hod": [f"/quality/{off}/", f"/quality/{later.pk}/"],
        "a.admin": ["/privacy/retention/", f"/imports/roster/{section}/", "/imports/"],
    }  # fmt: skip
    failures: list[str] = []
    login = Client().get("/accounts/login/").content.decode()
    failures += [f"/accounts/login/: {p}" for p in scan(login)]
    for username, urls in pages.items():
        client = Client()
        assert (
            client.post(
                "/accounts/login/", {"username": username, "password": PASSWORD}
            ).status_code
            == 302
        )
        for url in urls:
            response = client.get(url)
            assert response.status_code == 200, (username, url, response.status_code)
            failures += [f"{url}: {p}" for p in scan(response.content.decode())]
    assert not failures, "\n".join(failures)
