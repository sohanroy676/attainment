"""Denominator: how many students a question's pass count is divided by (design 6.3).

`by_choice` (the default): a choice question counts only students who attempted it; a
compulsory question counts everyone who sat the assessment.
"""

from ..errors import EngineError
from ..model import Part


def denominator_for(
    part: Part,
    mode: str,
    attempted: int,
    sat: int,
    enrolled: int,
    fixed_n: int | None,
) -> int:
    if mode == "by_choice":
        return attempted if part.choice_group is not None else sat
    if mode == "attempted":
        return attempted
    if mode == "sat":
        return sat
    if mode == "enrolled":
        return enrolled
    if mode == "fixed":
        if fixed_n is None:
            raise EngineError("denominator 'fixed' needs fixed_n")
        return fixed_n
    raise EngineError(f"unknown denominator mode '{mode}'")
