# -*- coding: utf-8 -*-
"""Default Agent Profile Hook configuration management."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import tempfile
from typing import Any

from pydantic import TypeAdapter, ValidationError

from ..agents.hook_runtime.executor import execute_handler
from ..agents.hook_runtime.models import (
    CommandHookHandlerConfig,
    HookConfig,
    HookContext,
    HookHandlerConfig,
    HookHandlerResult,
)
from ..agents.hook_runtime.redaction import redact_hook_payload
from ..security.skill_scanner import SkillScanError, scan_skill_directory

logger = logging.getLogger(__name__)

ALLOWED_SCRIPT_SUFFIXES = {".py", ".sh", ".bash", ".zsh"}
MAX_SCRIPT_BYTES = 1 * 1024 * 1024
MAX_UPLOAD_FILES = 20
MAX_MANUAL_TEST_SUMMARY_LENGTH = 4096

_HANDLER_ADAPTER = TypeAdapter(HookHandlerConfig)


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


@dataclass(frozen=True)
class UploadFilePayload:
    """One uploaded Hook-script file held in memory by the HTTP boundary."""

    filename: str
    content: bytes


@dataclass(frozen=True)
class HookScriptFailure:
    """A file-level upload failure that does not fail a whole batch."""

    filename: str
    reason: str


@dataclass(frozen=True)
class HookScriptUploadResult:
    """Independent outcomes for one batch of default-profile scripts."""

    accepted: tuple[str, ...] = ()
    warned: tuple[str, ...] = ()
    failed: tuple[HookScriptFailure, ...] = ()

    @property
    def accepted_names(self) -> list[str]:
        return list(self.accepted)


@dataclass(frozen=True)
class HookManualTestResult:
    """Bounded, redacted output from executing one draft Handler."""

    handler_result: HookHandlerResult
    redacted_summary: dict[str, Any]


class HookManagementService:
    """Own Hook-console persistence for a tenant's default profile workspace."""

    def __init__(self, workspace_dir: Path, *, tenant_id: str | None) -> None:
        self._workspace_dir = Path(workspace_dir)
        self._tenant_id = tenant_id

    @property
    def _agent_config_path(self) -> Path:
        return self._workspace_dir / "agent.json"

    @property
    def _script_root(self) -> Path:
        return self._workspace_dir / "hooks" / "scripts"

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

    def upload_scripts(
        self,
        *,
        files: list[UploadFilePayload],
        overwrite_names: set[str],
        actor: HookAuditActor,
    ) -> HookScriptUploadResult:
        """Upload independent script files into the controlled library root."""
        if len(files) > MAX_UPLOAD_FILES:
            raise HookManagementValidationError(
                f"a batch may contain at most {MAX_UPLOAD_FILES} files",
            )

        self._script_root.mkdir(parents=True, exist_ok=True)
        accepted: list[str] = []
        warned: list[str] = []
        failed: list[HookScriptFailure] = []
        seen_names: set[str] = set()

        for file in files:
            try:
                self._validate_upload(file, seen_names)
                target = self._script_root / file.filename
                if target.exists() and file.filename not in overwrite_names:
                    raise HookManagementConflict(
                        f"script already exists: {file.filename}",
                    )

                old_hash = (
                    self._sha256_file(target) if target.exists() else None
                )
                scan_outcome = self._scan_upload(file)
                self._atomic_write(target, file.content)
                new_hash = hashlib.sha256(file.content).hexdigest()
                accepted.append(file.filename)
                if scan_outcome == "warning":
                    warned.append(file.filename)
                self._emit_audit(
                    event=(
                        "script_replaced"
                        if old_hash is not None
                        else "script_uploaded"
                    ),
                    actor=actor,
                    revision=self.get_configuration().revision,
                    details={
                        "filename": file.filename,
                        "old_sha256": old_hash,
                        "new_sha256": new_hash,
                        "scan_outcome": scan_outcome,
                    },
                )
            except (
                HookManagementValidationError,
                HookManagementConflict,
            ) as exc:
                failed.append(HookScriptFailure(file.filename, str(exc)))
            finally:
                seen_names.add(file.filename)

        return HookScriptUploadResult(
            accepted=tuple(accepted),
            warned=tuple(warned),
            failed=tuple(failed),
        )

    async def manual_test(
        self,
        *,
        handler: dict[str, Any],
        context: HookContext,
        actor: HookAuditActor,
    ) -> HookManualTestResult:
        """Run exactly one unsaved Handler with real external side effects."""
        revision = self.get_configuration().revision
        self._emit_audit(
            event="manual_test_requested",
            actor=actor,
            revision=revision,
        )
        try:
            normalized_handler = self._parse_handler(handler)
            normalized_context = context.model_copy(
                update={
                    "tenant_id": self._tenant_id or context.tenant_id,
                    "effective_tenant_id": self._tenant_id
                    or context.effective_tenant_id,
                    "user_id": actor.user_id or context.user_id,
                    "agent_id": "default",
                    "workspace_dir": str(self._workspace_dir),
                },
            )
            handler_result = await execute_handler(
                normalized_handler,
                normalized_context,
                workspace_dir=self._workspace_dir,
            )
        except Exception:
            self._emit_audit(
                event="manual_test_failed",
                actor=actor,
                revision=revision,
            )
            raise

        result = HookManualTestResult(
            handler_result=handler_result,
            redacted_summary=self._redacted_summary(handler_result),
        )
        self._emit_audit(
            event="manual_test_completed",
            actor=actor,
            revision=revision,
        )
        return result

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
        normalized = config.model_dump(mode="json", by_alias=True)
        self._normalize_script_references(normalized)
        return normalized

    def _parse_handler(self, handler: dict[str, Any]) -> HookHandlerConfig:
        if not isinstance(handler, dict):
            raise HookManagementValidationError("handler must be an object")
        self._reject_command_strings(
            {"events": {"PreToolUse": [{"hooks": [handler]}]}},
        )
        try:
            parsed = _HANDLER_ADAPTER.validate_python(handler)
        except ValidationError as exc:
            raise HookManagementValidationError(str(exc)) from exc
        normalized = parsed.model_dump(mode="json", by_alias=True)
        self._normalize_script_references(
            {"events": {"PreToolUse": [{"hooks": [normalized]}]}},
        )
        return _HANDLER_ADAPTER.validate_python(normalized)

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

    def _normalize_script_references(self, hooks: dict[str, Any]) -> None:
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
                    if not isinstance(handler, dict):
                        continue
                    if handler.get("type") != "command":
                        continue
                    argv = handler.get("argv", [])
                    if not isinstance(argv, list):
                        continue
                    handler["argv"] = [
                        self._normalize_script_argument(item, index)
                        for index, item in enumerate(argv)
                    ]

    def _normalize_script_argument(self, argument: Any, index: int) -> str:
        if not isinstance(argument, str):
            raise HookManagementValidationError("argv entries must be strings")
        if index == 0 or argument.startswith("-"):
            return argument

        candidate = Path(argument)
        if candidate.suffix.lower() not in ALLOWED_SCRIPT_SUFFIXES:
            return argument
        if candidate.is_absolute() or ".." in candidate.parts:
            raise HookManagementValidationError(
                "script arguments must stay inside hooks/scripts",
            )

        canonical = Path("hooks") / "scripts" / candidate.name
        if candidate != Path(candidate.name) and candidate != canonical:
            raise HookManagementValidationError(
                "script arguments must use hooks/scripts/<filename>",
            )
        if not (self._script_root / candidate.name).is_file():
            raise HookManagementValidationError(
                f"script is not in the controlled library: {candidate.name}",
            )
        return canonical.as_posix()

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
    def _validate_upload(
        file: UploadFilePayload,
        seen_names: set[str],
    ) -> None:
        filename = file.filename
        if not filename or Path(filename).name != filename:
            raise HookManagementValidationError(
                "script filename must not contain a path",
            )
        if filename in seen_names:
            raise HookManagementValidationError(
                f"duplicate filename in batch: {filename}",
            )
        if Path(filename).suffix.lower() not in ALLOWED_SCRIPT_SUFFIXES:
            raise HookManagementValidationError("unsupported script suffix")
        if len(file.content) > MAX_SCRIPT_BYTES:
            raise HookManagementValidationError(
                f"script exceeds {MAX_SCRIPT_BYTES} byte limit",
            )

    def _scan_upload(self, file: UploadFilePayload) -> str:
        with tempfile.TemporaryDirectory(
            dir=self._script_root.parent,
        ) as stage:
            stage_dir = Path(stage)
            (stage_dir / file.filename).write_bytes(file.content)
            try:
                result = scan_skill_directory(
                    stage_dir,
                    skill_name=file.filename,
                )
            except SkillScanError as exc:
                raise HookManagementValidationError(
                    f"script scan blocked upload: {exc}",
                ) from exc
        if result is not None and not result.is_safe:
            return "warning"
        return "clean" if result is not None else "off"

    @staticmethod
    def _atomic_write(target: Path, content: bytes) -> None:
        with tempfile.NamedTemporaryFile(
            dir=target.parent,
            delete=False,
        ) as staged:
            staged.write(content)
            staged_path = Path(staged.name)
        staged_path.replace(target)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

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
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record operational metadata without making logs a write dependency."""
        try:
            extra = {
                "event": event,
                "actor_user_id": actor.user_id,
                "actor_tenant_id": actor.tenant_id,
                "tenant_id": self._tenant_id,
                "agent_id": "default",
                "configuration_revision": revision,
            }
            if details:
                extra.update(details)
            logger.info("agent_hook.audit", extra=extra)
        except (
            Exception
        ):  # pragma: no cover - logging failures are best effort
            pass

    @staticmethod
    def _redacted_summary(result: HookHandlerResult) -> dict[str, Any]:
        summary = redact_hook_payload(result.model_dump(mode="json"))
        return HookManagementService._bound_summary(summary)

    @staticmethod
    def _bound_summary(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: HookManagementService._bound_summary(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                HookManagementService._bound_summary(item) for item in value
            ]
        if isinstance(value, str):
            return value[:MAX_MANUAL_TEST_SUMMARY_LENGTH]
        return value
