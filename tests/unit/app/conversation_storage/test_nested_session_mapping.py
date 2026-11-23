# -*- coding: utf-8 -*-
"""Nested Session candidates require reviewed identities without ledger guesses."""

import json

import pytest

from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.migration.inventory import (
    WorkspaceMapping,
    inventory,
)
from swe.app.runner.session import SafeJSONSession
from tests.unit.app.conversation_storage.test_migration_inventory import (
    boundary,
    make_readonly,
)


def _mapping(root, *, session_paths=None):
    return WorkspaceMapping(
        WorkspaceScope("tenant", "source", "agent", service_unit_id="service"),
        root,
        session_paths=session_paths or {},
    )


def _root(tmp_path):
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "chats.json").write_text(json.dumps({"chats": []}))
    return root


async def test_chat_authoritative_inventory_keeps_zhaohu_active_pointer(
    tmp_path,
):
    from swe.app.conversation_storage.migration.inventory import (
        _workspace,
        verify_active_session_pointers,
    )
    from swe.app.conversation_storage.migration.source_inputs import (
        SourceInputInvalid,
    )

    root = _root(tmp_path)
    session = SafeJSONSession(str(root / "sessions"))
    sid = "zhaohu:active:alice"
    await session.update_session_state(
        sid,
        "active_session_id",
        "zhaohu:callback:alice:4",
        user_id="alice",
    )
    path = next((root / "sessions").glob("*.json"))
    report = {"blockers": [], "files": []}
    item = _workspace(
        _mapping(
            root,
            session_paths={
                ("alice", "console", sid): str(path.relative_to(root)),
            },
        ),
        report,
        0,
        chats_authoritative=True,
    )
    assert report["blockers"] == []
    (pointer,) = item["sessions"]
    assert pointer["identity"][-3:] == ["alice", "console", sid]
    assert (
        pointer["legacy"]["state"]["active_session_id"]
        == "zhaohu:callback:alice:4"
    )
    assert pointer["path"] in {entry["path"] for entry in report["files"]}
    captured = {"workspaces": [item]}
    verify_active_session_pointers(captured)
    await session.update_session_state(
        sid,
        "active_session_id",
        "zhaohu:callback:alice:5",
        user_id="alice",
    )
    with pytest.raises(SourceInputInvalid, match="changed during migration"):
        verify_active_session_pointers(captured)


@pytest.mark.parametrize(
    "relative",
    [
        "sessions/nested/orphan.json",
        "sessions/nested/.turn-ledger/unknown/metadata.json",
        "sessions/nested/.turn-ledger/unknown/references/turn.json",
    ],
)
def test_unmapped_nested_session_json_is_blocked(tmp_path, relative):
    root = _root(tmp_path)
    path = root / relative
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema_version": 2}))
    make_readonly(root)
    try:
        report = inventory([_mapping(root)], boundary())
        assert not report["ready"]
        assert any(
            item["code"] == "unmapped_session" and item["detail"] == relative
            for item in report["blockers"]
        )
        assert relative in {item["path"] for item in report["files"]}
    finally:
        for parent in path.parents:
            if parent == root.parent:
                break
            parent.chmod(0o755)


@pytest.mark.parametrize("stray_generation", [False, True])
async def test_mapped_nested_session_keeps_associated_ledger_json(
    tmp_path,
    stray_generation,
):
    root = _root(tmp_path)
    nested = root / "sessions/nested"
    session = SafeJSONSession(str(nested))
    await session.save_merged_state(
        "selected",
        state={
            "turn_states": {
                "question": {
                    "status": "completed",
                    "message": {"id": "question"},
                },
            },
        },
    )
    await session.migrate_terminal_turns("selected", dry_run=False)
    if stray_generation:
        stray = nested / ".turn-ledger/unmapped-generation/metadata.json"
        stray.parent.mkdir(parents=True)
        stray.write_text("{}")
    make_readonly(root)
    try:
        mapping = _mapping(
            root,
            session_paths={
                (
                    "user",
                    "console",
                    "selected",
                ): "sessions/nested/selected.json",
            },
        )
        report = inventory([mapping], boundary())
        assert report["ready"] is (not stray_generation), report["blockers"]
        if stray_generation:
            assert any(
                item["code"] == "unmapped_session"
                and item["detail"].endswith(
                    "unmapped-generation/metadata.json",
                )
                for item in report["blockers"]
            )
        assert len(report["workspaces"][0]["sessions"]) == 1
        assert (
            "question"
            in report["workspaces"][0]["sessions"][0]["legacy"]["state"][
                "turn_states"
            ]
        )
        assert any(
            "/.turn-ledger/" in item["path"] for item in report["files"]
        )
    finally:
        for path in root.rglob("*"):
            if path.is_dir():
                path.chmod(0o755)
        root.chmod(0o755)
