# -*- coding: utf-8 -*-
"""Source-tool catalogue lifecycle service."""

from __future__ import annotations

import hashlib
import tempfile
import time
from pathlib import Path
from typing import Callable

from swe.security.skill_scanner import SkillScanError, scan_skill_directory

from .models import (
    SourceToolAuditEvent,
    SourceToolDraft,
    SourceToolMetadata,
    SourceToolVersion,
)
from .store import SourceToolStore
from .validation import (
    SourceToolContract,
    SourceToolValidationError,
    validate_source_tool_script,
)


class SourceToolConflict(RuntimeError):
    """Raised when a lifecycle action needs explicit user confirmation."""


class SourceToolSafetyError(RuntimeError):
    """Raised when the mandatory safety gate cannot accept an upload."""


SafetyScan = Callable[[bytes, str], bool]
_INSTALLED_SOURCE_TOOL_SERVICE: "SourceToolService | None" = None


def install_source_tool_service(service: "SourceToolService") -> None:
    """Install the process-local catalogue resolver used by Agent construction."""
    global _INSTALLED_SOURCE_TOOL_SERVICE
    _INSTALLED_SOURCE_TOOL_SERVICE = service


def get_source_tool_service() -> "SourceToolService | None":
    """Return the installed catalogue resolver, if application startup completed."""
    return _INSTALLED_SOURCE_TOOL_SERVICE


class SourceToolService:
    """Manage source-owned drafts, immutable versions, and active catalogue."""

    def __init__(
        self,
        store: SourceToolStore,
        *,
        safety_scan: SafetyScan | None = None,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._store = store
        self._safety_scan = safety_scan or _scan_source_tool
        self._time_fn = time_fn or time.time

    def create_draft(
        self,
        source_id: str,
        content: bytes,
        *,
        actor: str | None,
        replace_draft: bool = False,
    ) -> SourceToolDraft:
        """Validate, scan, and persist one unpublished source-tool draft."""
        contract = validate_source_tool_script(content)
        self._require_safe_scan(content, contract.name)
        state = self._store.load()
        source = _source_state(state, source_id)
        drafts = source["drafts"]
        has_existing_draft = contract.name in drafts
        if has_existing_draft and not replace_draft:
            raise SourceToolConflict(
                "an unpublished draft already exists; explicit draft "
                "replacement is required",
            )
        draft = _new_draft(contract, content, actor, self._time_fn())
        drafts[contract.name] = draft.to_dict()
        _append_audit(
            source,
            SourceToolAuditEvent(
                event=(
                    "draft_replaced"
                    if has_existing_draft and replace_draft
                    else "draft_created"
                ),
                source_id=source_id,
                tool_name=contract.name,
                actor=actor,
                timestamp=self._time_fn(),
                content_digest=draft.content_digest,
            ),
        )
        self._store.save(state)
        return draft

    def list_drafts(self, source_id: str) -> tuple[SourceToolDraft, ...]:
        """Return source drafts without exposing them to ordinary catalogue APIs."""
        source = _read_source_state(self._store.load(), source_id)
        if source is None:
            return ()
        return tuple(
            SourceToolDraft.from_dict(value)
            for _, value in sorted(source["drafts"].items())
        )

    def download_draft(self, source_id: str, tool_name: str) -> bytes:
        """Return draft content for manager/admin controlled download."""
        source = _require_source(self._store.load(), source_id)
        try:
            return SourceToolDraft.from_dict(
                source["drafts"][tool_name],
            ).script.encode(
                "utf-8",
            )
        except KeyError as exc:
            raise KeyError(
                f"source tool draft not found: {tool_name}",
            ) from exc

    def get_draft(self, source_id: str, tool_name: str) -> SourceToolDraft:
        """Resolve one current draft for guarded manual execution."""
        source = _require_source(self._store.load(), source_id)
        try:
            return SourceToolDraft.from_dict(source["drafts"][tool_name])
        except KeyError as exc:
            raise KeyError(
                f"source tool draft not found: {tool_name}",
            ) from exc

    def discard_draft(
        self,
        source_id: str,
        tool_name: str,
        *,
        actor: str | None,
    ) -> None:
        """Discard a draft while retaining metadata-only lifecycle audit."""
        state = self._store.load()
        source = _require_source(state, source_id)
        try:
            draft = SourceToolDraft.from_dict(
                source["drafts"].pop(tool_name),
            )
        except KeyError as exc:
            raise KeyError(
                f"source tool draft not found: {tool_name}",
            ) from exc
        _append_audit(
            source,
            SourceToolAuditEvent(
                event="draft_discarded",
                source_id=source_id,
                tool_name=tool_name,
                actor=actor,
                timestamp=self._time_fn(),
                content_digest=draft.content_digest,
            ),
        )
        self._store.save(state)

    def publish(
        self,
        source_id: str,
        tool_name: str,
        *,
        actor: str | None,
        confirm_replace: bool = False,
    ) -> SourceToolVersion:
        """Publish a draft as the next immutable active version."""
        state = self._store.load()
        source = _require_source(state, source_id)
        try:
            draft = SourceToolDraft.from_dict(source["drafts"][tool_name])
        except KeyError as exc:
            raise KeyError(
                f"source tool draft not found: {tool_name}",
            ) from exc
        _validate_code_builtin_override_schema(draft)
        if tool_name in source["active"] and not confirm_replace:
            active_version = int(source["active"][tool_name])
            raise SourceToolConflict(
                "active source tool exists at version "
                f"{active_version}; explicit replacement confirmation is required",
            )
        existing = source["history"].get(tool_name, [])
        version = (
            max(int(record["version"]) for record in existing) + 1
            if existing
            else 1
        )
        published = SourceToolVersion(
            name=draft.name,
            version=version,
            description=draft.description,
            json_schema=draft.json_schema,
            required_env=draft.required_env,
            content_digest=draft.content_digest,
            script=draft.script,
            created_at=self._time_fn(),
            created_by=actor,
        )
        source["history"].setdefault(tool_name, []).append(published.to_dict())
        source["active"][tool_name] = version
        del source["drafts"][tool_name]
        _append_audit(
            source,
            SourceToolAuditEvent(
                event="published",
                source_id=source_id,
                tool_name=tool_name,
                actor=actor,
                timestamp=self._time_fn(),
                version=version,
                content_digest=published.content_digest,
            ),
        )
        self._store.save(state)
        return published

    def deactivate(
        self,
        source_id: str,
        tool_name: str,
        *,
        actor: str | None,
    ) -> None:
        """Remove one version from the active catalogue without deleting history."""
        state = self._store.load()
        source = _require_source(state, source_id)
        try:
            version = int(source["active"].pop(tool_name))
        except KeyError as exc:
            raise KeyError(
                f"active source tool not found: {tool_name}",
            ) from exc
        _append_audit(
            source,
            SourceToolAuditEvent(
                event="deactivated",
                source_id=source_id,
                tool_name=tool_name,
                actor=actor,
                timestamp=self._time_fn(),
                version=version,
            ),
        )
        self._store.save(state)

    def get_active_catalog(
        self,
        source_id: str,
    ) -> tuple[SourceToolVersion, ...]:
        """Snapshot active tools for a source; callers retain this snapshot."""
        source = _read_source_state(self._store.load(), source_id)
        if source is None:
            return ()
        return tuple(
            _version_for(source, name, int(version))
            for name, version in sorted(source["active"].items())
        )

    def list_metadata(
        self,
        source_id: str,
    ) -> tuple[SourceToolMetadata, ...]:
        """Return script-free metadata for the effective source catalogue."""
        return tuple(
            record.metadata(active=True)
            for record in self.get_active_catalog(source_id)
        )

    def history(
        self,
        source_id: str,
        tool_name: str,
    ) -> tuple[SourceToolVersion, ...]:
        """Return immutable version history, newest first, for managers."""
        source = _require_source(self._store.load(), source_id)
        return tuple(
            SourceToolVersion.from_dict(record)
            for record in reversed(source["history"].get(tool_name, []))
        )

    def download_version(
        self,
        source_id: str,
        tool_name: str,
        version: int,
    ) -> bytes:
        """Return immutable version content for manager/admin download."""
        return _version_for(
            _require_source(self._store.load(), source_id),
            tool_name,
            version,
        ).script.encode("utf-8")

    def audit(self, source_id: str) -> tuple[SourceToolAuditEvent, ...]:
        """Return metadata-only source tool lifecycle audit."""
        source = _read_source_state(self._store.load(), source_id)
        if source is None:
            return ()
        return tuple(
            SourceToolAuditEvent.from_dict(value) for value in source["audit"]
        )

    def record_invocation(
        self,
        *,
        source_id: str,
        tool: SourceToolVersion,
        tenant_id: str | None,
        agent_id: str | None,
        result: str,
    ) -> None:
        """Append source/version attribution without retaining input or secrets."""
        state = self._store.load()
        source = _source_state(state, source_id)
        _append_audit(
            source,
            SourceToolAuditEvent(
                event="invoked",
                source_id=source_id,
                tool_name=tool.name,
                actor=None,
                timestamp=self._time_fn(),
                version=tool.version,
                content_digest=tool.content_digest,
                tenant_id=tenant_id,
                agent_id=agent_id,
                result=result,
            ),
        )
        self._store.save(state)

    def record_manual_test(
        self,
        *,
        source_id: str,
        tool: SourceToolVersion,
        actor: str | None,
        tenant_id: str | None,
        agent_id: str | None,
        result: str,
    ) -> None:
        """Audit an explicit draft test without retaining test inputs."""
        state = self._store.load()
        source = _source_state(state, source_id)
        _append_audit(
            source,
            SourceToolAuditEvent(
                event="manual_test_" + result,
                source_id=source_id,
                tool_name=tool.name,
                actor=actor,
                timestamp=self._time_fn(),
                version=tool.version,
                content_digest=tool.content_digest,
                tenant_id=tenant_id,
                agent_id=agent_id,
                result=result,
            ),
        )
        self._store.save(state)

    def _require_safe_scan(self, content: bytes, tool_name: str) -> None:
        try:
            is_safe = self._safety_scan(content, tool_name)
        except Exception as exc:
            raise SourceToolSafetyError(
                "source tool safety scan is unavailable",
            ) from exc
        if not is_safe:
            raise SourceToolSafetyError(
                "source tool safety scan found unsafe code",
            )


def _scan_source_tool(content: bytes, tool_name: str) -> bool:
    """Run the existing scanner as an always-on, fail-closed upload gate."""
    with tempfile.TemporaryDirectory() as stage:
        script_path = Path(stage) / "tool.py"
        script_path.write_bytes(content)
        try:
            result = scan_skill_directory(
                stage,
                skill_name=f"source-tool-{tool_name}",
                block=True,
            )
        except SkillScanError:
            return False
    return result is not None and bool(result.is_safe)


def _validate_code_builtin_override_schema(draft: SourceToolDraft) -> None:
    """Reject a source override unless it matches its code builtin exactly."""
    from agentscope.tool import Toolkit
    from swe.agents.tools import (
        copy_file_to_static,
        edit_file,
        execute_shell_command,
        get_current_time,
        glob_search,
        grep_search,
        read_file,
        update_task_progress,
        write_file,
    )
    from swe.config.config import _default_builtin_tools

    if draft.name not in _default_builtin_tools():
        return
    tool_functions = {
        "execute_shell_command": execute_shell_command,
        "read_file": read_file,
        "write_file": write_file,
        "edit_file": edit_file,
        "grep_search": grep_search,
        "glob_search": glob_search,
        "get_current_time": get_current_time,
        "copy_file_to_static": copy_file_to_static,
        "update_task_progress": update_task_progress,
    }
    tool_function = tool_functions.get(draft.name)
    if tool_function is None:
        raise SourceToolValidationError(
            "source override targets a builtin that is not code-registered: "
            + draft.name,
        )
    toolkit = Toolkit()
    toolkit.register_tool_function(tool_function)
    registered_schema = getattr(toolkit.tools[draft.name], "json_schema", None)
    expected_schema = (
        registered_schema.get("function", {}).get("parameters")
        if isinstance(registered_schema, dict)
        else None
    )
    if expected_schema != draft.json_schema:
        raise SourceToolValidationError(
            "source override schema must match the code-defined builtin: "
            + draft.name,
        )


def _new_draft(
    contract: SourceToolContract,
    content: bytes,
    actor: str | None,
    now: float,
) -> SourceToolDraft:
    return SourceToolDraft(
        name=contract.name,
        description=contract.description,
        json_schema=contract.json_schema,
        required_env=contract.required_env,
        content_digest=hashlib.sha256(content).hexdigest(),
        script=content.decode("utf-8"),
        created_at=now,
        created_by=actor,
    )


def _source_state(state: dict, source_id: str) -> dict:
    return state.setdefault("sources", {}).setdefault(
        source_id,
        {"drafts": {}, "history": {}, "active": {}, "audit": []},
    )


def _read_source_state(state: dict, source_id: str) -> dict | None:
    return state.get("sources", {}).get(source_id)


def _require_source(state: dict, source_id: str) -> dict:
    source = _read_source_state(state, source_id)
    if source is None:
        raise KeyError(f"source tool catalogue not found: {source_id}")
    return source


def _version_for(
    source: dict,
    tool_name: str,
    version: int,
) -> SourceToolVersion:
    for record in source["history"].get(tool_name, []):
        if int(record["version"]) == version:
            return SourceToolVersion.from_dict(record)
    raise KeyError(f"source tool version not found: {tool_name}@{version}")


def _append_audit(source: dict, event: SourceToolAuditEvent) -> None:
    source["audit"].append(event.to_dict())
