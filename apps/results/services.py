"""Results' public interface: build the input, run the engine, store the run, explain it.

The engine itself never touches the database. This module collects an input snapshot from the
other modules (through their services), runs `engine.run_offering`, and stores the outcome with
the method version, engine version and input hash.
"""

import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.academics.models import CourseOffering, Programme, Section
from apps.accounts.models import User
from apps.assessments import services as papers
from apps.audit import services as audit
from apps.marks import services as marks
from apps.methodology import services as methods
from apps.outcomes import services as outcomes
from apps.outcomes.models import CourseDefinitionVersion, Target
from apps.roster.models import Enrolment
from apps.tenancy.services import college_context, get_current_college_id
from engine.display import display
from engine.hashing import result_to_dict
from engine.model import CourseInput, OfferingInput, Override
from engine.pipeline import run_offering
from engine.precision import decimal_text
from engine.schema import MethodConfig
from engine.trace import Trace

from .models import CalculationRun, IndirectValue, ResultValue

log = logging.getLogger(__name__)


@dataclass
class Built:
    offering_input: OfferingInput | None = None
    config: MethodConfig | None = None
    version: Any = None
    checklist: list[str] = field(default_factory=list)


def programmes_of(offering: CourseOffering) -> list[Programme]:
    ids = offering.sections.values_list("programme_id", flat=True).distinct()
    return list(Programme.objects.filter(pk__in=ids).order_by("name"))


def latest_definition(offering: CourseOffering) -> CourseDefinitionVersion | None:
    return offering.course.definitions.order_by("-version").first()


def build(offering: CourseOffering, programme: Programme) -> Built:
    """The input snapshot for one offering as seen by one programme (its sections only)."""
    built = Built()
    found = methods.method_for_offering(offering, programme_id=programme.pk)
    if found is None:
        built.checklist.append("No method is assigned to this course (or none is active yet).")
        return built
    version, _assignment = found
    built.version, built.config = version, methods.parse_config(version.config_text)
    definition = latest_definition(offering)
    if definition is None:
        built.checklist.append("The course has no outcomes (COs) defined.")
        return built
    cos = tuple(co.code for co in definition.outcomes.all())
    sections = list(offering.sections.filter(programme=programme).order_by("name"))
    if not sections:
        built.checklist.append("No section of this course belongs to this programme.")
        return built

    tools = built.config.tools
    assessments = {a.tool: a for a in offering.assessments.all() if a.tool in tools}
    overrides = {
        key: Override(pass_mark, reason)
        for key, (pass_mark, reason) in papers.approved_overrides(offering).items()
    }
    for tool in tools:
        if tool not in assessments:
            built.checklist.append(f"There is no paper for {tool}.")
        else:
            for problem in papers.validate_paper(assessments[tool]):
                built.checklist.append(f"{tool}: {problem}")
    section_inputs: dict[str, CourseInput] = {}
    for section in sections:
        enrolled = list(Enrolment.objects.filter(section=section, status=Enrolment.Status.ENROLLED))
        students = tuple(sorted(str(e.student_id) for e in enrolled))
        engine_assessments = {}
        for tool, assessment in assessments.items():
            data = marks.engine_assessment(assessment, [section])
            engine_assessments[tool] = data
            missing = len(students) - len(data.marks)
            if missing > 0:
                built.checklist.append(
                    f"Section {section.name}: {missing} enrolled student(s) have no marks for "
                    f"{assessment.name}."
                )
        section_inputs[section.name] = CourseInput(
            cos=cos, students=students, assessments=engine_assessments, overrides=overrides
        )
    indirect = {i.co_code: i.value for i in IndirectValue.objects.filter(offering=offering)}
    if built.config.final.indirect > 0:
        for co in cos:
            if co not in indirect:
                built.checklist.append(f"No indirect value has been entered for {co}.")
    target = Target.objects.filter(offering=offering).first()
    if target is None:
        built.checklist.append("No target has been set for this course.")
    mapping = outcomes.engine_mapping(definition, programme)
    if not any(mapping.values()):
        built.checklist.append("The CO-PO map is empty, so no PO or PSO values are produced.")
    built.offering_input = OfferingInput(
        cos=cos,
        sections=section_inputs,
        indirect=indirect,
        target=None if target is None else target.value,
        mapping={co: row for co, row in mapping.items() if row},
    )
    return built


def _trace_json(trace: Trace) -> list[dict[str, Any]]:
    return [
        {"step": e.step, "key": e.key, "message": e.message, "data": e.data} for e in trace.entries
    ]


def calculate(
    offering: CourseOffering,
    programme: Programme,
    actor: User | None = None,
    keep: bool = False,
) -> CalculationRun:
    """Run the engine for an offering and one programme and store the result.

    An automatic run replaces the previous latest run that was not kept; a kept run (snapshot)
    stays for good. The run is provisional until nothing is blocked and nothing is missing.
    """
    built = build(offering, programme)
    outputs: dict[str, Any] = {}
    trace: dict[str, Any] = {}
    status = CalculationRun.Status.PROVISIONAL
    engine_version = input_hash = ""
    result = None
    if built.offering_input is not None and built.config is not None:
        out = run_offering(built.config, built.offering_input)
        result = out.result
        engine_version, input_hash = result.engine_version, result.input_hash
        outputs = {
            "course": result_to_dict(result),
            "sections": {s: result_to_dict(o.result) for s, o in out.sections.items()},
            "cos": list(built.offering_input.cos),
            "attained": result.attained,
        }
        trace = {
            "offering": _trace_json(out.trace),
            "sections": {s: _trace_json(o.trace) for s, o in out.sections.items()},
        }
        if result.complete and not built.checklist:
            status = CalculationRun.Status.COMPLETE
        for tool, per_co in result.tool_values.items():
            for co, value in per_co.items():
                if value.status == "blocked":
                    built.checklist.append(
                        f"{tool} for {co} is stopped for review: {value.flag or 'blocked'}."
                    )
        for co, final in result.final.items():
            if final.status == "blocked" and final.note:
                built.checklist.append(f"{co} is stopped for review: {final.note}.")
    with transaction.atomic():
        CalculationRun.objects.filter(
            offering=offering, programme=programme, is_latest=True, kept=False
        ).delete()
        CalculationRun.objects.filter(
            offering=offering, programme=programme, is_latest=True
        ).update(is_latest=False)
        run = CalculationRun.objects.create(
            offering=offering,
            programme=programme,
            method_version=built.version,
            engine_version=engine_version,
            input_hash=input_hash,
            started_by=actor,
            at=timezone.now(),
            status=status,
            kept=keep,
            outputs=outputs,
            trace=trace,
            checklist=built.checklist,
        )
        if result is not None and built.config is not None:
            _store_values(run, built.config, result)
        audit.record_model(
            "created", run, actor_id=None if actor is None else actor.pk,
            after={"status": status, "kept": keep, "input_hash": input_hash},
        )  # fmt: skip
    return run


def _store_values(run: CalculationRun, config: MethodConfig, result: Any) -> None:
    def put(
        entity: str, key: str, value: Decimal | None, status: str, level: str, flags: list[str]
    ) -> None:
        shown = "" if value is None else str(display(config.precision, level, value))
        ResultValue.objects.create(
            run=run, entity=entity, key=key, status=status, flags=flags,
            value=decimal_text(value) or "", display=shown,
        )  # fmt: skip

    for co, v in result.direct.items():
        put("co_direct", co, v.value, v.status, "co", [])
    for co, v in result.final.items():
        put("co_final", co, v.value, v.status, "co", [v.note] if v.note else [])
    course_status = "ok" if result.course is not None else "missing"
    put("course", "course", result.course, course_status, "course", list(result.flags))
    for po, v in result.po.items():
        put("po", po, v.value, v.status, "po", [v.note] if v.note else [])


def latest_run(offering: CourseOffering, programme: Programme) -> CalculationRun | None:
    return CalculationRun.objects.filter(
        offering=offering, programme=programme, is_latest=True
    ).first()


def snapshot(offering: CourseOffering, programme: Programme, actor: User) -> CalculationRun:
    """Keep a run permanently (design 6.6: at submit, approve, sign, or on request)."""
    return calculate(offering, programme, actor=actor, keep=True)


# explaining a number ---------------------------------------
def explain(run: CalculationRun, key: str) -> list[tuple[str, dict[str, Any]]]:
    """The trace entries behind one value: (scope, entry) pairs, scope being "course" or a section.

    `key` is "TOOL/CO" (for example SEE/CO2), "direct/CO1", "final/CO1", "PO3", or "course".
    For TOOL/CO the entries are the parts tagged to that CO, the aggregation, the band, and the
    choice-selection and normalisation steps of the tool.
    """
    found: list[tuple[str, dict[str, Any]]] = []
    traces = {"course": run.trace.get("offering", [])} | {
        f"section {name}": entries for name, entries in run.trace.get("sections", {}).items()
    }
    tool, _, co = key.partition("/") if "/" in key else (key, "", "")
    for scope, entries in traces.items():
        for entry in entries:
            k, step = entry["key"], entry["step"]
            if k == key:
                found.append((scope, entry))
            elif co and step == "QuestionPass" and k.startswith(tool + "/"):
                if entry["data"].get("co") == co:
                    found.append((scope, entry))
            elif co and step in ("ChoiceSelect", "NormaliseStates") and k.split("/")[0] == tool:
                found.append((scope, entry))
    return found


# indirect values -------------------------------------------
def set_indirect(
    offering: CourseOffering, values: dict[str, Decimal | str], note: str, actor: User
) -> None:
    """Enter indirect values (one per CO). They are labelled "entered, not measured"."""
    definition = latest_definition(offering)
    known = {co.code for co in definition.outcomes.all()} if definition else set()
    for code, raw in values.items():
        if code not in known:
            raise ValidationError(f"{code} is not an outcome of this course.")
        value = Decimal(raw)
        if not 0 <= value <= 10:
            raise ValidationError(f"{code}: the value must be between 0 and 10.")
    with transaction.atomic():
        for code, raw in values.items():
            row, created = IndirectValue.objects.update_or_create(
                offering=offering, co_code=code,
                defaults={"value": Decimal(raw), "source_note": note, "entered_by": actor},
            )  # fmt: skip
            audit.record_model(
                "created" if created else "updated", row, actor_id=actor.pk,
                after=audit.snapshot(row), reason="indirect value entered, not measured",
            )  # fmt: skip


# automatic recalculation -----------------------------------
def mark_dirty(offering_id: uuid.UUID) -> None:
    """Ask for the offering to be recalculated once, after the current transaction commits."""
    college_id = get_current_college_id()
    if college_id is None:
        return
    pending: set[tuple[uuid.UUID, uuid.UUID]] | None = getattr(connection, "_results_dirty", None)
    if pending is None:
        pending = connection._results_dirty = set()  # type: ignore[attr-defined]
    pending.add((college_id, offering_id))
    # Registered every time on purpose: a rolled-back transaction leaves its entries behind, so
    # a "register once" flag would silence later commits. The flush is idempotent, so the first
    # callback to run does all the work and the others find nothing pending.
    transaction.on_commit(_flush_dirty)


def _flush_dirty() -> None:
    pending: set[tuple[uuid.UUID, uuid.UUID]] = getattr(connection, "_results_dirty", None) or set()
    connection._results_dirty = None  # type: ignore[attr-defined]
    for college_id, offering_id in sorted(pending, key=str):
        try:
            with college_context(college_id):
                offering = CourseOffering.objects.filter(pk=offering_id).first()
                if offering is not None:
                    for programme in programmes_of(offering):
                        calculate(offering, programme)
        except Exception:  # noqa: BLE001 - saving marks must never fail because a recalculation did
            log.exception("Recalculation of offering %s failed", offering_id)


def offerings_with_runs() -> list[uuid.UUID]:
    return list(CalculationRun.objects.values_list("offering_id", flat=True).distinct())


def section_result(run: CalculationRun, section: Section) -> dict[str, Any] | None:
    return run.outputs.get("sections", {}).get(section.name)
