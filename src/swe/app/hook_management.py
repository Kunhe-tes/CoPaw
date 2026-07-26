# -*- coding: utf-8 -*-
"""Default Agent Profile Hook configuration management."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..agents.hook_runtime.models import HookConfig

logger = logging.getLogger(__name__)


class HookManagementConflict(Exception):
    """Raised when a client saves against an obsolete Hook revision."""


class HookManagementValidationError(ValueError):
    """Raised when Hook-console constraints reject a draft."""


@dataclass(frozen=True)
class HookAuditActor:
    """Request actor identity retained in Hook-management audit logs."""

    user_id: str | None
    tenant_id: str | None


@dataclass(frozen=True)
class HookConfigurationSnapshot:
    """A default profile Hook draft plus its optimistic-lock revision."""

    hooks: dict[str, Any]
    revision: str


class HookManagementService:
    """Own Hook-console persistence for a tenant's default profile workspace."""

    def __init__(self, workspace_dir: Path, *, tenant_id: str | None) -> None:
        self._workspace_dir = Path(workspace_dir)
        self._tenant_id = tenant_id

    @property
    def _agent_config_path(self) -> Path:
        return self._workspace_dir / "agent.json"

    def get_configuration(self) -> HookConfigurationSnapshot:
        """Return the validated Hook configuration stored for the default profile."""
        hooks = self._load_hooks()
        return HookConfigurationSnapshot(
            hooks=hooks,
            revision=self._revision_for(hooks),
        )

    def save_configuration(
        self,
        *,
        hooks: dict[str, Any],
        expected_revision: str,
        actor: HookAuditActor,
    ) -> HookConfigurationSnapshot:
        """Validate and persist a Hook draft when its revision is current."""
        current = self.get_configuration()
        if expected_revision != current.revision:
            raise HookManagementConflict(
                "hook configuration revision is stale",
            )

        normalized_hooks = self._validate_hooks(hooks)
        agent_config = self._load_agent_config()
        agent_config["hooks"] = normalized_hooks
        self._write_agent_config(agent_config)

        snapshot = HookConfigurationSnapshot(
            hooks=normalized_hooks,
            revision=self._revision_for(normalized_hooks),
        )
        self._emit_audit(
            event="configuration_saved",
            actor=actor,
            revision=snapshot.revision,
        )
        return snapshot

    def _load_agent_config(self) -> dict[str, Any]:
        try:
            with self._agent_config_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError as exc:
            raise HookManagementValidationError(
                "default agent configuration does not exist",
            ) from exc
        except json.JSONDecodeError as exc:
            raise HookManagementValidationError(
                "default agent configuration is invalid JSON",
            ) from exc

        if not isinstance(data, dict):
            raise HookManagementValidationError(
                "default agent configuration must be an object",
            )
        return data

    def _load_hooks(self) -> dict[str, Any]:
        agent_config = self._load_agent_config()
        raw_hooks = agent_config.get("hooks", {})
        if not isinstance(raw_hooks, dict):
            raise HookManagementValidationError(
                "agent hooks must be an object",
            )
        return self._validate_hooks(raw_hooks)

    def _validate_hooks(self, hooks: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(hooks, dict):
            raise HookManagementValidationError("hooks must be an object")

        self._reject_command_strings(hooks)
        try:
            config = HookConfig.model_validate(hooks)
        except ValidationError as exc:
            raise HookManagementValidationError(str(exc)) from exc

        self._validate_unique_ids(config)
        return config.model_dump(mode="json", by_alias=True)

    @staticmethod
    def _reject_command_strings(hooks: dict[str, Any]) -> None:
        events = hooks.get("events", {})
        if not isinstance(events, dict):
            return
        for groups in events.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, dict):
                    continue
                for handler in group.get("hooks", []):
                    if (
                        isinstance(handler, dict)
                        and handler.get("type") == "command"
                        and str(handler.get("command", "")).strip()
                    ):
                        raise HookManagementValidationError(
                            "command handler command strings are not supported; use argv",
                        )

    @staticmethod
    def _validate_unique_ids(config: HookConfig) -> None:
        group_ids: set[str] = set()
        handler_ids: set[str] = set()
        for groups in config.events.values():
            for group in groups:
                if group.id:
                    if group.id in group_ids:
                        raise HookManagementValidationError(
                            f"duplicate matcher group id: {group.id}",
                        )
                    group_ids.add(group.id)
                for handler in group.hooks:
                    if handler.id in handler_ids:
                        raise HookManagementValidationError(
                            f"duplicate handler id: {handler.id}",
                        )
                    handler_ids.add(handler.id)

    def _write_agent_config(self, agent_config: dict[str, Any]) -> None:
        with self._agent_config_path.open("w", encoding="utf-8") as file:
            json.dump(agent_config, file, ensure_ascii=False, indent=2)
            file.write("\n")

    @staticmethod
    def _revision_for(hooks: dict[str, Any]) -> str:
        canonical = json.dumps(
            hooks,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _emit_audit(
        self,
        *,
        event: str,
        actor: HookAuditActor,
        revision: str,
    ) -> None:
        """Record operational metadata without making logs a write dependency."""
        try:
            logger.info(
                "agent_hook.audit",
                extra={
                    "event": event,
                    "actor_user_id": actor.user_id,
                    "actor_tenant_id": actor.tenant_id,
                    "tenant_id": self._tenant_id,
                    "agent_id": "default",
                    "configuration_revision": revision,
                },
            )
        except (
            Exception
        ):  # pragma: no cover - logging failures are best effort
            pass
