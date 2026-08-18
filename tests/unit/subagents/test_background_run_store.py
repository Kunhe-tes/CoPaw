# -*- coding: utf-8 -*-
"""Background SubAgent per-run store tests."""

from __future__ import annotations

import pytest

from swe.app.subagents import (
    AgentRegistry,
    AgentResult,
    DefinitionMatchMetadata,
    DelegationSpec,
    PerRunSubAgentRunStore,
    PermissionPolicy,
    SubAgentStartRequest,
    builtin_definition_provider,
)


def _definition():
    registry = AgentRegistry([builtin_definition_provider()])
    return registry.resolve("plan-researcher")


def _spec() -> DelegationSpec:
    return DelegationSpec(
        task_id="task-1",
        parent_thread_id="session-1",
        name="plan-researcher",
        objective="Inspect background run persistence",
        background="User asked for background SubAgent support",
    )


def _result(status: str = "completed") -> AgentResult:
    return AgentResult(
        task_id="task-1",
        agent_run_id="subagent-test",
        agent_name="plan-researcher",
        status=status,
        summary=f"{status} summary",
    )


@pytest.mark.asyncio
async def test_per_run_store_writes_one_file_per_run(tmp_path):
    store = PerRunSubAgentRunStore(tmp_path)

    record = await store.create(
        _spec(),
        _definition(),
        PermissionPolicy.readonly(),
    )

    assert record.status == "pending"
    assert (tmp_path / f"{record.run_id}.json").exists()
    assert not (tmp_path / "subagent_runs.json").exists()


@pytest.mark.asyncio
async def test_per_run_store_terminal_state_is_first_writer_wins(tmp_path):
    store = PerRunSubAgentRunStore(tmp_path)
    record = await store.create(
        _spec(),
        _definition(),
        PermissionPolicy.readonly(),
    )
    completed_result = _result()

    completed = await store.finish(record.run_id, completed_result)
    cancelled = await store.cancel(record.run_id)

    assert completed.status == "completed"
    assert cancelled.status == "completed"
    assert cancelled.result == completed_result


@pytest.mark.asyncio
async def test_per_run_store_marks_running_with_worker_metadata(tmp_path):
    store = PerRunSubAgentRunStore(tmp_path)
    record = await store.create(
        _spec(),
        _definition(),
        PermissionPolicy.readonly(),
    )

    running = await store.mark_running(record.run_id, worker_pid=123)

    assert running.status == "running"
    assert running.worker is not None
    assert running.worker.pid == 123


@pytest.mark.asyncio
async def test_per_run_store_persists_observed_turn_progress(tmp_path):
    store = PerRunSubAgentRunStore(tmp_path)
    record = await store.create(
        _spec(),
        _definition(),
        PermissionPolicy.readonly(),
    )
    await store.mark_running(record.run_id, worker_pid=123)

    updated = await store.record_turns(record.run_id, turns_used=2)
    reloaded = await PerRunSubAgentRunStore(tmp_path).get(record.run_id)

    assert updated.turns_used == 2
    assert reloaded is not None
    assert reloaded.turns_used == 2


@pytest.mark.asyncio
async def test_per_run_store_loads_record_from_individual_file(tmp_path):
    store = PerRunSubAgentRunStore(tmp_path)
    record = await store.create(
        _spec(),
        _definition(),
        PermissionPolicy.readonly(),
    )
    await store.finish(record.run_id, _result(status="partial"))

    reloaded = await PerRunSubAgentRunStore(tmp_path).get(record.run_id)

    assert reloaded is not None
    assert reloaded.status == "partial"
    assert reloaded.result is not None
    assert reloaded.result.status == "partial"


@pytest.mark.asyncio
async def test_background_run_record_persists_start_request_match_and_nickname(
    tmp_path,
):
    store = PerRunSubAgentRunStore(tmp_path)
    start_request = SubAgentStartRequest.model_validate(
        {
            "name": "aum-customer-analyst",
            "instruction": "Analyze AUM customer maintenance.",
            "objective": "Summarize customer maintenance strategy.",
        },
    )
    definition_match = DefinitionMatchMetadata(matched=False)

    record = await store.create(
        _spec(),
        _definition(),
        PermissionPolicy.readonly(),
        start_request=start_request,
        definition_match=definition_match,
        nickname="研究员",
    )

    reloaded = await PerRunSubAgentRunStore(tmp_path).get(record.run_id)

    assert reloaded is not None
    assert reloaded.nickname == "研究员"
    assert reloaded.start_request is not None
    assert reloaded.start_request.name == "aum-customer-analyst"
    assert reloaded.definition_match.matched is False


@pytest.mark.asyncio
async def test_background_run_record_persists_safe_launch_diagnostics(
    tmp_path,
):
    store = PerRunSubAgentRunStore(tmp_path)

    record = await store.create(
        _spec(),
        _definition(),
        PermissionPolicy.readonly(),
        launch_diagnostics={
            "loaded_skills": ["quality"],
            "skipped_skills": ["disabled"],
            "snapshotted_mcps": ["github"],
            "connected_mcps": ["github"],
            "skipped_mcps": ["offline"],
            "resolved_model": {
                "provider_id": "openai",
                "model": "gpt-5-mini",
            },
        },
    )

    reloaded = await PerRunSubAgentRunStore(tmp_path).get(record.run_id)

    assert reloaded is not None
    assert reloaded.launch_diagnostics.loaded_skills == ["quality"]


def test_launch_diagnostics_rejects_provider_secrets_in_resolved_model():
    from swe.app.subagents.models import SubAgentLaunchDiagnostics

    with pytest.raises(ValueError, match="provider_id"):
        SubAgentLaunchDiagnostics.model_validate(
            {
                "resolved_model": {
                    "provider_id": "openai",
                    "model": "gpt-5-mini",
                    "api_key": "secret",
                },
            },
        )
