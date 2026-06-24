# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

import pytest
from agentscope.tool import ToolResponse

from swe.agents.react_agent import SWEAgent
from swe.agents.tool_failure import (
    ToolExecutionError,
    build_structured_failure_output,
    normalize_tool_function_errors,
)
from swe.agents.tools.copy_file_to_static import copy_file_to_static
from swe.config.context import tenant_context


def test_build_structured_failure_output_uses_canonical_shape() -> None:
    output = build_structured_failure_output(
        error_type="permission_denied",
        detail="permission denied",
    )

    assert output == {
        "isError": True,
        "error_type": "permission_denied",
        "content": [{"type": "text", "text": "permission denied"}],
    }


@pytest.mark.asyncio
async def test_normalize_tool_function_errors_converts_tool_execution_error():
    async def failing_tool() -> ToolResponse:
        raise ToolExecutionError(
            error_type="permission_denied",
            detail="permission denied",
        )

    wrapped = normalize_tool_function_errors(failing_tool)

    result = await wrapped()

    assert isinstance(result, ToolResponse)
    assert result.content["isError"] is True
    assert result.content["error_type"] == "permission_denied"
    assert result.content["content"][0]["text"] == "permission denied"


@pytest.mark.asyncio
async def test_normalize_tool_function_errors_maps_generic_exceptions():
    async def failing_tool() -> ToolResponse:
        raise RuntimeError("boom")

    wrapped = normalize_tool_function_errors(failing_tool)

    result = await wrapped()

    assert isinstance(result, ToolResponse)
    assert result.content["isError"] is True
    assert result.content["error_type"] == "unexpected_tool_error"
    assert result.content["content"][0]["text"] == "boom"


@pytest.mark.asyncio
async def test_react_toolkit_normalizes_builtin_tool_execution_errors(
    tmp_path,
    monkeypatch,
) -> None:
    workspace_dir = tmp_path / "tenant_a" / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)

    agent = object.__new__(SWEAgent)
    agent._agent_config = SimpleNamespace()

    toolkit = agent._create_toolkit()

    monkeypatch.setattr(
        "swe.security.tenant_path_boundary.WORKING_DIR",
        tmp_path,
    )
    with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
        tool_res = await toolkit.call_tool_function(
            {
                "type": "tool_use",
                "id": "tool-1",
                "name": "read_file",
                "input": {"file_path": "missing.txt"},
            },
        )
        chunks = [chunk async for chunk in tool_res]

    assert len(chunks) == 1
    assert chunks[0].content["isError"] is True
    assert chunks[0].content["error_type"] == "not_found"
    assert "does not exist" in chunks[0].content["content"][0]["text"]


@pytest.mark.asyncio
async def test_copy_file_to_static_raises_tool_execution_error_for_missing_file():
    with pytest.raises(ToolExecutionError) as exc_info:
        await copy_file_to_static("missing-file.txt")

    assert exc_info.value.error_type == "not_found"
    assert "File not found" in exc_info.value.detail
