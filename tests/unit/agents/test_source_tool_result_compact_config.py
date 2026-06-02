# -*- coding: utf-8 -*-
"""Source 工具结果压缩配置运行时接入的回归测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.agents.hooks import memory_compaction
from swe.agents.hooks.memory_compaction import MemoryCompactionHook
from swe.agents.tools.file_io import read_file
from swe.security import tenant_path_boundary
from swe.app.source_system_config.models import (
    EffectiveSourceSystemConfig,
    SourceSystemConfig,
)
from swe.app.source_system_config.runtime import (
    bind_source_system_config,
    resolve_tool_result_compact_config,
)
from swe.config.config import ToolResultCompactConfig
from swe.config.context import (
    set_current_file_read_max_bytes,
    reset_current_tenant_id,
    reset_current_workspace_dir,
    set_current_recent_max_bytes,
    set_current_tenant_id,
    set_current_workspace_dir,
)


def _build_effective_source_config(
    raw_config: dict,
) -> EffectiveSourceSystemConfig:
    """构造携带 raw_config 的请求级 source 配置。"""
    source_config = SourceSystemConfig.model_validate(raw_config)
    return EffectiveSourceSystemConfig(
        source_id="portal",
        config=source_config.merged_with_defaults(),
        raw_config=source_config,
        version=1,
    )


@pytest.mark.asyncio
async def test_memory_compaction_hook_uses_tenant_scoped_agent_config(
    tmp_path,
    monkeypatch,
):
    """Hook compaction should use tenant agent.json instead of global defaults."""
    from swe.config.config import (
        Config,
        AgentsConfig,
        AgentProfileConfig,
        AgentProfileRef,
        AgentsRunningConfig,
        save_agent_config,
    )
    from swe.config.utils import save_config
    import swe.config.utils as config_utils
    import swe.config.config as config_module

    monkeypatch.setattr(config_utils, "WORKING_DIR", tmp_path)
    monkeypatch.setattr(config_module, "WORKING_DIR", tmp_path)

    global_workspace = tmp_path / "workspaces" / "default"
    tenant_workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    global_workspace.mkdir(parents=True)
    tenant_workspace.mkdir(parents=True)

    save_config(
        Config(
            agents=AgentsConfig(
                active_agent="default",
                profiles={
                    "default": AgentProfileRef(
                        id="default",
                        workspace_dir=str(global_workspace),
                    ),
                },
            ),
        ),
        tmp_path / "config.json",
    )
    save_config(
        Config(
            agents=AgentsConfig(
                active_agent="default",
                profiles={
                    "default": AgentProfileRef(
                        id="default",
                        workspace_dir=str(tenant_workspace),
                    ),
                },
            ),
        ),
        tmp_path / "tenant-a" / "config.json",
    )

    save_agent_config(
        "default",
        AgentProfileConfig(
            id="default",
            name="Global",
            workspace_dir=str(global_workspace),
            running=AgentsRunningConfig(
                tool_result_compact={
                    "enabled": True,
                    "recent_n": 2,
                    "old_max_bytes": 3000,
                    "recent_max_bytes": 50000,
                    "retention_days": 5,
                },
                memory_summary={"memory_summary_enabled": False},
            ),
        ),
        config_path=tmp_path / "config.json",
    )
    save_agent_config(
        "default",
        AgentProfileConfig(
            id="default",
            name="Tenant",
            workspace_dir=str(tenant_workspace),
            running=AgentsRunningConfig(
                tool_result_compact={
                    "enabled": True,
                    "recent_n": 10,
                    "old_max_bytes": 50000,
                    "recent_max_bytes": 50000,
                    "retention_days": 5,
                },
                memory_summary={"memory_summary_enabled": False},
            ),
        ),
        config_path=tmp_path / "tenant-a" / "config.json",
    )

    token_counter = SimpleNamespace(count=AsyncMock(return_value=0))
    memory_manager = SimpleNamespace(
        agent_id="default",
        tenant_id="tenant-a",
        compact_tool_result=AsyncMock(),
        check_context=AsyncMock(return_value=([], [], True)),
    )
    agent = SimpleNamespace(
        name="agent",
        sys_prompt="",
        memory=SimpleNamespace(
            get_compressed_summary=lambda: "",
            get_memory=AsyncMock(return_value=["dummy"]),
        ),
        print=AsyncMock(),
    )
    monkeypatch.setattr(
        memory_compaction,
        "get_swe_token_counter",
        lambda _config: token_counter,
    )

    await MemoryCompactionHook(memory_manager)(agent, {})

    assert (
        memory_manager.compact_tool_result.await_args.kwargs["old_max_bytes"]
        == 50000
    )
    assert (
        memory_manager.compact_tool_result.await_args.kwargs["recent_n"] == 10
    )


@pytest.mark.asyncio
async def test_source_recent_max_bytes_affects_read_file_context(
    tmp_path,
    monkeypatch,
):
    """source 覆盖的近期阈值应影响 read_file 返回给模型的内容长度。"""
    tenant_root = tmp_path / "tenant-a"
    workspace = tenant_root / "workspace"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(tenant_path_boundary, "WORKING_DIR", tmp_path)
    file_path = workspace / "large.txt"
    file_path.write_text("\n".join(["x" * 20] * 200), encoding="utf-8")
    base_config = ToolResultCompactConfig(
        old_max_bytes=500,
        recent_max_bytes=2000,
    )
    effective = _build_effective_source_config(
        {
            "tool_result_compact": {
                "recent_max_bytes": 1000,
            },
        },
    )

    with bind_source_system_config(effective):
        resolved = resolve_tool_result_compact_config(base_config)
        tenant_token = set_current_tenant_id("tenant-a")
        workspace_token = set_current_workspace_dir(workspace)
        try:
            set_current_recent_max_bytes(resolved.recent_max_bytes)
            result = await read_file("large.txt")
        finally:
            set_current_recent_max_bytes(None)
            reset_current_workspace_dir(workspace_token)
            reset_current_tenant_id(tenant_token)

    text = result.content[0]["text"]
    assert "covers the next 1000 bytes" in text


@pytest.mark.asyncio
async def test_explicit_file_read_disable_skips_recent_threshold_fallback(
    tmp_path,
    monkeypatch,
):
    """显式关闭文件读取截断后，不应再回退到 recent_max_bytes 截断。"""
    tenant_root = tmp_path / "tenant-a"
    workspace = tenant_root / "workspace"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(tenant_path_boundary, "WORKING_DIR", tmp_path)
    file_path = workspace / "large.txt"
    file_path.write_text("\n".join(["x" * 20] * 200), encoding="utf-8")

    tenant_token = set_current_tenant_id("tenant-a")
    workspace_token = set_current_workspace_dir(workspace)
    try:
        set_current_recent_max_bytes(1000)
        set_current_file_read_max_bytes(0)
        result = await read_file("large.txt")
    finally:
        set_current_recent_max_bytes(None)
        set_current_file_read_max_bytes(None)
        reset_current_workspace_dir(workspace_token)
        reset_current_tenant_id(tenant_token)

    text = result.content[0]["text"]
    assert "covers the next 1000 bytes" not in text
    assert len(text.encode("utf-8")) > 1000


@pytest.mark.asyncio
async def test_source_disabled_config_skips_memory_tool_result_compaction(
    monkeypatch,
):
    """source 显式关闭工具结果压缩时，hook 不应调用 compact_tool_result。"""
    base_config = ToolResultCompactConfig(
        enabled=True,
        recent_n=2,
        old_max_bytes=3000,
        recent_max_bytes=50000,
        retention_days=5,
    )
    running_config = SimpleNamespace(
        tool_result_compact=base_config,
        memory_compact_threshold=10000,
        memory_compact_reserve=1000,
        memory_summary=SimpleNamespace(memory_summary_enabled=False),
        context_compact=SimpleNamespace(context_compact_enabled=False),
    )
    agent_config = SimpleNamespace(running=running_config)
    token_counter = SimpleNamespace(count=AsyncMock(return_value=0))
    memory = SimpleNamespace(
        get_compressed_summary=lambda: "",
        get_memory=AsyncMock(return_value=[]),
    )
    agent = SimpleNamespace(
        name="agent",
        sys_prompt="",
        memory=memory,
        print=AsyncMock(),
    )
    load_agent_config_calls: list[tuple[str, str | None]] = []

    def fake_load_agent_config(
        agent_id: str,
        config_path=None,
        *,
        tenant_id: str | None = None,
    ):
        load_agent_config_calls.append((agent_id, tenant_id))
        return agent_config

    memory_manager = SimpleNamespace(
        agent_id="default",
        tenant_id="tenant-a",
        compact_tool_result=AsyncMock(),
        check_context=AsyncMock(return_value=([], [], True)),
    )
    effective = _build_effective_source_config(
        {
            "tool_result_compact": {
                "enabled": False,
            },
        },
    )
    monkeypatch.setattr(
        memory_compaction,
        "load_agent_config",
        fake_load_agent_config,
    )
    monkeypatch.setattr(
        memory_compaction,
        "get_swe_token_counter",
        lambda config: token_counter,
    )

    with bind_source_system_config(effective):
        await MemoryCompactionHook(memory_manager)(agent, {})

    memory_manager.compact_tool_result.assert_not_awaited()
    memory_manager.check_context.assert_awaited_once()
    assert load_agent_config_calls == [("default", "tenant-a")]
