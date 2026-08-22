from __future__ import annotations

import pytest
from types import SimpleNamespace

from swe.app.goals.models import CompletionCriterion
from swe.app.goals import verification
from swe.app.goals.verification import ContractVerificationAdapter


def criterion(method: str, expected: str) -> CompletionCriterion:
    return CompletionCriterion(
        requirement="A check can run",
        observable_assertion="The check produces the expected state",
        verification_method=method,
        expected_outcome=expected,
    )


@pytest.mark.asyncio
async def test_command_verification_is_tool_recheckable(monkeypatch) -> None:
    async def execute(*_args, **_kwargs):
        return SimpleNamespace(content=[{"text": "goal-pass"}])

    monkeypatch.setattr(verification, "execute_shell_command", execute)
    passed, _ = await ContractVerificationAdapter(None)._verify(
        criterion("command: printf goal-pass", "output contains: goal-pass"),
    )

    assert passed


@pytest.mark.asyncio
async def test_verification_rejects_mutating_or_unexecutable_contract_method() -> None:
    adapter = ContractVerificationAdapter(None)
    blocked, reason = await adapter._verify(
        criterion("command: touch unwanted-file", "exit 0"),
    )
    prose, prose_reason = await adapter._verify(
        criterion("Inspect the release notes", "exit 0"),
    )

    assert not blocked
    assert "read-only" in (reason or "")
    assert not prose
    assert "must begin" in (prose_reason or "")
