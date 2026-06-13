# -*- coding: utf-8 -*-
"""MCP progress token scope namespace regression tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from swe.app import mcp as app_mcp
from swe.config.context import tenant_context


@pytest.mark.asyncio
async def test_patched_mcp_call_namespaces_progress_tokens_by_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """相同 runtime 对象在不同 scope 下也必须生成不同 progress namespace。"""
    captured_tokens: list[str] = []

    async def _fake_call_with_progress(
        _session,
        *,
        meta,
        **_kwargs,
    ):
        captured_tokens.append(meta["progressToken"])
        yield SimpleNamespace(content="done", metadata=meta, is_last=True)

    token_values = iter(["uuid-a", "uuid-b"])
    fake_tool = SimpleNamespace(
        name="demo-tool",
        timeout=5.0,
        wrap_tool_result=False,
        client_gen=None,
        session=SimpleNamespace(_progress_callbacks={}),
    )

    monkeypatch.setattr(
        app_mcp,
        "_call_with_progress",
        _fake_call_with_progress,
    )
    monkeypatch.setattr(
        app_mcp.uuid,
        "uuid4",
        lambda: next(token_values),
    )

    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        async for _chunk in app_mcp._patched_mcp_call(fake_tool, value=1):
            pass

    with tenant_context(tenant_id="tenant-a", source_id="source-b"):
        async for _chunk in app_mcp._patched_mcp_call(fake_tool, value=1):
            pass

    assert captured_tokens == [
        "dGVuYW50LWE.c291cmNlLWE@uuid-a",
        "dGVuYW50LWE.c291cmNlLWI@uuid-b",
    ]


@pytest.mark.asyncio
async def test_call_with_progress_wraps_mcp_error_as_structured_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcp.types import TextContent

    async def _fake_drain_progress(_queue, _tool_name, result_box):
        result_box.append(
            SimpleNamespace(
                content=[
                    TextContent(type="text", text="permission denied"),
                ],
                meta={"source": "test"},
                isError=True,
            ),
        )
        if _queue is None:
            yield None

    monkeypatch.setattr(app_mcp, "_drain_progress", _fake_drain_progress)
    monkeypatch.setattr(
        app_mcp,
        "_launch_call_tool",
        lambda *_args, **_kwargs: asyncio.create_task(asyncio.sleep(0)),
    )

    chunks = []
    async for chunk in app_mcp._call_with_progress(
        session=SimpleNamespace(),
        tool_name="demo-tool",
        kwargs={},
        timeout=5.0,
        meta={},
        per_timeout=1.0,
        max_total=None,
        progress_event=asyncio.Event(),
        watchdog_cb=None,
        progress_queue=asyncio.Queue(),
        wrap_tool_result=True,
    ):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0].content["isError"] is True
    assert chunks[0].content["error_type"] == "mcp_tool_error"
    assert chunks[0].content["content"][0]["text"] == "permission denied"
