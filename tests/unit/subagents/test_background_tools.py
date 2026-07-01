# -*- coding: utf-8 -*-
"""Background SubAgent tool factory tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from swe.agents.tools.subagent_background import (
    create_background_subagent_tools,
)
from swe.app.subagents import BackgroundSubAgentStartBlocked
from swe.app.subagents import (
    AgentRegistry,
    DelegationSpec,
    PerRunSubAgentRunStore,
    PermissionPolicy,
    builtin_definition_provider,
)
from swe.config.config import AgentProfileConfig


def _agent_config(tmp_path: Path) -> AgentProfileConfig:
    return AgentProfileConfig(
        id="agent-1",
        name="Agent",
        workspace_dir=str(tmp_path),
    )


@pytest.mark.asyncio
async def test_start_subagent_returns_blocked_without_run_file(tmp_path):
    supervisor = SimpleNamespace()
    supervisor.start = _AsyncReturn(
        BackgroundSubAgentStartBlocked(
            limit=1,
            active_run_ids=["subagent-running"],
        ),
    )
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "session_id": "session-1",
        },
    )

    response = await tools["start_subagent"]("plan-researcher", "Inspect")
    payload = json.loads(response.content[0]["text"])

    assert payload["status"] == "blocked"
    assert payload["reason"] == "background_subagent_concurrency_limit"
    assert not (tmp_path / "subagent_runs").exists()


@pytest.mark.asyncio
async def test_wait_subagent_returns_compact_snapshot(tmp_path):
    supervisor = SimpleNamespace()
    supervisor.wait = _AsyncReturn(
        SimpleNamespace(
            active_runs=[
                SimpleNamespace(
                    run_id="subagent-active",
                    status="running",
                    spec=SimpleNamespace(
                        agent_name="plan-researcher",
                        objective="Inspect",
                    ),
                    result=None,
                    errors=[],
                    model_dump=lambda mode="json": {},
                ),
            ],
            terminal_runs=[],
            timed_out=True,
        ),
    )
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={"tenant_id": "tenant-1", "agent_id": "agent-1"},
    )

    response = await tools["wait_subagent"](timeout_ms=1)
    payload = json.loads(response.content[0]["text"])

    assert payload["timed_out"] is True
    assert payload["active_runs"][0]["run_id"] == "subagent-active"


@pytest.mark.asyncio
async def test_start_subagent_serializes_real_run_record(tmp_path):
    definition = AgentRegistry([builtin_definition_provider()]).resolve(
        "plan-researcher",
    )
    record = await PerRunSubAgentRunStore(tmp_path / "runs").create(
        DelegationSpec(
            agent_name="plan-researcher",
            objective="Inspect",
        ),
        definition,
        PermissionPolicy.readonly(),
    )
    supervisor = SimpleNamespace()
    supervisor.start = _AsyncReturn(record)
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={"tenant_id": "tenant-1", "agent_id": "agent-1"},
    )

    response = await tools["start_subagent"]("plan-researcher", "Inspect")
    payload = json.loads(response.content[0]["text"])

    assert payload["run_id"] == record.run_id
    assert payload["created_at"]


class _AsyncReturn:
    def __init__(self, value):
        self.value = value

    async def __call__(self, *args, **kwargs):
        return self.value
