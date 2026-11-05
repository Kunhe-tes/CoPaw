# -*- coding: utf-8 -*-
"""Read selected legacy resources without starting or repairing a workspace."""

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from ...config.context import encode_scope_id, is_valid_identity_value
from . import migration_source as source


def _sources(root, key):
    tenant, origin, agent, _ = key
    if not all(is_valid_identity_value(value) for value in key):
        raise ValueError("invalid_cron_identity")
    scope = encode_scope_id(tenant, origin)
    home = root / scope
    files = source._workspace_sources(
        home,
        root,
    )  # pylint: disable=protected-access
    legacy = home / "jobs.json"
    if legacy.exists() and agent == "default":
        files.append(
            source._SourceFile(
                legacy,
                str(legacy.relative_to(root)),
                scope,
                agent,
            ),
        )  # pylint: disable=protected-access
    return [
        item
        for item in (
            source._resolved_profile(item, root)
            for item in files  # pylint: disable=protected-access
        )
        if item.agent_id == agent
    ]


def _chat(path, root, candidate):
    path = path.with_name("chats.json")
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError("cron_migration_unsafe_chat_path")
    if not path.is_file():
        raise ValueError("cron_migration_chat_missing")
    with path.open("rb") as handle:
        raw = handle.read(source.MAX_FILE_BYTES + 1)
    if len(raw) > source.MAX_FILE_BYTES:
        raise ValueError("cron_migration_chat_file_too_large")
    state, definition = candidate.state_patch, candidate.definition
    chats = [
        chat
        for chat in json.loads(raw).get("chats", [])
        if chat.get("id") == state.get("task_chat_id")
    ]
    if len(chats) != 1:
        raise ValueError("cron_migration_chat_missing")
    chat = chats[0]
    expected = {
        "session_kind": "task",
        "task_job_id": definition["job_id"],
        "task_tenant_id": definition["tenant_id"],
        "task_source_id": definition["source_id"],
    }
    if (
        not state.get("task_session_id")
        or chat.get("session_id") != state["task_session_id"]
        or chat.get("user_id") != definition["creator_user_id"]
        or any(chat.get("meta", {}).get(k) != v for k, v in expected.items())
    ):
        raise ValueError("cron_migration_binding_conflict")
    if (
        chat.get("meta", {}).get("task_agent_id", definition["agent_id"])
        != definition["agent_id"]
    ):
        raise ValueError("cron_migration_binding_conflict")


def read_member(root, key, loaded):
    """Only inspect the requested tenant and Agent; no global workspace walk."""
    root = Path(root).expanduser().resolve()
    found = []
    for item in _sources(root, key):
        data, fingerprint = source._read_file(
            item,
            root,
        )  # pylint: disable=protected-access
        for raw in data["jobs"]:
            if raw.get("id") != key[3]:
                continue
            candidate = source._candidate(
                raw,
                item,
                data,
                loaded,
                fingerprint,
                datetime.now(timezone.utc),
            )  # pylint: disable=protected-access
            if candidate.identity != tuple(key):
                raise ValueError("cron_migration_identity_conflict")
            _chat(item.path, root, candidate)
            found.append(candidate)
    if len(found) != 1:
        raise ValueError(
            (
                "cron_migration_job_missing"
                if not found
                else "cron_migration_duplicate_source"
            ),
        )
    candidate = found[0]
    if candidate.definition["task_type"] not in {"text", "agent", "workflow"}:
        raise ValueError("cron_migration_system_job_unsupported")
    state = copy.deepcopy(candidate.state_patch)
    legacy_runtime = copy.deepcopy(state)
    if state.get("last_status") == "running":
        state["last_status"] = "idle"
    for field in (
        "ordinary_external_job_id",
        "batch_external_job_id",
        "next_run_at",
        "next_run_times_json",
    ):
        state.pop(field, None)
    candidate.definition["spec_json"]["schedule"]["run_on_non_workday"] = False
    spec = candidate.definition["spec_json"]
    target = {
        "user_id": candidate.definition["creator_user_id"],
        "session_id": state["task_session_id"],
    }
    spec["dispatch"]["target"] = target
    if spec.get("request") is not None:
        spec["request"].update(target)
    return {
        "definition": candidate.definition,
        "state": state,
        "legacy_runtime": legacy_runtime,
        "fingerprint": candidate.fingerprint,
        "warnings": candidate.warnings,
        "memory_available": candidate.memory_available,
    }
