# -*- coding: utf-8 -*-
"""Bounded private evidence reduction before a tool-free final answer."""

import json
from types import SimpleNamespace

import pytest
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg

from swe.agents.utils.selected_expert_summary import (
    ExpertEvidenceBudgetError,
    prepare_selected_expert_summary,
)


def _agent(model, limit=8000):
    async def format_messages(messages):
        return [message.to_dict() for message in messages]

    return SimpleNamespace(
        sys_prompt="Summarize findings",
        memory=InMemoryMemory(),
        compression_config=None,
        formatter=SimpleNamespace(format=format_messages),
        model=model,
        _agent_config=SimpleNamespace(
            running=SimpleNamespace(max_input_length=limit),
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [True, False])
async def test_reduction_reads_large_unicode_evidence_with_bounded_inputs(
    streaming,
):
    marker = "结论：必须修复凭据泄漏"
    evidence = {
        "status": "partial",
        "result": "资料" * 100000 + marker + "后文" * 100000,
    }
    calls = []

    async def model(prompt):
        serialized = json.dumps(prompt)
        assert len(serialized.encode()) < 65536
        calls.append(serialized)
        content = "partial evidence; "
        contents = str([message["content"] for message in prompt])
        if marker in contents or json.dumps(marker)[1:-1] in " ".join(
            message["content"] for message in prompt
        ):
            content += marker
        response = SimpleNamespace(content=content)
        if not streaming:
            return response

        async def chunks():
            yield SimpleNamespace(content="partial evidence")
            yield response

        return chunks()

    agent = _agent(model, limit=65536)
    message = await prepare_selected_expert_summary(agent, evidence)
    assert len(calls) > 1
    assert marker in message.get_text_content()
    assert not await agent.memory.get_memory()
    assert len(json.dumps(message.to_dict()).encode()) < 65536


@pytest.mark.asyncio
async def test_small_evidence_uses_remaining_budget_without_reduction():
    async def model(_prompt):
        raise AssertionError("Small evidence must not need a model call")

    agent = _agent(model)
    await agent.memory.add(Msg("user", "history" * 500, "user"))
    evidence = {"status": "completed", "result": "finding"}
    message = await prepare_selected_expert_summary(agent, evidence)
    assert json.dumps(evidence) in message.content


@pytest.mark.asyncio
async def test_no_remaining_budget_does_not_call_model():
    async def model(_prompt):
        raise AssertionError("Do not send an oversized context")

    agent = _agent(model)
    await agent.memory.add(Msg("user", "history" * 1500, "user"))
    with pytest.raises(ExpertEvidenceBudgetError, match="No context budget"):
        await prepare_selected_expert_summary(agent, {"result": "finding"})


@pytest.mark.asyncio
async def test_oversized_digest_is_rejected_before_final_prompt():
    async def model(_prompt):
        return SimpleNamespace(content="unbounded digest" * 1000)

    agent = _agent(model)
    with pytest.raises(ExpertEvidenceBudgetError, match="digest exceeds"):
        await prepare_selected_expert_summary(agent, {"result": "x" * 20000})
