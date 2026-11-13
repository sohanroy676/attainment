"""The method configuration (`attainment-method/1`), validated by Pydantic.

A method is data built from the fixed step catalogue. Validation rejects anything the engine
could not run safely: weights that do not sum to 1, overlapping bands, references to tools that
do not exist, percentages outside 0 to 100. Messages name the field.
"""

import json
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError

from .errors import MethodConfigError
from .precision import Mode

Percent = Annotated[Decimal, Field(ge=0, le=100)]
Weight = Annotated[Decimal, Field(ge=0, le=1)]
Boundary = Literal[">=", ">"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Band(_Strict):
    min_pct: Percent
    level: Decimal
    label: str = ""


class BelowLowest(_Strict):
    flag: bool = True
    # What later steps use for a result below the lowest band: stop for review, 0, or a value.
    value_for_calc: Literal["block", "zero"] | Decimal = "block"


class Levels(_Strict):
    bands: list[Band] = Field(min_length=1)
    below_lowest: BelowLowest = BelowLowest()

    @field_validator("bands")
    @classmethod
    def bands_descend_without_overlap(cls, bands: list[Band]) -> list[Band]:
        minimums = [b.min_pct for b in bands]
        if any(a <= b for a, b in zip(minimums, minimums[1:], strict=False)):
            raise PydanticCustomError(
                "bands", "bands must be listed from highest to lowest minimum, with no two equal"
            )
        levels = [b.level for b in bands]
        if any(a <= b for a, b in zip(levels, levels[1:], strict=False)):
            raise PydanticCustomError("bands", "a higher band must give a higher level")
        return bands


class PrecisionRule(_Strict):
    mode: Mode = "truncate"
    places: int = Field(default=2, ge=0, le=10)


class Precision(_Strict):
    default: PrecisionRule = PrecisionRule()
    co: PrecisionRule | None = None
    course: PrecisionRule | None = None
    question_pct: PrecisionRule | None = None
    compare_with: Literal["unrounded", "displayed"] = "unrounded"


class ChoiceRule(_Strict):
    best_n: int = Field(ge=1)
    best_k_parts: dict[str, int] = {}


class QuestionWiseTool(_Strict):
    behaviour: Literal["question_wise"]
    pass_pct: Percent
    boundary: Boundary = ">="
    denominator: Literal["by_choice", "attempted", "sat", "enrolled", "fixed"] = "by_choice"
    fixed_n: int | None = Field(default=None, ge=1)
    absent: Literal["zero", "exclude", "error"] = "exclude"
    whole_assessment_absent: Literal["exclude", "count_as_fail"] = "exclude"
    choice: dict[str, ChoiceRule] = {}  # choice group id -> rule
    small_group_warning: int = Field(default=10, ge=0)

    @model_validator(mode="after")
    def fixed_needs_a_count(self) -> "QuestionWiseTool":
        if self.denominator == "fixed" and self.fixed_n is None:
            raise PydanticCustomError("fixed_n", "denominator 'fixed' needs fixed_n")
        return self


class PerStudentAverageTool(_Strict):
    behaviour: Literal["per_student_average"]
    max: Decimal = Field(gt=0)
    pass_pct: Percent
    boundary: Boundary = ">="
    absent: Literal["zero", "skip", "error"] = "zero"
    applies_to: Literal["all_cos"] | list[str] = "all_cos"


class SingleTotalTool(_Strict):
    behaviour: Literal["single_total"]
    max: Decimal = Field(gt=0)
    pass_mark: Decimal | None = Field(default=None, ge=0)
    pass_pct: Percent | None = None
    boundary: Boundary = ">="
    absent: Literal["zero", "exclude", "error"] = "exclude"
    applies_to: Literal["all_cos"] | list[str] = "all_cos"

    @model_validator(mode="after")
    def one_pass_rule(self) -> "SingleTotalTool":
        if (self.pass_mark is None) == (self.pass_pct is None):
            raise PydanticCustomError("pass", "give exactly one of pass_mark and pass_pct")
        if self.pass_mark is not None and self.pass_mark > self.max:
            raise PydanticCustomError("pass_mark", "pass_mark cannot exceed max")
        return self


Tool = Annotated[
    QuestionWiseTool | PerStudentAverageTool | SingleTotalTool, Field(discriminator="behaviour")
]


class Merge(_Strict):
    sources: list[str] = Field(alias="from", min_length=2)
    method: Literal["average"] = "average"

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Final(_Strict):
    direct: Weight
    indirect: Weight
    indirect_source: Literal["entered_value"] = "entered_value"

    @model_validator(mode="after")
    def sums_to_one(self) -> "Final":
        if self.direct + self.indirect != 1:
            raise PydanticCustomError(
                "weights",
                "final weights must sum to 1 (got {total})",
                {"total": str(self.direct + self.indirect)},
            )
        return self


class Course(_Strict):
    aggregate: Literal["mean_ignore_blank"] = "mean_ignore_blank"
    target_compare: Literal[">="] = ">="


class MethodConfig(_Strict):
    schema_version: Literal["attainment-method/1"] = Field(alias="schema")
    name: str
    levels: Levels
    missing_data: Literal["block", "renormalise", "zero"] = "block"
    attempts: Literal["regular_only"] = "regular_only"
    precision: Precision = Precision()
    tools: dict[str, Tool] = Field(min_length=1)
    merge: dict[str, Merge] = {}
    direct: dict[str, Weight] = Field(min_length=1)
    final: Final
    course: Course = Course()

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @field_validator("merge")
    @classmethod
    def merge_sources_exist(cls, merge: dict[str, Merge], info: object) -> dict[str, Merge]:
        tools = getattr(info, "data", {}).get("tools", {})
        for name, rule in merge.items():
            if name in tools:
                raise PydanticCustomError("merge", "merge '{n}' reuses a tool name", {"n": name})
            for source in rule.sources:
                if source not in tools:
                    raise PydanticCustomError(
                        "merge",
                        "merge '{n}' refers to unknown tool '{s}'",
                        {"n": name, "s": source},
                    )
        return merge

    @field_validator("direct")
    @classmethod
    def direct_weights_are_valid(cls, direct: dict[str, Weight], info: object) -> dict[str, Weight]:
        data = getattr(info, "data", {})
        tools = data.get("tools", {})
        merge = data.get("merge", {})
        merged_away = {s for rule in merge.values() for s in rule.sources}
        for name in direct:
            if name not in tools and name not in merge:
                raise PydanticCustomError("direct", "unknown tool '{n}'", {"n": name})
            if name in merged_away:
                raise PydanticCustomError(
                    "direct", "tool '{n}' is merged and cannot also be weighted", {"n": name}
                )
        total = sum(direct.values(), Decimal(0))
        if total != 1:
            raise PydanticCustomError(
                "direct", "weights must sum to 1 (got {total})", {"total": str(total)}
            )
        return direct

    @model_validator(mode="after")
    def every_tool_is_used(self) -> "MethodConfig":
        merged_away = {s for rule in self.merge.values() for s in rule.sources}
        for name in self.tools:
            if name not in self.direct and name not in merged_away:
                raise PydanticCustomError(
                    "tools", "tool '{n}' is defined but has no weight", {"n": name}
                )
        return self


def load_method(text: str) -> MethodConfig:
    """Parse and validate a method. Numbers are read as Decimal, never float."""
    try:
        raw = json.loads(text, parse_float=Decimal)
        return MethodConfig.model_validate(raw)
    except json.JSONDecodeError as error:
        raise MethodConfigError(f"method is not valid JSON: {error}") from error
    except ValidationError as error:
        lines = []
        for item in error.errors():
            where = ".".join(str(part) for part in item["loc"]) or "method"
            lines.append(f"{where}: {item['msg']}")
        raise MethodConfigError("; ".join(lines)) from error
