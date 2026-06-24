# -*- coding: utf-8 -*-
from __future__ import annotations

from importlib import import_module

import pytest
from agentscope.message import Msg

from swe.app.runner.utils import agentscope_msg_to_message


def _tool_status_module():
    try:
        return import_module("swe.app.runner.tool_status")
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing tool status module: {exc}")
        raise AssertionError("unreachable")


def test_apply_running_tool_status_marks_call_without_error() -> None:
    module = _tool_status_module()
    data = {"name": "grep_search", "arguments": '{"pattern":"tenant"}'}

    result = module.apply_running_tool_status(data)

    assert result is data
    assert result["tool_status"] == module.TOOL_STATUS_RUNNING
    assert module.TOOL_ERROR_FIELD not in result


def test_apply_terminal_tool_status_marks_success_with_null_error() -> None:
    module = _tool_status_module()
    data = {"name": "grep_search", "output": ["a.py:1"]}

    result = module.apply_terminal_tool_status(data)

    assert result["tool_status"] == module.TOOL_STATUS_SUCCESS
    assert result["tool_error"] is None


def test_apply_terminal_tool_status_marks_failed_error_output() -> None:
    module = _tool_status_module()
    data = {"name": "grep_search", "output": {"error": "permission denied"}}

    result = module.apply_terminal_tool_status(data)

    assert result["tool_status"] == module.TOOL_STATUS_FAILED
    assert result["tool_error"] == "permission denied"


def test_apply_terminal_tool_status_uses_default_failed_error_text() -> None:
    module = _tool_status_module()
    data = {"name": "grep_search", "output": {"isError": True}}

    result = module.apply_terminal_tool_status(data)

    assert result["tool_status"] == module.TOOL_STATUS_FAILED
    assert result["tool_error"]


def test_apply_terminal_tool_status_preserves_preexisting_failed_status() -> (
    None
):
    module = _tool_status_module()
    data = {
        "name": "grep_search",
        "output": "tool output was rewritten downstream",
        "tool_status": module.TOOL_STATUS_FAILED,
        "tool_error": "permission denied",
    }

    result = module.apply_terminal_tool_status(data)

    assert result["tool_status"] == module.TOOL_STATUS_FAILED
    assert result["tool_error"] == "permission denied"


def test_apply_terminal_tool_status_truncates_long_error_text() -> None:
    module = _tool_status_module()
    long_error = "x" * (module.TOOL_ERROR_SUMMARY_LIMIT + 20)
    data = {"name": "grep_search", "output": {"error": long_error}}

    result = module.apply_terminal_tool_status(data)

    assert len(result["tool_error"]) == module.TOOL_ERROR_SUMMARY_LIMIT
    assert (
        result["tool_error"] == long_error[: module.TOOL_ERROR_SUMMARY_LIMIT]
    )


def test_history_tool_use_rebuilds_running_status() -> None:
    messages = agentscope_msg_to_message(
        Msg(
            name="Friday",
            role="assistant",
            content=[
                {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "grep_search",
                    "input": {"pattern": "tenant"},
                },
            ],
            timestamp="2026-06-01T08:00:00Z",
        ),
    )

    data = messages[0].content[0].data
    assert data["tool_status"] == "running"
    assert "tool_error" not in data


def test_history_tool_result_rebuilds_success_status() -> None:
    messages = agentscope_msg_to_message(
        Msg(
            name="Friday",
            role="assistant",
            content=[
                {
                    "type": "tool_result",
                    "id": "tool-1",
                    "name": "grep_search",
                    "output": ["a.py:1", "b.py:2"],
                },
            ],
            timestamp="2026-06-01T08:00:00Z",
        ),
    )

    data = messages[0].content[0].data
    assert data["tool_status"] == "success"
    assert data["tool_error"] is None


def test_history_tool_result_rebuilds_failed_status() -> None:
    messages = agentscope_msg_to_message(
        Msg(
            name="Friday",
            role="assistant",
            content=[
                {
                    "type": "tool_result",
                    "id": "tool-1",
                    "name": "grep_search",
                    "output": {"error": "permission denied"},
                },
            ],
            timestamp="2026-06-01T08:00:00Z",
        ),
    )

    data = messages[0].content[0].data
    assert data["tool_status"] == "failed"
    assert data["tool_error"] == "permission denied"


def test_history_tool_result_rebuilds_structured_failed_status() -> None:
    messages = agentscope_msg_to_message(
        Msg(
            name="Friday",
            role="assistant",
            content=[
                {
                    "type": "tool_result",
                    "id": "tool-1",
                    "name": "grep_search",
                    "output": {
                        "isError": True,
                        "error_type": "permission_denied",
                        "content": [
                            {
                                "type": "text",
                                "text": "permission denied",
                            },
                        ],
                    },
                },
            ],
            timestamp="2026-06-01T08:00:00Z",
        ),
    )

    data = messages[0].content[0].data
    assert data["tool_status"] == "failed"
    assert data["tool_error"] == "permission denied"
