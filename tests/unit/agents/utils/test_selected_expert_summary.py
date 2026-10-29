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
from swe.agents.utils.swe_token_counter import get_swe_token_counter


def _agent(model, limit=8000, divisor=4):
    async def format_messages(messages):
        return [message.to_dict() for message in messages]

    return SimpleNamespace(
        sys_prompt="Summarize findings",
        memory=InMemoryMemory(),
        compression_config=None,
        formatter=SimpleNamespace(format=format_messages),
        model=model,
        _agent_config=SimpleNamespace(
            running=SimpleNamespace(
                max_input_length=limit,
                context_compact=SimpleNamespace(
                    token_count_estimate_divisor=divisor,
                ),
            ),
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("divisor", "finding"),
    [(2, "finding " * 1600), (4, "中文结论" * 1600), (5, "finding " * 4000)],
    ids=["divisor-2", "chinese-divisor-4", "divisor-5"],
)
async def test_evidence_fitting_main_agent_estimate_needs_no_reduction(
    divisor,
    finding,
):
    async def model(_prompt):
        raise AssertionError("Evidence fits the main agent token estimate")

    agent = _agent(model, divisor=divisor)
    await agent.memory.add(
        Msg("user", [{"type": "text", "text": "历史" * 50}], "user"),
    )
    evidence = {"status": "completed", "result": finding}
    counter = get_swe_token_counter(agent._agent_config)
    assert await counter.count(messages=[], text=finding) < 7200
    message = await prepare_selected_expert_summary(agent, evidence)
    assert json.dumps(evidence, ensure_ascii=False) in message.content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("divisor", "needs_reduction"),
    [(2, True), (5, False)],
)
async def test_configured_divisor_controls_reduction(
    divisor,
    needs_reduction,
):
    calls = []

    async def model(prompt):
        calls.append(prompt)
        return SimpleNamespace(content="Retained finding")

    agent = _agent(model, divisor=divisor)
    await prepare_selected_expert_summary(agent, {"result": "x" * 24000})
    assert bool(calls) is needs_reduction


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [True, False])
@pytest.mark.parametrize("divisor", [2, 4, 5])
async def test_reduction_reads_large_unicode_evidence_with_bounded_inputs(
    streaming,
    divisor,
):
    marker = "结论：必须修复凭据泄漏"
    evidence = {
        "status": "partial",
        "result": "资料" * 100000 + marker + "后文" * 100000,
    }
    calls = []

    async def model(prompt):
        counter = get_swe_token_counter(agent._agent_config)
        assert (
            await counter.count(
                messages=[msg for msg in prompt if msg["role"] != "system"],
            )
            + await counter.count(
                messages=[],
                text="".join(
                    msg["content"] for msg in prompt if msg["role"] == "system"
                ),
            )
            <= 65536 - 6553
        )
        serialized = json.dumps(prompt, ensure_ascii=False)
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

    agent = _agent(model, limit=65536, divisor=divisor)
    message = await prepare_selected_expert_summary(agent, evidence)
    assert len(calls) > 1
    assert marker in message.get_text_content()
    assert not await agent.memory.get_memory()
    counter = get_swe_token_counter(agent._agent_config)
    assert await counter.count(messages=[message.to_dict()]) < 65536


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
    await agent.memory.add(Msg("user", "history" * 6000, "user"))
    with pytest.raises(ExpertEvidenceBudgetError, match="No context budget"):
        await prepare_selected_expert_summary(agent, {"result": "finding"})


@pytest.mark.asyncio
async def test_oversized_digest_is_rejected_before_final_prompt():
    async def model(_prompt):
        return SimpleNamespace(content="unbounded digest" * 1000)

    agent = _agent(model)
    with pytest.raises(ExpertEvidenceBudgetError, match="digest exceeds"):
        await prepare_selected_expert_summary(agent, {"result": "x" * 80000})
