from __future__ import annotations

from types import SimpleNamespace

import pytest

from swe.app.goals.models import (
    CompletionCriterion,
    GoalContract,
    GoalCriterionStatus,
    GoalScope,
    GoalSnapshot,
)
from swe.app.goals.runtime import VerificationPending
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


@pytest.mark.asyncio
async def test_guarded_verification_creates_an_approval_and_returns_pending(
    monkeypatch,
) -> None:
    checked = criterion("command: pytest -q", "exit 0")
    snapshot = GoalSnapshot(
        goal_id="goal-1",
        scope=GoalScope(
            tenant_id="tenant",
            source_id="source",
            agent_profile_id="agent",
            chat_id="chat",
            effective_model="model",
        ),
        contract=GoalContract(
            objective="Verify the change",
            completion_criteria=[checked],
            constraints={"must_preserve": [], "must_not_do": []},
            autonomy_boundary="No deployment",
        ),
        criteria=[
            GoalCriterionStatus(criterion_id="criterion-1", criterion=checked),
        ],
        turn_budget=12,
    )
    monkeypatch.setattr(
        verification,
        "get_guard_engine",
        lambda: SimpleNamespace(
            guard=lambda *_args, **_kwargs: SimpleNamespace(is_safe=False),
        ),
    )
    created: list[dict] = []

    class _Approvals:
        async def create_pending(self, **kwargs):
            created.append(kwargs)
            return SimpleNamespace(request_id="approval-1")

        async def get_request_status(self, _request_id):
            return {"status": "pending"}

    monkeypatch.setattr(verification, "get_approval_service", lambda: _Approvals())
    results = await ContractVerificationAdapter(
        None,
        approval_context={
            "session_id": "session",
            "user_id": "user",
            "channel": "console",
        },
    )(snapshot)

    result = results["criterion-1"]
    assert isinstance(result, VerificationPending)
    assert result.request_id == "approval-1"
    assert created[0]["extra"]["goal_id"] == "goal-1"
