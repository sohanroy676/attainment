"""The approval state machine as data (design 8.7). One table drives the services and the tests.

A move is (current state, action) -> (next state, permission needed, reason required). Anything
not in the table is illegal. `None` means "no state yet" (a section starts as draft; a result has
no stage until it is reviewed).
"""

from dataclasses import dataclass

from .models import ResultStage, SectionState

S = SectionState.Status
R = ResultStage.Status


@dataclass(frozen=True)
class Move:
    to: str
    permission: str
    reason_required: bool = False


SECTION_MOVES: dict[tuple[str, str], Move] = {
    (S.DRAFT, "submit"): Move(S.SUBMITTED, "workflow.submit"),
    (S.RETURNED, "submit"): Move(S.SUBMITTED, "workflow.submit"),
    (S.SUBMITTED, "accept"): Move(S.ACCEPTED, "workflow.accept"),
    (S.SUBMITTED, "return"): Move(S.RETURNED, "workflow.accept", reason_required=True),
}

STAGE_MOVES: dict[tuple[str | None, str], Move] = {
    (None, "review"): Move(R.REVIEWED, "workflow.accept"),
    (R.REOPENED, "review"): Move(R.REVIEWED, "workflow.accept"),
    (R.REVIEWED, "approve"): Move(R.APPROVED, "workflow.approve"),
    (R.APPROVED, "sign"): Move(R.SIGNED, "workflow.sign"),
    (R.APPROVED, "reopen"): Move(R.REOPENED, "data.reopen", reason_required=True),
    (R.SIGNED, "reopen"): Move(R.REOPENED, "data.reopen", reason_required=True),
}

# The exam branch submits the SEE; everyone else submits through the lecturer's right.
SEE_SUBMIT_PERMISSION = "marks.enter_see"

LOCKED_STAGES = (R.APPROVED, R.SIGNED)
