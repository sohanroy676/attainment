"""The audit log's public interface: record an event, verify the chain.

Writers elsewhere call `record`. Nothing here, or anywhere, updates or deletes an event.
"""

import hashlib
import json
import uuid
from datetime import UTC
from typing import Any

from django.db import connection
from django.utils import timezone

from apps.tenancy.services import get_current_college_id

from .models import AuditEvent


def _json_safe(value: Any) -> Any:
    """Round-trip through JSON so the hashed form equals what the database returns."""
    return None if value is None else json.loads(json.dumps(value, default=str))


def _digest(hash_prev: str, fields: dict[str, Any]) -> str:
    payload = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((hash_prev + payload).encode()).hexdigest()


def _hashed_fields(event: AuditEvent) -> dict[str, Any]:
    return {
        "college_id": str(event.college_id),
        "seq": event.seq,
        "actor_id": None if event.actor_id is None else str(event.actor_id),
        "action": event.action,
        "entity": event.entity,
        "entity_id": event.entity_id,
        "before": event.before,
        "after": event.after,
        "reason": event.reason,
        "ip": event.ip,
        "at": event.at.astimezone(UTC).isoformat(),
    }


def record(
    action: str,
    entity: str,
    entity_id: object = "",
    actor_id: uuid.UUID | None = None,
    before: Any = None,
    after: Any = None,
    reason: str = "",
    ip: str | None = None,
) -> AuditEvent:
    """Append an event for the current college. Must run inside a transaction."""
    college_id = get_current_college_id()
    if college_id is None:
        raise RuntimeError("No current college: cannot write an audit event")
    if not connection.in_atomic_block:
        raise RuntimeError("Audit events are written inside a transaction")
    with connection.cursor() as cursor:
        # One writer at a time per college, so two requests cannot claim the same previous row.
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [str(college_id)])
    last = AuditEvent.objects.order_by("-seq").first()
    event = AuditEvent(
        college_id=college_id,
        seq=1 if last is None else last.seq + 1,
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        before=_json_safe(before),
        after=_json_safe(after),
        reason=reason,
        ip=ip,
        at=timezone.now().astimezone(UTC),
        hash_prev="" if last is None else last.hash,
    )
    event.hash = _digest(event.hash_prev, _hashed_fields(event))
    event.save(force_insert=True)
    return event


def verify_chain() -> bool:
    """Recompute the current college's chain. False means a row was changed or removed."""
    hash_prev = ""
    expected_seq = 1
    for event in AuditEvent.objects.order_by("seq").iterator():
        if (
            event.seq != expected_seq
            or event.hash_prev != hash_prev
            or event.hash != _digest(hash_prev, _hashed_fields(event))
        ):
            return False
        hash_prev = event.hash
        expected_seq += 1
    return True


def client_ip(request: Any) -> str | None:
    address = request.META.get("REMOTE_ADDR")
    return address or None


def snapshot(instance: Any) -> dict[str, Any]:
    """The fields of a model instance for the audit log.

    Fields named in the model's `audit_exclude` (names, identifier values) are left out: the log
    refers to people by internal id only, so anonymising a student never breaks the chain.
    """
    exclude = set(getattr(instance, "audit_exclude", ())) | {"college"}
    return {
        field.attname: getattr(instance, field.attname)
        for field in instance._meta.concrete_fields
        if field.name not in exclude and field.attname not in exclude
    }


def record_model(
    action: str,
    instance: Any,
    actor_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str = "",
    ip: str | None = None,
) -> AuditEvent:
    """Log a create, update or delete of a business record (`action`: created, updated, deleted)."""
    return record(
        f"{instance._meta.label_lower}.{action}",
        instance._meta.label_lower,
        entity_id=instance.pk,
        actor_id=actor_id,
        before=before,
        after=after,
        reason=reason,
        ip=ip,
    )
