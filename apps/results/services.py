"""Results' public interface: build the input, run the engine, store the run, explain it.

The engine itself never touches the database. This module collects an input snapshot from the
other modules (through their services), runs `engine.run_offering`, and stores the outcome with
the method version, engine version and input hash.
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.academics.models import Batch, CourseOffering, Programme, Section
from apps.accounts.models import User
from apps.assessments import services as papers
from apps.audit import services as audit
from apps.marks import services as marks
from apps.methodology import services as methods
from apps.outcomes import services as outcomes
from apps.outcomes.models import CourseDefinitionVersion, ProgrammeOutcome, Target
from apps.roster.models import Enrolment
from apps.tenancy.services import college_context, get_current_college_id
from engine.batch import BatchCourse, BatchInput, batch_result_to_dict, run_batch
from engine.compare import compare_values
from engine.display import display
from engine.hashing import result_to_dict
from engine.model import CourseInput, OfferingInput, Override
from engine.pipeline import run_offering
from engine.precision import decimal_text
from engine.schema import MethodConfig
from engine.trace import Trace

from .models import (
    BatchIndirect,
    BatchRun,
    CalculationRun,
    HistoricResult,
    IndirectValue,
    ResultValue,
)

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


def run_content_hash(run: CalculationRun) -> str:
    """SHA-256 over everything a signature vouches for: inputs, method version and outputs."""
    payload = {
        "input_hash": run.input_hash,
        "engine_version": run.engine_version,
        "method_hash": "" if run.method_version is None else run.method_version.content_hash,
        "outputs": run.outputs,
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def seal(run: CalculationRun, actor: User) -> CalculationRun:
    """Freeze a kept, complete run at sign-off. After this the database refuses any change."""
    if run.signed:
        raise ValidationError("This run is already signed.")
    if not run.kept:
        raise ValidationError("Only a kept run can be signed.")
    if run.status != CalculationRun.Status.COMPLETE:
        raise ValidationError("A result that is stopped for review cannot be signed.")
    run.signed = True
    run.content_hash = run_content_hash(run)
    run.save(update_fields=["signed", "content_hash", "updated_at"])
    audit.record_model(
        "updated", run, actor_id=actor.pk, after={"signed": True, "content_hash": run.content_hash}
    )
    return run


def signed_run(offering: CourseOffering, programme: Programme) -> CalculationRun | None:
    """The newest signed run, or None."""
    return (
        CalculationRun.objects.filter(offering=offering, programme=programme, signed=True)
        .order_by("-at")
        .first()
    )


def differs_from_signed(offering: CourseOffering, programme: Programme) -> bool:
    """True when the current result no longer matches the signed one (marks or method moved on)."""
    signed = signed_run(offering, programme)
    latest = latest_run(offering, programme)
    if signed is None or latest is None or latest.pk == signed.pk:
        return False
    return latest.input_hash != signed.input_hash


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


# batch roll-up ---------------------------------------------
def batch_outcomes(programme: Programme) -> list[ProgrammeOutcome]:
    """The POs then the PSOs of a programme (latest version of each code), in report order."""
    newest: dict[str, ProgrammeOutcome] = {}
    for row in ProgrammeOutcome.objects.filter(
        programme=programme, kind__in=[ProgrammeOutcome.Kind.PO, ProgrammeOutcome.Kind.PSO]
    ).order_by("version"):
        newest[row.code] = row

    def order(row: ProgrammeOutcome) -> tuple[bool, int, str]:
        digits = "".join(ch for ch in row.code if ch.isdigit())
        return (row.kind == ProgrammeOutcome.Kind.PSO, int(digits or 0), row.code)

    return sorted(newest.values(), key=order)


def batch_offerings(batch: Batch) -> list[CourseOffering]:
    """Every offering that has a section of this batch (and its programme)."""
    ids = (
        Section.objects.filter(programme=batch.programme, batch=batch)
        .values_list("offering_id", flat=True)
        .distinct()
    )
    return list(
        CourseOffering.objects.filter(pk__in=ids)
        .select_related("course", "term")
        .order_by("course__title", "term__academic_year__start_date", "term__number")
    )


def set_batch_indirect(
    batch: Batch, values: dict[str, Decimal | str], note: str, actor: User
) -> None:
    """Enter indirect values per PO or PSO of a batch. They are "entered, not measured"."""
    known = {o.code for o in batch_outcomes(batch.programme)}
    for code, raw in values.items():
        if code not in known:
            raise ValidationError(f"{code} is not an outcome of this programme.")
        if not 0 <= Decimal(raw) <= 10:
            raise ValidationError(f"{code}: the value must be between 0 and 10.")
    with transaction.atomic():
        for code, raw in values.items():
            row, created = BatchIndirect.objects.update_or_create(
                batch=batch, outcome_code=code,
                defaults={"value": Decimal(raw), "source_note": note, "entered_by": actor},
            )  # fmt: skip
            audit.record_model(
                "created" if created else "updated", row, actor_id=actor.pk,
                after=audit.snapshot(row), reason="indirect value entered, not measured",
            )  # fmt: skip


def _course_po_values(run: CalculationRun) -> dict[str, Decimal | None]:
    return {v.key: (Decimal(v.value) if v.value else None) for v in run.values.filter(entity="po")}


def calculate_batch(
    batch: Batch,
    actor: User | None = None,
    include_unsigned: bool = False,
    keep: bool = False,
) -> BatchRun:
    """Roll the course results of a programme batch up into PO and PSO values.

    By default only signed course runs go in, and the ones left out are listed with the reason.
    With `include_unsigned` the newest run of an unsigned course is used and marked as such.
    The batch is provisional while anything is left out, unsigned, missing or stopped.
    """
    programme = batch.programme
    outcome_rows = batch_outcomes(programme)
    checklist: list[str] = []
    offerings = batch_offerings(batch)
    included: list[tuple[CourseOffering, CalculationRun]] = []
    excluded: list[dict[str, str]] = []
    for offering in offerings:
        run = signed_run(offering, programme)
        if run is None and include_unsigned:
            run = latest_run(offering, programme)
        if run is None:
            reason = "no result yet" if include_unsigned else "not signed yet"
            excluded.append(
                {"offering": str(offering.pk), "name": offering.course.title, "reason": reason}
            )
            checklist.append(f"{offering.course.title} is left out: {reason}.")
            continue
        if not run.signed:
            checklist.append(f"{offering.course.title} is included but not signed.")
        if run.status != CalculationRun.Status.COMPLETE:
            checklist.append(f"{offering.course.title} is included but its result is provisional.")
        if (
            Section.objects.filter(offering=offering, programme=programme)
            .exclude(batch=batch)
            .exists()
        ):
            checklist.append(
                f"{offering.course.title} also has sections of another batch; its course "
                "result counts in each batch it serves."
            )
        included.append((offering, run))

    version = None
    if offerings:
        found = methods.method_for_offering(offerings[0], programme_id=programme.pk)
        version = None if found is None else found[0]
    if version is None and included:
        version = included[0][1].method_version
    outputs: dict[str, Any] = {"outcomes_order": [o.code for o in outcome_rows]}
    trace: list[dict[str, Any]] = []
    engine_version = input_hash = ""
    status = "provisional"
    if version is None:
        checklist.append("No method is assigned to this programme (or none is active yet).")
    elif not outcome_rows:
        checklist.append("The programme has no POs or PSOs defined.")
    else:
        config = methods.parse_config(version.config_text)
        targets = {
            t.outcome.code: t.value
            for t in Target.objects.filter(batch=batch).select_related("outcome")
        }
        indirect = {i.outcome_code: i.value for i in BatchIndirect.objects.filter(batch=batch)}
        for row in outcome_rows:
            if row.code not in targets:
                checklist.append(f"No target has been set for {row.code}.")
            if config.batch.indirect > 0 and row.code not in indirect:
                checklist.append(f"No indirect value has been entered for {row.code}.")
        batch_input = BatchInput(
            courses=tuple(
                BatchCourse(
                    str(offering.pk),
                    offering.course.title,
                    offering.course.category,
                    _course_po_values(run),
                    run.outputs.get("attained"),
                )  # fmt: skip
                for offering, run in included
            ),
            outcomes=tuple(o.code for o in outcome_rows),
            targets=targets,
            indirect=indirect,
        )
        out = run_batch(config, batch_input)
        engine_version, input_hash = out.result.engine_version, out.result.input_hash
        outputs.update(batch_result_to_dict(out.result))
        trace = _trace_json(out.trace)
        if out.result.complete and not checklist:
            status = "complete"
    used = [
        {
            "offering": str(offering.pk), "name": offering.course.title,
            "category": offering.course.category, "run": str(run.pk), "signed": run.signed,
            "run_hash": run.content_hash or run.input_hash,
        }
        for offering, run in included
    ]  # fmt: skip
    with transaction.atomic():
        BatchRun.objects.filter(batch=batch, is_latest=True, kept=False).delete()
        BatchRun.objects.filter(batch=batch, is_latest=True).update(is_latest=False)
        batch_run = BatchRun.objects.create(
            batch=batch, method_version=version, include_unsigned=include_unsigned,
            engine_version=engine_version, input_hash=input_hash, started_by=actor,
            at=timezone.now(), status=status, kept=keep, outputs=outputs, trace=trace,
            courses=used, excluded=excluded, checklist=checklist,
        )  # fmt: skip
        audit.record_model(
            "created", batch_run, actor_id=None if actor is None else actor.pk,
            after={"status": status, "kept": keep, "courses": len(used)},
        )  # fmt: skip
    return batch_run


def latest_batch_run(batch: Batch) -> BatchRun | None:
    return BatchRun.objects.filter(batch=batch, is_latest=True).first()


def set_batch_targets(batch: Batch, values: dict[str, Decimal | str], actor: User) -> None:
    """Set the target of each named PO or PSO for a batch (one value each, 0 to 10)."""
    wanted = {o.code: o for o in batch_outcomes(batch.programme)}
    for code in values:
        if code not in wanted:
            raise ValidationError(f"{code} is not an outcome of this programme.")
    with transaction.atomic():
        for code, raw in values.items():
            outcomes.set_target(raw, outcome=wanted[code], batch=batch, actor=actor)


def batch_inputs(batch: Batch) -> list[tuple[str, str, str]]:
    """(outcome code, target text, indirect text) for every PO and PSO of the batch."""
    targets = {
        t.outcome.code: t.value
        for t in Target.objects.filter(batch=batch).select_related("outcome")
    }
    indirect = {i.outcome_code: i.value for i in BatchIndirect.objects.filter(batch=batch)}
    return [
        (
            o.code,
            "" if o.code not in targets else str(targets[o.code].normalize()),
            "" if o.code not in indirect else str(indirect[o.code].normalize()),
        )
        for o in batch_outcomes(batch.programme)
    ]


def batch_content_hash(run: BatchRun) -> str:
    """SHA-256 over everything a batch signature vouches for: the inputs, the course runs that
    went in (and the ones left out), the method version and the outputs."""
    payload = {
        "input_hash": run.input_hash,
        "engine_version": run.engine_version,
        "method_hash": "" if run.method_version is None else run.method_version.content_hash,
        "courses": run.courses,
        "excluded": run.excluded,
        "outputs": run.outputs,
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def seal_batch(run: BatchRun, actor: User) -> BatchRun:
    """Freeze a kept, complete batch run at sign-off. After this the database refuses changes."""
    if run.signed:
        raise ValidationError("This batch result is already signed.")
    if not run.kept:
        raise ValidationError("Only a kept batch result can be signed.")
    if run.status != "complete":
        raise ValidationError("A batch result that is not complete cannot be signed.")
    if run.include_unsigned:
        raise ValidationError("A batch result with unsigned courses cannot be signed.")
    run.signed = True
    run.content_hash = batch_content_hash(run)
    run.save(update_fields=["signed", "content_hash", "updated_at"])
    audit.record_model(
        "updated", run, actor_id=actor.pk, after={"signed": True, "content_hash": run.content_hash}
    )
    return run


def signed_batch_run(batch: Batch) -> BatchRun | None:
    """The newest signed batch run, or None."""
    return BatchRun.objects.filter(batch=batch, signed=True).order_by("-at").first()


def batch_differs_from_signed(batch: Batch) -> bool:
    """True when the current batch result no longer matches the signed one."""
    signed = signed_batch_run(batch)
    latest = latest_batch_run(batch)
    if signed is None or latest is None or latest.pk == signed.pk:
        return False
    return latest.input_hash != signed.input_hash


# earlier batches and the old workbook (design 8.13) ---------
def store_historic(
    batch: Batch,
    values: dict[tuple[str, str], Decimal],
    source: Any,
    actor: User | None = None,
) -> int:
    """Store PO values typed in an old workbook for a batch: (kind, outcome code) -> value.

    The values for the kinds in `values` are replaced as a whole (the audit log keeps the old
    ones). Returns how many values were stored.
    """
    known = {o.code for o in batch_outcomes(batch.programme)}
    kinds = {kind for kind, _code in values}
    for kind, code in values:
        if kind not in HistoricResult.Kind.values:
            raise ValidationError(f"{kind} is not a kind of earlier result.")
        if code not in known:
            raise ValidationError(f"{code} is not an outcome of this programme.")
    for (_kind, code), value in values.items():
        if not 0 <= value <= 10:
            raise ValidationError(f"{code}: the value {value} must be between 0 and 10.")
    actor_id = None if actor is None else actor.pk
    with transaction.atomic():
        for old in HistoricResult.objects.filter(batch=batch, kind__in=kinds):
            audit.record_model(
                "deleted", old, actor_id=actor_id, before=audit.snapshot(old),
                reason="replaced by a new upload",
            )  # fmt: skip
            old.delete()
        for (kind, code), value in sorted(values.items()):
            row = HistoricResult.objects.create(
                batch=batch, kind=kind, key=code, value=decimal_text(value) or "", source=source
            )
            audit.record_model("created", row, actor_id=actor_id, after=audit.snapshot(row))
    return len(values)


def historic_values(batch: Batch, kind: str) -> dict[str, Decimal]:
    return {h.key: Decimal(h.value) for h in HistoricResult.objects.filter(batch=batch, kind=kind)}


def earlier_batches(batch: Batch, count: int = 2) -> list[Batch]:
    """The `count` batches of the same programme that finished before this one, oldest first."""
    found = Batch.objects.filter(
        programme=batch.programme, start_year__lt=batch.start_year
    ).order_by("-start_year")[:count]
    return list(reversed(list(found)))


@dataclass
class BatchColumn:
    batch: Batch
    source: str  # "signed", "imported", "calculated", "provisional" or "none"
    values: dict[str, str | None] = field(default_factory=dict)  # code -> shown text


def _run_totals(run: BatchRun, codes: list[str]) -> dict[str, str | None]:
    config = (
        None if run.method_version is None else methods.parse_config(run.method_version.config_text)
    )
    shown: dict[str, str | None] = {}
    for code in codes:
        raw = run.outputs.get("outcomes", {}).get(code)
        total = None if raw is None else raw[3]
        shown[code] = (
            None
            if total is None or config is None
            else str(display(config.precision, "batch", Decimal(total)))
        )
    return shown


def comparison_columns(batch: Batch) -> list[BatchColumn]:
    """PO and PSO totals of this batch and the two before it, side by side.

    This batch shows its newest result. An earlier batch shows its signed result if it has one,
    else the values imported from its workbook, else its newest calculated result.
    """
    codes = [o.code for o in batch_outcomes(batch.programme)]
    columns: list[BatchColumn] = []
    for earlier in earlier_batches(batch):
        signed = signed_batch_run(earlier)
        imported = historic_values(earlier, HistoricResult.Kind.PO_TOTAL)
        latest = latest_batch_run(earlier)
        if signed is not None:
            columns.append(BatchColumn(earlier, "signed", _run_totals(signed, codes)))
        elif imported:
            columns.append(
                BatchColumn(earlier, "imported", {c: _text(imported.get(c)) for c in codes})
            )
        elif latest is not None:
            columns.append(BatchColumn(earlier, "provisional", _run_totals(latest, codes)))
        else:
            columns.append(BatchColumn(earlier, "none", dict.fromkeys(codes)))
    run = latest_batch_run(batch)
    if run is None:
        columns.append(BatchColumn(batch, "none", dict.fromkeys(codes)))
    else:
        label = (
            "signed" if run.signed else "calculated" if run.status == "complete" else "provisional"
        )
        columns.append(BatchColumn(batch, label, _run_totals(run, codes)))
    return columns


def _text(value: Decimal | None) -> str | None:
    return None if value is None else decimal_text(value)


@dataclass
class SideBySideRow:
    code: str
    kind: str
    computed: str
    imported: str
    difference: str
    differs: bool
    note: str


def compare_with_imported(batch: Batch) -> list[SideBySideRow]:
    """The newest computed PO values against the ones typed in the batch's old workbook.

    A row differs when the two values differ at the method's batch display precision.
    """
    run = latest_batch_run(batch)
    if run is None or run.method_version is None:
        return []
    config = methods.parse_config(run.method_version.config_text)
    rows: list[SideBySideRow] = []
    for kind, position in ((HistoricResult.Kind.PO_DIRECT, 1), (HistoricResult.Kind.PO_TOTAL, 3)):
        imported = historic_values(batch, kind)
        if not imported:
            continue
        for code in run.outputs.get("outcomes_order", []):
            raw = run.outputs.get("outcomes", {}).get(code)
            computed = None if raw is None or raw[position] is None else Decimal(raw[position])
            result = compare_values(config.precision, "batch", computed, imported.get(code))

            def shown(value: Decimal | None) -> str:
                return "-" if value is None else str(display(config.precision, "batch", value))

            rows.append(
                SideBySideRow(
                    code,
                    str(HistoricResult.Kind(kind).label),
                    shown(result.computed),
                    "-" if result.imported is None else decimal_text(result.imported) or "-",
                    "-" if result.difference is None else decimal_text(result.difference) or "0",
                    result.differs,
                    result.note,
                )  # fmt: skip
            )
    return rows
