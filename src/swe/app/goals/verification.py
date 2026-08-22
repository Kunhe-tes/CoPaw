"""Contract-bound, read-only verification for Goal completion criteria.

The first phase deliberately supports an executable subset of the free-text
``verification_method`` field.  A Contract remains readable/editable prose,
but a method must opt into ``command:`` for the host to make a deterministic
completion decision.  It prevents a model assertion from becoming acceptance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...agents.tools.shell import execute_shell_command
from ...app.approvals import get_approval_service
from ...security.tool_guard.engine import get_guard_engine
from .models import GoalSnapshot
from .runtime import VerificationPending, VerificationResult

_COMMAND_PREFIX = "command:"
_MUTATING_SHELL_TOKENS = frozenset(
    {
        "rm ",
        "mv ",
        "cp ",
        "mkdir",
        "touch",
        "tee ",
        ">",
        ">>",
        "sed -i",
        "git commit",
        "git reset",
        "git checkout",
        "git clean",
        "pip install",
        "npm install",
        "pnpm install",
    },
)


class ContractVerificationAdapter:
    """Run explicitly declared, guard-checked read-only shell verification."""

    def __init__(
        self,
        workspace_dir: Path | str | None,
        *,
        approval_context: dict[str, Any] | None = None,
    ) -> None:
        self._workspace_dir = Path(workspace_dir) if workspace_dir else None
        self._approval_context = dict(approval_context or {})

    async def __call__(self, goal: GoalSnapshot) -> dict[str, VerificationResult]:
        results: dict[str, VerificationResult] = {}
        for status in goal.criteria:
            results[status.criterion_id] = await self._verify(
                status.criterion,
                goal_id=goal.goal_id,
                criterion_id=status.criterion_id,
                pending_request_id=status.verification_request_id,
            )
        return results

    async def _verify(
        self,
        criterion,
        *,
        goal_id: str | None = None,
        criterion_id: str | None = None,
        pending_request_id: str | None = None,
    ) -> VerificationResult:
        method = criterion.verification_method.strip()
        if not method.lower().startswith(_COMMAND_PREFIX):
            return False, "verification method must begin with 'command:'"
        command = method[len(_COMMAND_PREFIX) :].strip()
        if not command:
            return False, "verification command is blank"
        if _is_mutating_command(command):
            return False, "verification command is not read-only"

        guard = get_guard_engine().guard(
            "execute_shell_command",
            {"command": command, "cwd": str(self._workspace_dir or "")},
        )
        if guard is not None and not guard.is_safe:
            pending = await self._verification_approval(
                guard=guard,
                command=command,
                goal_id=goal_id,
                criterion_id=criterion_id,
                pending_request_id=pending_request_id,
            )
            if isinstance(pending, VerificationPending):
                return pending
            if pending is not None:
                return False, pending
        try:
            response = await execute_shell_command(
                command=command,
                cwd=self._workspace_dir,
            )
        except Exception as exc:
            return False, f"verification command failed: {exc}"
        output = _response_text(response)
        expected = criterion.expected_outcome.strip()
        if expected.lower() == "exit 0":
            return True, output
        if expected.lower().startswith("output contains:"):
            needle = expected.split(":", 1)[1].strip()
            return needle in output, output
        return False, ("expected_outcome must be 'exit 0' or 'output contains: <text>'")

    async def _verification_approval(
        self,
        *,
        guard: object,
        command: str,
        goal_id: str | None,
        criterion_id: str | None,
        pending_request_id: str | None,
    ) -> VerificationPending | str | None:
        """Use the normal approval service before guarded verification runs."""
        if not goal_id or not criterion_id or not self._approval_context:
            return "verification command requires tool approval"
        approvals = get_approval_service()
        if pending_request_id:
            status = await approvals.get_request_status(pending_request_id)
            decision = str((status or {}).get("status") or "pending")
            if decision == "approved":
                return None
            if decision == "pending":
                return VerificationPending(
                    request_id=pending_request_id,
                    reason="verification command requires tool approval",
                )
            return f"verification approval {decision}"
        pending = await approvals.create_pending(
            session_id=str(self._approval_context.get("session_id") or ""),
            user_id=str(self._approval_context.get("user_id") or ""),
            channel=str(self._approval_context.get("channel") or "console"),
            tool_name="execute_shell_command",
            result=guard,
            extra={
                "goal_id": goal_id,
                "goal_verification": {
                    "criterion_id": criterion_id,
                    "command": command,
                },
            },
        )
        return VerificationPending(
            request_id=pending.request_id,
            reason="verification command requires tool approval",
        )


def _is_mutating_command(command: str) -> bool:
    normalized = f" {command.lower()} "
    return any(token in normalized for token in _MUTATING_SHELL_TOKENS)


def _response_text(response: object) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "\n".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)
