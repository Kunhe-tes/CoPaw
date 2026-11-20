# -*- coding: utf-8 -*-
import json
from pathlib import Path
import uuid

from swe.app.runner.models import ChatSpec, ChatsFile
from swe.app.conversation_storage.migration.inventory_v3 import (
    inventory_discovery,
)


def _mapping(root):
    return {
        "service_unit_id": "service",
        "tenant_id": "tenant",
        "source_id": "source",
        "agent_id": "agent",
        "root": str(root),
        "position": "workspace-position",
    }


def _report(root):
    return inventory_discovery(
        {
            "source_binding_storage": "manifest-v1",
            "source_isolation": True,
            "workspaces": [_mapping(root)],
            "tenants": [],
            "shares": [],
            "services": [],
            "fingerprints": [],
        },
    )


def _chat(*, session_id="session", meta=None):
    return ChatSpec(
        id=str(uuid.uuid4()),
        session_id=session_id,
        user_id="user",
        channel="console",
        meta=meta or {},
    )


def _write_registry(root, chats):
    (root / "chats.json").write_text(
        ChatsFile(chats=chats).model_dump_json(),
    )


def _write_session(root, name="user_session.json", **extra):
    (root / "sessions" / name).write_text(
        json.dumps({"schema_version": 1, **extra}),
    )


def test_manifest_v1_uses_registered_inputs_and_ignores_unmapped_objects(
    tmp_path,
):
    root = tmp_path / "workspace"
    (root / "sessions").mkdir(parents=True)
    (root / "dialog").mkdir()
    chat = _chat()
    _write_registry(root, [chat])
    _write_session(root)
    (root / "sessions" / "orphan.json").write_text("{")
    ledger = root / "sessions" / ".turn-ledger" / "unknown"
    ledger.mkdir(parents=True)
    (ledger / "metadata.json").write_text("{")
    (root / "dialog" / "unknown-chat").mkdir()
    (root / "dialog" / "journal-v2-quarantine.json").write_text("{")
    (root / "sessions" / "unrelated-link").symlink_to(tmp_path)
    root.chmod(0o755)
    (root / "sessions").chmod(0o755)
    (root / "dialog").chmod(0o755)

    result = _report(root)

    assert result["ready"], result["blockers"]
    assert len(result["workspaces"][0]["sessions"]) == 1
    paths = {item["path"] for item in result["files"]}
    assert paths == {"chats.json", "sessions/user_session.json"}


def test_manifest_v1_accepts_large_registry_and_registered_session(tmp_path):
    root = tmp_path / "workspace"
    (root / "sessions").mkdir(parents=True)
    (root / "dialog").mkdir()
    chat = _chat(meta={"large": "x" * (9 * 1024 * 1024)})
    _write_registry(root, [chat])
    _write_session(root, future_module={"large": "y" * (9 * 1024 * 1024)})

    result = _report(root)

    assert result["ready"], result["blockers"]
    assert len(result["workspaces"][0]["sessions"]) == 1


def test_manifest_v1_accepts_in_workspace_session_symlink(tmp_path):
    root = tmp_path / "workspace"
    (root / "sessions").mkdir(parents=True)
    (root / "dialog").mkdir()
    chat = _chat(session_id="quarantine")
    _write_registry(root, [chat])
    _write_session(root, "actual.json", retained=True)
    (root / "sessions" / "user_quarantine.json").symlink_to("actual.json")

    result = _report(root)

    assert result["ready"], result["blockers"]
    assert result["workspaces"][0]["sessions"][0]["legacy"]["state"][
        "retained"
    ]


def test_manifest_v1_accepts_in_workspace_chats_symlink(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "sessions").mkdir()
    actual = root / "registry.json"
    actual.write_text(ChatsFile(chats=[_chat()]).model_dump_json())
    (root / "chats.json").symlink_to(actual.name)
    _write_session(root)

    result = _report(root)

    assert result["ready"], result["blockers"]
    assert len(result["workspaces"][0]["chats"]) == 1


def test_manifest_v1_accepts_in_workspace_sessions_directory_symlink(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    actual = root / "session-data"
    actual.mkdir()
    (actual / "user_session.json").write_text(
        json.dumps({"schema_version": 1}),
    )
    (root / "sessions").symlink_to(actual.name)
    (root / "dialog").mkdir()
    _write_registry(root, [_chat()])

    result = _report(root)

    assert result["ready"], result["blockers"]
    assert len(result["workspaces"][0]["sessions"]) == 1


def test_manifest_v1_rejects_registered_session_symlink_escape(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "session.json"
    outside.write_text(json.dumps({"schema_version": 1}))
    chat = _chat()
    _write_registry(root, [chat])
    (root / "sessions").mkdir()
    (root / "sessions" / "user_session.json").symlink_to(outside)

    result = _report(root)

    assert not result["ready"]
    assert result["blockers"]


def test_manifest_v1_ignores_manifest_session_not_registered_in_chats(
    tmp_path,
):
    root = tmp_path / "workspace"
    (root / "sessions").mkdir(parents=True)
    (root / "dialog").mkdir()
    chat = _chat()
    _write_registry(root, [chat])
    _write_session(root)
    _write_session(root, "other.json", orphan=True)
    data = {
        "source_binding_storage": "manifest-v1",
        "source_isolation": True,
        "workspaces": [
            {
                **_mapping(root),
                "session_paths": [
                    {
                        "user_id": "other",
                        "channel": "console",
                        "session_id": "orphan",
                        "path": "sessions/other.json",
                    },
                ],
            },
        ],
        "tenants": [],
        "shares": [],
        "services": [],
        "fingerprints": [],
    }

    result = inventory_discovery(data)

    assert result["ready"], result["blockers"]
    assert len(result["workspaces"][0]["sessions"]) == 1
