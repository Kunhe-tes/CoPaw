# -*- coding: utf-8 -*-
"""Watch agent.json for changes and auto-reload agent components.

This watcher monitors an agent's workspace/agent.json file for changes
and automatically reloads channels, heartbeat, and other configurations
without requiring manual restart.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from ..config.channel_invariants import include_mandatory_channels
from ..config.config import (
    load_agent_config,
    normalize_channel_config_set,
    normalize_single_channel_config,
)
from ..config.utils import get_available_channels

if TYPE_CHECKING:
    from ..config.config import ChannelConfig, HeartbeatConfig

logger = logging.getLogger(__name__)

# How often to poll (seconds)
DEFAULT_POLL_INTERVAL = 2.0


def _heartbeat_hash(hb: Optional[HeartbeatConfig]) -> int:
    """Hash of heartbeat config for change detection."""
    if hb is None:
        return hash("None")
    return hash(str(hb.model_dump(mode="json")))


def _memory_job_hash(memory_summary: Optional[Any]) -> int:
    """Hash of memory job config for change detection."""
    if memory_summary is None:
        return hash("None")
    cron_expr = getattr(memory_summary, "dream_cron", "")
    return hash(str(cron_expr))


class AgentConfigWatcher:
    """Poll agent.json mtime and reload changed configs automatically.

    This watcher is agent-scoped and monitors a specific agent's
    workspace/agent.json file for configuration changes.
    """

    def __init__(
        self,
        agent_id: str,
        workspace_dir: Path,
        channel_manager: Any,
        cron_manager: Any = None,
        tenant_id: str | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ):
        """Initialize agent config watcher.

        Args:
            agent_id: Agent ID to monitor
            workspace_dir: Path to agent's workspace directory
            channel_manager: ChannelManager instance for this agent
            cron_manager: CronManager instance for this agent (optional)
            tenant_id: Optional tenant ID owning this workspace
            poll_interval: How often to check for changes (seconds)
        """
        self._agent_id = agent_id
        self._workspace_dir = workspace_dir
        self._config_path = workspace_dir / "agent.json"
        self._channel_manager = channel_manager
        self._cron_manager = cron_manager
        self._tenant_id = tenant_id
        self._poll_interval = poll_interval
        self._task: Optional[asyncio.Task] = None

        # Snapshot of the last known config (for diffing)
        self._last_channels: Optional[ChannelConfig] = None
        self._last_channels_hash: Optional[int] = None
        self._last_heartbeat_hash: Optional[int] = None
        self._last_memory_job_hash: Optional[int] = None
        # mtime of agent.json at last check
        self._last_mtime: float = 0.0

    def _load_agent_config(self):
        """Load agent config using the owning tenant scope."""
        return load_agent_config(
            self._agent_id,
            tenant_id=self._tenant_id,
        )

    async def start(self) -> None:
        """Take initial snapshot and start the polling task."""
        self._snapshot()
        self._task = asyncio.create_task(
            self._poll_loop(),
            name=f"agent_config_watcher_{self._agent_id}",
        )
        logger.info(
            f"AgentConfigWatcher started for agent {self._agent_id} "
            f"(poll={self._poll_interval}s, path={self._config_path})",
        )

    async def stop(self) -> None:
        """Stop the polling task."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info(f"AgentConfigWatcher stopped for agent {self._agent_id}")

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _snapshot(self) -> None:
        """Load current agent config; record mtime and hashes."""
        try:
            self._last_mtime = self._config_path.stat().st_mtime
        except FileNotFoundError:
            self._last_mtime = 0.0

        try:
            agent_config = self._load_agent_config()
            normalized_channels = normalize_channel_config_set(
                agent_config.channels,
                materialize_missing_console=True,
            )
            self._last_channels = normalized_channels
            self._last_channels_hash = (
                self._channels_hash(normalized_channels)
                if normalized_channels is not None
                else None
            )

            self._last_heartbeat_hash = _heartbeat_hash(
                agent_config.heartbeat,
            )
            self._last_memory_job_hash = _memory_job_hash(
                getattr(agent_config.running, "memory_summary", None),
            )
        except Exception:
            logger.exception(
                f"AgentConfigWatcher: failed to load initial config "
                f"for agent {self._agent_id}",
            )
            self._last_channels = None
            self._last_channels_hash = None
            self._last_heartbeat_hash = None
            self._last_memory_job_hash = None

    @staticmethod
    def _channels_hash(channels: ChannelConfig) -> int:
        """Fast hash of channels section for quick change detection."""
        return hash(str(channels.model_dump(mode="json")))

    @staticmethod
    def _channel_dump(ch: Any) -> Any:
        """Return JSON-serializable dict for channel config, or None."""
        if ch is None:
            return None
        if isinstance(ch, dict):
            return ch
        if hasattr(ch, "model_dump"):
            return ch.model_dump(mode="json")
        return None

    @staticmethod
    def _channel_enabled(ch: Any) -> bool:
        """Return whether a channel config is enabled."""
        if ch is None:
            return False
        if isinstance(ch, dict):
            return bool(ch.get("enabled", False))
        return bool(getattr(ch, "enabled", False))

    @staticmethod
    def _extra_channel_configs(channels: Any) -> dict[str, Any]:
        """Return ad-hoc channel configs stored in pydantic extras."""
        return getattr(channels, "__pydantic_extra__", None) or {}

    @staticmethod
    def _channel_config_for_name(
        channels: Any,
        extra_channels: dict[str, Any],
        name: str,
    ) -> Any:
        """Return the named channel config from model fields or extras."""
        return getattr(channels, name, None) or extra_channels.get(name)

    @classmethod
    def _resolve_channel_change_action(
        cls,
        new_ch: Any,
        old_ch: Any,
    ) -> str | None:
        """Return the channel action needed for a before/after config pair."""
        if new_ch is None and old_ch is None:
            return None
        if new_ch is None:
            return "remove"
        if old_ch is None and not cls._channel_enabled(new_ch):
            return None
        new_dump = cls._channel_dump(new_ch)
        old_dump = cls._channel_dump(old_ch)
        if new_dump is not None and new_dump == old_dump:
            return None
        return "reload"

    def _channel_names_for_diff(
        self,
        new_channels: ChannelConfig,
        old_channels: ChannelConfig | None,
    ) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
        """Return channel names and extra config maps participating in diff."""
        extra_new = self._extra_channel_configs(new_channels)
        extra_old = (
            self._extra_channel_configs(old_channels) if old_channels else {}
        )
        channel_names = include_mandatory_channels(
            (
                *get_available_channels(),
                *extra_new.keys(),
                *extra_old.keys(),
            ),
        )
        return channel_names, extra_new, extra_old

    async def _remove_one_channel(
        self,
        name: str,
        new_channels: ChannelConfig,
        old_ch: Any,
    ) -> None:
        """Remove one channel and restore config state if removal fails."""
        logger.info(
            f"AgentConfigWatcher ({self._agent_id}): "
            f"channel '{name}' removed, stopping",
        )
        try:
            await self._channel_manager.remove_channel(name)
        except Exception:
            logger.exception(
                f"AgentConfigWatcher ({self._agent_id}): "
                f"failed to remove channel '{name}'",
            )
            setattr(new_channels, name, old_ch)

    async def _reload_one_channel(
        self,
        name: str,
        new_ch: Any,
        new_channels: ChannelConfig,
        old_ch: Any,
    ) -> None:
        """Reload a single channel; on failure revert new_channels entry."""
        try:
            new_ch = normalize_single_channel_config(
                name,
                new_ch,
                materialize_missing=(name == "console"),
            )
            setattr(new_channels, name, new_ch)
            old_channel = await self._channel_manager.get_channel(name)
            if old_channel is None:
                logger.info(
                    f"AgentConfigWatcher ({self._agent_id}): "
                    f"channel '{name}' not loaded, creating",
                )
                new_channel = self._channel_manager.instantiate_channel(
                    name,
                    new_ch,
                    workspace_dir=self._workspace_dir,
                )
            else:
                new_channel = old_channel.clone(new_ch)
            await self._channel_manager.replace_channel(new_channel)
            logger.info(
                f"AgentConfigWatcher ({self._agent_id}): "
                f"channel '{name}' reloaded",
            )
        except Exception:
            logger.exception(
                f"AgentConfigWatcher ({self._agent_id}): "
                f"failed to reload channel '{name}'",
            )
            setattr(new_channels, name, old_ch if old_ch else new_ch)

    async def _apply_channel_changes(self, agent_config: Any) -> None:
        """Diff channels and reload changed ones; update snapshot."""
        new_channels = normalize_channel_config_set(
            agent_config.channels,
            materialize_missing_console=True,
        )
        if new_channels is None:
            return

        new_hash = self._channels_hash(new_channels)
        if new_hash == self._last_channels_hash:
            return

        old_channels = self._last_channels
        channel_names, extra_new, extra_old = self._channel_names_for_diff(
            new_channels,
            old_channels,
        )

        for name in channel_names:
            new_ch = self._channel_config_for_name(
                new_channels,
                extra_new,
                name,
            )
            old_ch = (
                self._channel_config_for_name(
                    old_channels,
                    extra_old,
                    name,
                )
                if old_channels
                else None
            )
            action = self._resolve_channel_change_action(new_ch, old_ch)
            if action is None:
                continue
            if action == "remove":
                await self._remove_one_channel(name, new_channels, old_ch)
                continue
            logger.info(
                f"AgentConfigWatcher ({self._agent_id}): "
                f"channel '{name}' config changed, reloading",
            )
            await self._reload_one_channel(name, new_ch, new_channels, old_ch)

        self._last_channels = new_channels.model_copy(deep=True)
        self._last_channels_hash = self._channels_hash(new_channels)

    async def _apply_heartbeat_change(self, agent_config: Any) -> None:
        """Update heartbeat hash. Scheduling is handled externally."""
        new_hb_hash = _heartbeat_hash(agent_config.heartbeat)
        if (
            self._cron_manager is not None
            and new_hb_hash != self._last_heartbeat_hash
        ):
            self._last_heartbeat_hash = new_hb_hash
            logger.info(
                f"AgentConfigWatcher ({self._agent_id}): "
                f"heartbeat config updated (external scheduling)",
            )
        else:
            self._last_heartbeat_hash = new_hb_hash

    async def _apply_memory_job_change(self, agent_config: Any) -> None:
        """Update memory job hash. Scheduling is handled externally."""
        new_memory_summary = getattr(
            agent_config.running,
            "memory_summary",
            None,
        )
        new_memory_job_hash = _memory_job_hash(new_memory_summary)
        if (
            self._cron_manager is not None
            and new_memory_job_hash != self._last_memory_job_hash
        ):
            self._last_memory_job_hash = new_memory_job_hash
            logger.info(
                f"AgentConfigWatcher ({self._agent_id}): "
                f"memory job config updated (external scheduling)",
            )
        else:
            self._last_memory_job_hash = new_memory_job_hash

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while True:
            try:
                await asyncio.sleep(self._poll_interval)
                await self._check()
            except Exception:
                logger.exception(
                    f"AgentConfigWatcher ({self._agent_id}): "
                    f"poll iteration failed",
                )

    async def _check(self) -> None:
        """Check for config changes and reload if needed."""
        try:
            mtime = self._config_path.stat().st_mtime
        except FileNotFoundError:
            return

        if mtime == self._last_mtime:
            return

        self._last_mtime = mtime

        try:
            agent_config = self._load_agent_config()
        except Exception:
            logger.exception(
                f"AgentConfigWatcher ({self._agent_id}): "
                f"failed to parse agent.json",
            )
            return

        # Apply changes
        if self._channel_manager:
            await self._apply_channel_changes(agent_config)
        if self._cron_manager:
            await self._apply_heartbeat_change(agent_config)
            await self._apply_memory_job_change(agent_config)
