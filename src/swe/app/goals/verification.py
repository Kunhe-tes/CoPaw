"""Contract-bound, read-only verification for Goal completion criteria.

The first phase deliberately supports an executable subset of the free-text
``verification_method`` field.  A Contract remains readable/editable prose,
but a method must opt into ``command:`` for the host to make a deterministic
completion decision.  It prevents a model assertion from becoming acceptance.
"""

from __future__ import annotations

from pathlib import Path

from ...agents.tools.shell import execute_shell_command
from ...security.tool_guard.engine import get_guard_engine
from .models import GoalSnapshot
from .runtime import VerificationResult

_COMMAND_PREFIX = "command:"
_MUTATING_SHELL_TOKENS = frozenset(
    {
        "rm ", "mv ", "cp ", "mkdir", "touch", "tee ", ">", ">>",
        "sed -i", "git commit", "git reset", "git checkout", "git clean",
        "pip install", "npm install", "pnpm install",
    },
)


class ContractVerificationAdapter:
    """Run explicitly declared, guard-checked read-only shell verification."""

    def __init__(self, workspace_dir: Path | str | None) -> None:
        self._workspace_dir = Path(workspace_dir) if workspace_dir else None

    async def __call__(self, goal: GoalSnapshot) -> dict[str, VerificationResult]:
        results: dict[str, VerificationResult] = {}
        for status in goal.criteria:
            results[status.criterion_id] = await self._verify(status.criterion)
        return results

    async def _verify(self, criterion) -> VerificationResult:
        method = criterion.verification_method.strip()
        if not method.lower().startswith(_COMMAND_PREFIX):
            return False, "verification method must begin with 'command:'"
        command = method[len(_COMMAND_PREFIX):].strip()
        if not command:
            return False, "verification command is blank"
        if _is_mutating_command(command):
            return False, "verification command is not read-only"

        guard = get_guard_engine().guard(
            "execute_shell_command",
            {"command": command, "cwd": str(self._workspace_dir or "")},
        )
        if guard is not None and not guard.is_safe:
            return False, "verification command requires tool approval"
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
        return False, (
            "expected_outcome must be 'exit 0' or 'output contains: <text>'"
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
