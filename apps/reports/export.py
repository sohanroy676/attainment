"""The full college export: every tenant table, as one Excel file or one JSON file.

It is for portability and data requests, so it holds personal data. Only a role with
`data.export` may ask for it, and every export is written to the audit log. Password hashes and
binary file contents are left out (files are listed with their size and checksum).
"""

import io
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import openpyxl
from django.apps import apps
from django.db import models

from apps.tenancy.models import TenantModel

from .excel import add_rows

SKIPPED_FIELDS = {"password"}
SHEET_NAME_LIMIT = 31


def tenant_models() -> list[type[models.Model]]:
    found = [m for m in apps.get_models() if issubclass(m, TenantModel)]
    return sorted(found, key=lambda m: m._meta.label_lower)


def _fields(model: type[models.Model]) -> list[Any]:
    return [
        f
        for f in model._meta.concrete_fields
        if f.name not in SKIPPED_FIELDS and not isinstance(f, models.BinaryField)
    ]


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def table(model: type[models.Model]) -> tuple[list[str], list[list[Any]]]:
    """Column names and rows of one table, for the current college only (the tenant manager)."""
    fields = _fields(model)
    names = [f.attname for f in fields]
    rows = [
        [_plain(getattr(obj, name)) for name in names]
        for obj in model._default_manager.all().order_by("pk").iterator()
    ]
    return names, rows


def counts() -> dict[str, int]:
    return {m._meta.label_lower: m._default_manager.count() for m in tenant_models()}


def as_json() -> bytes:
    data = {}
    for model in tenant_models():
        names, rows = table(model)
        data[model._meta.label_lower] = [dict(zip(names, row, strict=True)) for row in rows]
    return json.dumps(data, default=str, indent=1, sort_keys=True).encode("utf-8")


def as_excel() -> bytes:
    book = openpyxl.Workbook()
    index = book.active
    if index is None:
        raise RuntimeError("A new workbook has no sheet")
    index.title = "Index"
    index.append(["Table", "Sheet", "Rows"])
    for n, model in enumerate(tenant_models(), start=1):
        names, rows = table(model)
        sheet_name = f"{n:02d} {model._meta.label_lower}"[:SHEET_NAME_LIMIT]
        index.append([model._meta.label_lower, sheet_name, len(rows)])
        sheet = book.create_sheet(sheet_name)
        add_rows(
            sheet,
            [
                names,
                *[
                    [json.dumps(v, default=str) if isinstance(v, dict | list) else v for v in row]
                    for row in rows
                ],
            ],
        )
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
