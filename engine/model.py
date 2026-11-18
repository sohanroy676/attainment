"""Plain data classes for engine input and output. No Django, no database."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class State(Enum):
    """The state of one mark cell. Blank, 0 and absent are different things."""

    ENTERED = "entered"  # a number was entered; 0 is a real mark
    ABSENT = "absent"  # marked absent
    BLANK = "blank"  # nothing entered (for example a choice question not answered)
    DROPPED = "dropped"  # set by ChoiceSelect: answered but not counted


@dataclass(frozen=True)
class Cell:
    state: State
    value: Decimal | None = None

    @staticmethod
    def entered(value: Decimal | int | str) -> "Cell":
        return Cell(State.ENTERED, Decimal(value))

    @staticmethod
    def absent() -> "Cell":
        return Cell(State.ABSENT)

    @staticmethod
    def blank() -> "Cell":
        return Cell(State.BLANK)


@dataclass(frozen=True)
class Part:
    """One question part on a paper."""

    id: str
    question: str
    max: Decimal
    co: str | None = None  # None for items that apply to every CO (quiz, assignment)
    choice_group: str | None = None  # None means compulsory


@dataclass(frozen=True)
class Override:
    """An approved pass mark for one part. The reason is mandatory."""

    pass_mark: Decimal
    reason: str


@dataclass(frozen=True)
class AssessmentInput:
    tool: str
    parts: tuple[Part, ...]
    marks: Mapping[str, Mapping[str, Cell]]  # student -> part id -> cell
    absent_whole: frozenset[str] = frozenset()  # students absent for the whole assessment


@dataclass(frozen=True)
class CourseInput:
    cos: tuple[str, ...]
    students: tuple[str, ...]  # enrolled
    assessments: Mapping[str, AssessmentInput]
    overrides: Mapping[tuple[str, str], Override] = field(default_factory=dict)  # (tool, part)
    indirect: Mapping[str, Decimal] = field(default_factory=dict)  # CO -> entered value
    target: Decimal | None = None


@dataclass(frozen=True)
class ToolValue:
    """What one tool says about one CO."""

    tool: str
    co: str
    percent: Decimal | None
    level: Decimal | None
    status: str  # "ok", "missing" (no data for this CO), "blocked" (stopped for review)
    flag: str | None = None


@dataclass(frozen=True)
class CoValue:
    """A value for one CO at some stage, or why there is none."""

    value: Decimal | None
    status: str  # "ok", "missing", "blocked"
    note: str | None = None


@dataclass(frozen=True)
class CourseResult:
    tool_values: Mapping[str, Mapping[str, ToolValue]]
    merged: Mapping[str, Mapping[str, CoValue]]
    direct: Mapping[str, CoValue]
    final: Mapping[str, CoValue]
    course: Decimal | None
    course_status: str  # "ok" or "no value"
    attained: bool | None
    target: Decimal | None
    complete: bool  # False (provisional) when anything is blocked or missing
    flags: tuple[str, ...]
    engine_version: str
    input_hash: str
