"""Which role may do what. The single table behind every permission check (design section 9).

Permissions are named `area.action`. A role grants the permission over its assigned scope.
"""

from .models import Role

PERMISSIONS: dict[str, frozenset[str]] = {
    Role.COLLEGE_ADMIN: frozenset(
        {"users.manage", "structure.manage", "roster.manage", "reports.view"}
    ),
    Role.IQAC: frozenset(
        {
            "method.edit",
            "method.activate",
            "outcomes.edit",
            "override.apply",
            "data.reopen",
            "batch.prepare",
            "indirect.enter",
            "reports.view",
            "audit.view",
        }
    ),
    Role.HOD: frozenset(
        {
            "outcomes.approve",
            "workflow.approve",
            "override.apply",
            "data.reopen",
            "observations.edit",
            "reports.view",
            "audit.view",
        }
    ),
    Role.COORDINATOR: frozenset(
        {
            "outcomes.edit",
            "paper.edit",
            "marks.enter_internal",
            "workflow.accept",
            "observations.edit",
            "reports.view",
        }
    ),
    Role.LECTURER: frozenset(
        {"marks.enter_internal", "workflow.submit", "observations.edit", "reports.view"}
    ),
    Role.EXAM_BRANCH: frozenset({"marks.enter_see"}),
    Role.PRINCIPAL: frozenset({"workflow.sign", "reports.view", "audit.view"}),
    Role.AUDITOR: frozenset({"reports.view", "audit.view"}),
}
