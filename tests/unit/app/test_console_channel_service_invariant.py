# -*- coding: utf-8 -*-

from types import SimpleNamespace
from unittest.mock import Mock, patch

from swe.app.workspace.service_factories import create_channel_service


async def test_create_channel_service_materializes_console_when_channels_missing(
    tmp_path,
):
    workspace_dir = tmp_path / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)

    runner = Mock()
    channel_manager = Mock()
    ws = SimpleNamespace(
        agent_id="default",
        tenant_id="tenant-a",
        workspace_dir=workspace_dir,
        _config=SimpleNamespace(channels=None),
        _service_manager=SimpleNamespace(
            services={"runner": runner},
        ),
    )

    with (
        patch(
            "swe.app.channels.utils.make_process_from_runner",
            return_value=Mock(),
        ),
        patch(
            "swe.app.channels.manager.ChannelManager.from_config",
            return_value=channel_manager,
        ) as mock_from_config,
    ):
        await create_channel_service(ws, None)

    temp_config = mock_from_config.call_args.kwargs["config"]
    assert temp_config.channels.console.enabled is True
    channel_manager.set_workspace.assert_called_once_with(ws)
