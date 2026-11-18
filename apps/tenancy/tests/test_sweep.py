"""v0.11.0 A5: the full isolation sweep.

Every URL pattern the project defines is discovered from the URL configuration (nothing is listed
by hand). Each id in a pattern is filled with a real id from college A, and every user of college B
asks for it with GET and POST. The answer must be 403, 404 or 405, and college A's data must not
change. A pattern with an id the sweep cannot fill fails the test, so a new endpoint cannot be
added without being swept.
"""

import itertools
import re
from collections.abc import Iterator
from typing import Any

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from apps.academics.models import Batch, CourseOffering, Programme, Section
from apps.accounts.models import Role
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import make_user
from apps.assessments.models import Assessment
from apps.marks.models import MarkCell
from apps.methodology.models import MethodVersion
from apps.outcomes.models import CourseDefinitionVersion
from apps.quality.models import ActionPlan, Evidence
from apps.reports import export
from apps.results.models import CalculationRun
from apps.tenancy.services import college_context
from apps.workflow.tests.helpers import make_wf_env

from .test_v090_isolation import _build, _login

pytestmark = [pytest.mark.isolation, pytest.mark.integration]

SKIPPED_PREFIXES = ("admin/", "static/")
ID_MODELS: dict[str, Any] = {
    "offering_id": CourseOffering,
    "batch_id": Batch,
    "section_id": Section,
    "assessment_id": Assessment,
    "programme_id": Programme,
    "definition_id": CourseDefinitionVersion,
    "version_id": MethodVersion,
    "cell_id": MarkCell,
    "run_id": CalculationRun,
    "evidence_id": Evidence,
    "plan_id": ActionPlan,
}
WORDS = {
    "action": ["submit", "accept", "review", "approve", "sign", "reopen", "prepare"],
    "fmt": ["html", "pdf", "xlsx", "json"],
    "name": ["co_sheet", "analysis", "co_po", "action_taken", "appendix"],
}
PER_PARAMETER = 2  # ids tried for each id in a pattern
FOREIGN_ANSWERS = {403, 404, 405}


def _routes(patterns: Any, prefix: str = "") -> Iterator[str]:
    for entry in patterns:
        if isinstance(entry, URLResolver):
            yield from _routes(entry.url_patterns, prefix + str(entry.pattern))
        elif isinstance(entry, URLPattern):
            yield prefix + str(entry.pattern)


def discovered_routes() -> list[str]:
    routes = [r for r in _routes(get_resolver().url_patterns) if not r.startswith(SKIPPED_PREFIXES)]
    return sorted(set(routes))


def _fill(route: str, pool: dict[str, list[str]]) -> list[str]:
    names = re.findall(r"<\w+:(\w+)>", route)
    for name in names:
        if name not in pool:
            pytest.fail(
                f"The sweep cannot fill <{name}> in '{route}': add it to ID_MODELS or WORDS"
            )
    urls = []
    for choice in itertools.product(*(pool[n] for n in names)):
        url = route
        for name, value in zip(names, choice, strict=True):
            url = re.sub(rf"<\w+:{name}>", value, url, count=1)
        urls.append("/" + url)
    return urls


def _pool() -> dict[str, list[str]]:
    pool = {name: [str(pk) for pk in model.objects.values_list("pk", flat=True)[:PER_PARAMETER]]
            for name, model in ID_MODELS.items()}  # fmt: skip
    pool.update({k: v for k, v in WORDS.items()})
    for name, values in pool.items():
        assert values, f"college A has no {name} to sweep with"
    return pool


def test_a5_every_discovered_endpoint_refuses_another_college(committed_db: None) -> None:
    a, _batch, _later, _plan, _proof = _build()
    b = make_wf_env("b")
    admin = make_user(b.college, "b.admin")
    with college_context(b.college.id):
        assign_role(admin, Role.COLLEGE_ADMIN)
    with college_context(a.college.id):
        pool = _pool()
        before = export.counts()
    # only routes that name a record; "<fmt>" alone (the college's own export) is not about A
    routes = [r for r in discovered_routes() if re.search(r"<uuid:\w+>", r)]
    assert len(routes) >= 30, len(routes)  # the sweep really found the project's endpoints
    urls = sorted({url for route in routes for url in _fill(route, pool)})
    leaks = []
    for username in ("b.admin", "b.iqac", "b.hod", "b.coordinator", "b.principal", "b.lecturer_a"):
        client = _login(username)
        for url in urls:
            for verb in ("get", "post"):
                response = getattr(client, verb)(url, {} if verb == "post" else None)
                if response.status_code not in FOREIGN_ANSWERS:
                    leaks.append((username, verb, url, response.status_code))
    assert not leaks, leaks[:10]
    with college_context(a.college.id):
        assert export.counts() == before  # nothing of A changed
