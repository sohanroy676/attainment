"""The explanation trace: every step writes what it used, the rule, and what it produced."""

from dataclasses import dataclass, field
from decimal import Decimal

from .precision import decimal_text

JsonValue = str | int | bool | None | list[str]


@dataclass(frozen=True)
class TraceEntry:
    step: str
    key: str  # what the entry is about, for example "SEE/CO2" or "INT1/Q3a"
    message: str
    data: dict[str, JsonValue]


@dataclass
class Trace:
    entries: list[TraceEntry] = field(default_factory=list)

    def add(self, step: str, key: str, message: str, **data: object) -> None:
        self.entries.append(TraceEntry(step, key, message, {k: _plain(v) for k, v in data.items()}))

    def for_key(self, prefix: str) -> list[TraceEntry]:
        return [e for e in self.entries if e.key == prefix or e.key.startswith(prefix + "/")]

    def text(self) -> str:
        return "\n".join(f"[{e.step}] {e.key}: {e.message}" for e in self.entries)


def _plain(value: object) -> JsonValue:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, list | tuple | set | frozenset):
        return [
            str(_plain(v)) for v in (sorted(value) if isinstance(value, set | frozenset) else value)
        ]
    return str(value)
