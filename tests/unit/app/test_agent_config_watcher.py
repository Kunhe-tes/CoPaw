# -*- coding: utf-8 -*-
"""Tests for tenant-aware AgentConfigWatcher config loading."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from swe.app.agent_config_watcher import AgentConfigWatcher
from swe.app.channels.console.channel import ConsoleChannel
from swe.config.config import ChannelConfig, ConsoleConfig
from swe.app.workspace.service_factories import create_agent_config_watcher


class TestAgentConfigWatcherTenantScope:
    """AgentConfigWatcher must load config from the owning tenant scope."""

    def test_snapshot_loads_agent_config_with_tenant_scope(self, tmp_path):
        """Initial snapshot should use the watcher tenant_id."""
        workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
        workspace_dir.mkdir(parents=True)
        (workspace_dir / "agent.json").write_text("{}", encoding="utf-8")

        watcher = AgentConfigWatcher(
            agent_id="default",
            workspace_dir=workspace_dir,
            channel_manager=None,
            tenant_id="tenant-a",
        )

        with patch(
            "swe.app.agent_config_watcher.load_agent_config",
        ) as mock_load:
            mock_load.return_value = Mock(channels=None, heartbeat=None)
            watcher._snapshot()

        mock_load.assert_called_once_with(
            "default",
            tenant_id="tenant-a",
        )

    async def test_check_loads_agent_config_with_tenant_scope(self, tmp_path):
        """Reload path should use the watcher tenant_id after file change."""
        workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
        workspace_dir.mkdir(parents=True)
        config_path = workspace_dir / "agent.json"
        config_path.write_text("{}", encoding="utf-8")

        watcher = AgentConfigWatcher(
            agent_id="default",
            workspace_dir=workspace_dir,
            channel_manager=None,
            tenant_id="tenant-a",
        )
        watcher._last_mtime = 0.0

        with patch(
            "swe.app.agent_config_watcher.load_agent_config",
        ) as mock_load:
            mock_load.return_value = Mock(channels=None, heartbeat=None)
            await watcher._check()

        mock_load.assert_called_once_with(
            "default",
            tenant_id="tenant-a",
        )

    async def test_service_factory_passes_workspace_tenant_id(self, tmp_path):
        """Workspace factory should pass tenant_id into AgentConfigWatcher."""
        workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
        workspace_dir.mkdir(parents=True)

        ws = Mock()
        ws.agent_id = "default"
        ws.workspace_dir = workspace_dir
        ws.tenant_id = "tenant-a"
        ws._service_manager = Mock()  # pylint: disable=protected-access
        ws._service_manager.services = {
            "channel_manager": AsyncMock(),
            "cron_manager": AsyncMock(),
        }

        with patch(
            "swe.app.agent_config_watcher.AgentConfigWatcher",
        ) as mock_watcher:
            watcher = Mock()
            mock_watcher.return_value = watcher

            result = await create_agent_config_watcher(ws, None)

        assert result is watcher
        mock_watcher.assert_called_once_with(
            agent_id="default",
            workspace_dir=workspace_dir,
            channel_manager=ws._service_manager.services["channel_manager"],
            cron_manager=ws._service_manager.services["cron_manager"],
            tenant_id="tenant-a",
        )

    def test_snapshot_materializes_default_console_when_channels_missing(
        self,
        tmp_path,
    ):
        workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
        workspace_dir.mkdir(parents=True)
        (workspace_dir / "agent.json").write_text("{}", encoding="utf-8")

        watcher = AgentConfigWatcher(
            agent_id="default",
            workspace_dir=workspace_dir,
            channel_manager=None,
            tenant_id="tenant-a",
        )

        with patch(
            "swe.app.agent_config_watcher.load_agent_config",
        ) as mock_load:
            mock_load.return_value = Mock(channels=None, heartbeat=None)
            watcher._snapshot()

        assert watcher._last_channels is not None
        assert watcher._last_channels.console.enabled is True
        assert watcher._last_channels.console.bot_prefix == ""
        assert watcher._last_channels_hash == watcher._channels_hash(
            watcher._last_channels,
        )


async def test_apply_channel_changes_reloads_console_when_env_filter_excludes_it(
    tmp_path,
):
    workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "agent.json").write_text("{}", encoding="utf-8")

    channel_manager = AsyncMock()
    watcher = AgentConfigWatcher(
        agent_id="default",
        workspace_dir=workspace_dir,
        channel_manager=channel_manager,
        tenant_id="tenant-a",
    )
    watcher._last_channels = ChannelConfig(
        console=ConsoleConfig(bot_prefix="[OLD]"),
    )
    watcher._last_channels_hash = watcher._channels_hash(
        watcher._last_channels,
    )
    reload_calls: list[tuple[str, str, str | None]] = []

    async def _record_reload(name, new_ch, new_channels, old_ch):
        reload_calls.append((name, new_ch.bot_prefix, old_ch.bot_prefix))

    watcher._reload_one_channel = _record_reload
    new_channels = ChannelConfig(console=ConsoleConfig(bot_prefix="[NEW]"))
    agent_config = SimpleNamespace(channels=new_channels)

    with patch(
        "swe.app.agent_config_watcher.get_available_channels",
        return_value=("zhaohu",),
    ):
        await watcher._apply_channel_changes(agent_config)

    assert reload_calls == [("console", "[NEW]", "[OLD]")]


async def test_reload_one_channel_forces_console_enabled(tmp_path):
    workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "agent.json").write_text("{}", encoding="utf-8")

    replacement = SimpleNamespace(enabled=None)
    old_channel = Mock()

    def _clone(config):
        replacement.enabled = config.enabled
        return replacement

    old_channel.clone.side_effect = _clone
    channel_manager = AsyncMock()
    channel_manager.get_channel.return_value = old_channel
    watcher = AgentConfigWatcher(
        agent_id="default",
        workspace_dir=workspace_dir,
        channel_manager=channel_manager,
        tenant_id="tenant-a",
    )
    new_channels = ChannelConfig(console=ConsoleConfig(enabled=False))

    await watcher._reload_one_channel(
        "console",
        new_channels.console,
        new_channels,
        ConsoleConfig(),
    )

    assert replacement.enabled is True
    assert new_channels.console.enabled is True


async def test_reload_one_channel_preserves_console_workspace_media_dir(
    tmp_path,
):
    workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "agent.json").write_text("{}", encoding="utf-8")

    old_channel = ConsoleChannel.from_config(
        process=Mock(),
        config=ConsoleConfig(bot_prefix="[OLD]"),
        workspace_dir=workspace_dir,
    )
    channel_manager = AsyncMock()
    channel_manager.get_channel.return_value = old_channel
    channel_manager.replace_channel = AsyncMock()
    watcher = AgentConfigWatcher(
        agent_id="default",
        workspace_dir=workspace_dir,
        channel_manager=channel_manager,
        tenant_id="tenant-a",
    )
    new_channels = ChannelConfig(console=ConsoleConfig(bot_prefix="[NEW]"))

    await watcher._reload_one_channel(
        "console",
        new_channels.console,
        new_channels,
        ConsoleConfig(bot_prefix="[OLD]"),
    )

    reloaded_channel = channel_manager.replace_channel.await_args.args[0]
    assert reloaded_channel.media_dir == workspace_dir / "media"
    assert reloaded_channel.bot_prefix == "[NEW]"


async def test_apply_channel_changes_materializes_default_console_when_missing(
    tmp_path,
):
    workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "agent.json").write_text("{}", encoding="utf-8")

    channel_manager = AsyncMock()
    watcher = AgentConfigWatcher(
        agent_id="default",
        workspace_dir=workspace_dir,
        channel_manager=channel_manager,
        tenant_id="tenant-a",
    )
    watcher._last_channels = ChannelConfig(
        console=ConsoleConfig(bot_prefix="[OLD]"),
    )
    watcher._last_channels_hash = watcher._channels_hash(
        watcher._last_channels,
    )
    reload_calls: list[tuple[str, bool, str, str | None]] = []

    async def _record_reload(name, new_ch, new_channels, old_ch):
        reload_calls.append(
            (
                name,
                new_ch.enabled,
                new_ch.bot_prefix,
                old_ch.bot_prefix if old_ch else None,
            ),
        )

    watcher._reload_one_channel = _record_reload
    agent_config = SimpleNamespace(channels=None)

    with patch(
        "swe.app.agent_config_watcher.get_available_channels",
        return_value=("zhaohu",),
    ):
        await watcher._apply_channel_changes(agent_config)

    assert ("console", True, "", "[OLD]") in reload_calls
    assert watcher._last_channels is not None
    assert watcher._last_channels.console.enabled is True
    assert watcher._last_channels.console.bot_prefix == ""


def test_resolve_channel_change_action_marks_deleted_channel_for_removal(
    tmp_path,
):
    workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "agent.json").write_text("{}", encoding="utf-8")

    watcher = AgentConfigWatcher(
        agent_id="default",
        workspace_dir=workspace_dir,
        channel_manager=AsyncMock(),
        tenant_id="tenant-a",
    )

    action = watcher._resolve_channel_change_action(
        None,
        {"enabled": True, "bot_prefix": "[OLD]"},
    )

    assert action == "remove"


async def test_reload_one_channel_adds_enabled_custom_channel(
    tmp_path,
):
    workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "agent.json").write_text("{}", encoding="utf-8")

    added_channel = Mock(channel="custom")
    channel_manager = Mock()
    channel_manager.get_channel = AsyncMock(return_value=None)
    channel_manager.instantiate_channel = Mock(return_value=added_channel)
    channel_manager.replace_channel = AsyncMock()
    watcher = AgentConfigWatcher(
        agent_id="default",
        workspace_dir=workspace_dir,
        channel_manager=channel_manager,
        tenant_id="tenant-a",
    )
    new_channels = ChannelConfig.model_validate(
        {
            "console": {},
            "custom": {"enabled": True, "bot_prefix": "[NEW]"},
        },
    )

    await watcher._reload_one_channel(
        "custom",
        getattr(new_channels, "__pydantic_extra__", {})["custom"],
        new_channels,
        None,
    )

    channel_manager.instantiate_channel.assert_called_once()
    channel_manager.replace_channel.assert_awaited_once_with(added_channel)


async def test_apply_channel_changes_adds_enabled_custom_channel(
    tmp_path,
):
    workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "agent.json").write_text("{}", encoding="utf-8")

    added_channel = Mock(channel="custom")
    channel_manager = Mock()
    channel_manager.get_channel = AsyncMock(return_value=None)
    channel_manager.instantiate_channel = Mock(return_value=added_channel)
    channel_manager.replace_channel = AsyncMock()
    watcher = AgentConfigWatcher(
        agent_id="default",
        workspace_dir=workspace_dir,
        channel_manager=channel_manager,
        tenant_id="tenant-a",
    )
    watcher._last_channels = ChannelConfig(console=ConsoleConfig())
    watcher._last_channels_hash = watcher._channels_hash(
        watcher._last_channels,
    )
    agent_config = SimpleNamespace(
        channels=ChannelConfig.model_validate(
            {
                "console": {},
                "custom": {"enabled": True, "bot_prefix": "[NEW]"},
            },
        ),
    )

    with patch(
        "swe.app.agent_config_watcher.get_available_channels",
        return_value=("zhaohu", "custom"),
    ):
        await watcher._apply_channel_changes(agent_config)

    channel_manager.instantiate_channel.assert_called_once()
    channel_manager.replace_channel.assert_awaited_once_with(added_channel)


async def test_apply_channel_changes_removes_deleted_custom_channel(
    tmp_path,
):
    workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "agent.json").write_text("{}", encoding="utf-8")

    channel_manager = AsyncMock()
    channel_manager.remove_channel = AsyncMock()
    watcher = AgentConfigWatcher(
        agent_id="default",
        workspace_dir=workspace_dir,
        channel_manager=channel_manager,
        tenant_id="tenant-a",
    )
    watcher._last_channels = ChannelConfig.model_validate(
        {
            "console": {"bot_prefix": "[OLD]"},
            "custom": {"enabled": True, "bot_prefix": "[OLD]"},
        },
    )
    watcher._last_channels_hash = watcher._channels_hash(
        watcher._last_channels,
    )
    agent_config = SimpleNamespace(
        channels=ChannelConfig(console=ConsoleConfig(bot_prefix="[OLD]")),
    )

    with patch(
        "swe.app.agent_config_watcher.get_available_channels",
        return_value=("zhaohu",),
    ):
        await watcher._apply_channel_changes(agent_config)

    channel_manager.remove_channel.assert_awaited_once_with("custom")
