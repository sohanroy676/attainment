"""A workflow environment on top of the results environment (synthetic data only)."""

from dataclasses import dataclass

from django.db import transaction

from apps.accounts.models import Role, ScopeType, User
from apps.accounts.services import assign_role
from apps.accounts.tests.helpers import make_user
from apps.assessments.models import Assessment
from apps.results.tests.helpers import REnv, make_results_env
from apps.tenancy.services import college_context
from apps.workflow import services as wf


@dataclass
class WEnv:
    r: REnv
    coordinator: User
    principal: User

    @property
    def env(self):  # type: ignore[no-untyped-def]
        return self.r.env

    @property
    def offering(self):  # type: ignore[no-untyped-def]
        return self.r.offering

    @property
    def programme(self):  # type: ignore[no-untyped-def]
        return self.r.programme

    @property
    def college(self):  # type: ignore[no-untyped-def]
        return self.r.college


def make_wf_env(code: str = "a") -> WEnv:
    r = make_results_env(code)
    coordinator = make_user(r.college, f"{code}.coordinator")
    principal = make_user(r.college, f"{code}.principal")
    with transaction.atomic(), college_context(r.college.id):
        assign_role(coordinator, Role.COORDINATOR, ScopeType.OFFERING, r.offering.pk)
        assign_role(principal, Role.PRINCIPAL)
    return WEnv(r, coordinator, principal)


def internal(w: WEnv) -> Assessment:
    with college_context(w.college.id):
        return Assessment.objects.get(pk=w.env.internal.pk)


def see(w: WEnv) -> Assessment:
    with college_context(w.college.id):
        return Assessment.objects.get(pk=w.env.see.pk)


def submit_all(w: WEnv) -> None:
    """Every section submits every assessment (the exam branch submits the SEE)."""
    env = w.env
    for section, lecturer in ((env.s.section_a, env.lecturer_a), (env.s.section_b, env.lecturer_b)):
        wf.transition_section(section, internal(w), "submit", lecturer)
        wf.transition_section(section, see(w), "submit", env.exam)


def accept_all(w: WEnv) -> None:
    submit_all(w)
    env = w.env
    for section in (env.s.section_a, env.s.section_b):
        for assessment in (internal(w), see(w)):
            wf.transition_section(section, assessment, "accept", w.coordinator)


def reviewed(w: WEnv) -> None:
    accept_all(w)
    wf.review(w.offering, w.programme, w.coordinator)


def approved(w: WEnv) -> None:
    reviewed(w)
    wf.approve(w.offering, w.programme, w.r.hod)


def signed(w: WEnv) -> None:
    approved(w)
    wf.sign(w.offering, w.programme, w.principal)
