# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

import pytest

from swe.app.goals.router import CreateGoalRequest, EditGoalRequest, _scope


def _contract() -> dict:
    return {
        "objective": "Ship the Goal Runtime",
        "completion_criteria": [
            {
                "requirement": "Goal API exists",
                "observable_assertion": "route is registered",
                "verification_method": "inspect OpenAPI",
                "expected_outcome": "route is listed",
            },
        ],
        "constraints": {"must_preserve": [], "must_not_do": []},
        "autonomy_boundary": "No deployment",
    }


def test_create_and_edit_requests_require_a_complete_contract() -> None:
    created = CreateGoalRequest(chat_id="chat-1", contract=_contract())
    edited = EditGoalRequest(contract=_contract())

    assert created.contract.objective == "Ship the Goal Runtime"
    assert (
        edited.contract.completion_criteria[0].expected_outcome
        == "route is listed"
    )


def test_scope_captures_the_active_provider_and_model(
    monkeypatch,
) -> None:
    class FakeProviderManager:
        def get_active_model(self):
            return SimpleNamespace(provider_id="provider-1", model="model-1")

    monkeypatch.setattr(
        "swe.providers.provider_manager.ProviderManager.get_instance",
        lambda tenant_id: (
            FakeProviderManager() if tenant_id == "tenant-1" else None
        ),
    )
    scope = _scope(
        SimpleNamespace(
            tenant_id="tenant-1",
            agent_id="agent-1",
            config=SimpleNamespace(source_id="source-1"),
        ),
        SimpleNamespace(id="chat-1"),
    )

    assert scope.effective_model_provider_id == "provider-1"
    assert scope.effective_model == "model-1"


def test_scope_rejects_goal_creation_without_a_resolved_model(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "swe.providers.provider_manager.ProviderManager.get_instance",
        lambda _tenant_id: SimpleNamespace(get_active_model=lambda: None),
    )

    with pytest.raises(ValueError, match="active effective model"):
        _scope(
            SimpleNamespace(
                tenant_id="tenant-1",
                agent_id="agent-1",
                config=SimpleNamespace(source_id="source-1"),
            ),
            SimpleNamespace(id="chat-1"),
        )
