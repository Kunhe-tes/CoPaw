# -*- coding: utf-8 -*-
"""Business trees never enter conversation inventory."""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.migration.inventory import (
    WorkspaceMapping,
    _source_files,
)
from swe.app.conversation_storage.migration.source_inputs import (
    safe_input_entries,
    workspace_files,
)


def _mapping(root, **options):
    return WorkspaceMapping(
        WorkspaceScope("tenant", "source", "agent", service_unit_id="service"),
        root,
        **options,
    )


def test_unrelated_large_attachment_and_code_are_never_enumerated(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "chats.json").write_text("{}")
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    with (attachments / "large.bin").open("wb") as stream:
        stream.truncate(20 * 1024 * 1024)
    code = tmp_path / "code"
    (code / "deep" / "tree").mkdir(parents=True)
    (code / "external").symlink_to("/unrelated-missing-target")
    original = Path.iterdir

    def selected_only(path):
        if (
            path == attachments
            or path == code
            or attachments in path.parents
            or code in path.parents
        ):
            pytest.fail("enumerated unrelated business tree")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", selected_only)
    (tmp_path / "chats.json").chmod(0o444)
    tmp_path.chmod(0o555)
    try:
        assert _source_files(_mapping(tmp_path)) == [tmp_path / "chats.json"]
    finally:
        tmp_path.chmod(0o755)


def test_writable_workspace_directories_are_allowed_for_migration(tmp_path):
    chats = tmp_path / "chats.json"
    chats.write_text("{}")
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    session = sessions / "session.json"
    session.write_text("{}")
    dialog = tmp_path / "dialog"
    dialog.mkdir()
    archive = dialog / "chat" / "archive.json"
    archive.parent.mkdir()
    archive.write_text("{}")

    for path in (chats, session, archive):
        path.chmod(0o444)
    for path in (tmp_path, sessions, dialog, archive.parent):
        path.chmod(0o755)

    assert set(
        _source_files(
            _mapping(tmp_path),
            ["chats.json", "sessions", "dialog"],
            chats_authoritative=True,
        ),
    ) == {chats, session, archive}


def test_writable_conversation_files_are_allowed(tmp_path):
    chats = tmp_path / "chats.json"
    chats.write_text("{}")

    assert _source_files(
        _mapping(tmp_path),
        ["chats.json"],
        chats_authoritative=True,
    ) == [chats]


def test_override_includes_only_its_session_and_associated_ledger(
    tmp_path,
    monkeypatch,
):
    parent = tmp_path / "reviewed"
    generation = str(uuid4())
    ledger = parent / ".turn-ledger" / generation
    ledger.mkdir(parents=True)
    (ledger / "metadata.json").write_text("{}")
    state = {"schema_version": 3, "session_generation": generation}
    (parent / "session.json").write_text(json.dumps(state))
    unrelated = parent / "other"
    unrelated.mkdir()
    (unrelated / "code.py").write_text("business data")
    other_ledger = parent / ".turn-ledger" / str(uuid4())
    other_ledger.mkdir()
    original = Path.iterdir

    def selected_only(path):
        if path in (parent, parent / ".turn-ledger", unrelated, other_ledger):
            pytest.fail("enumerated override parent or unrelated generation")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", selected_only)
    mapping = _mapping(
        tmp_path,
        session_paths={
            ("user", "console", "session"): "reviewed/session.json",
        },
    )
    assert set(workspace_files(mapping)) == {
        parent / "session.json",
        ledger / "metadata.json",
    }


@pytest.mark.parametrize("relative", ["../outside.json", "/outside.json", "."])
def test_explicit_inputs_reject_invalid_roots(tmp_path, relative):
    with pytest.raises(ValueError, match="relative to trusted workspace"):
        safe_input_entries(tmp_path, [relative])


@pytest.mark.parametrize(
    "kind",
    ["symlink", "broken_symlink", "fifo", "parent_symlink"],
)
def test_selected_conversation_inputs_reject_unsafe_objects(tmp_path, kind):
    sessions = tmp_path / "sessions"
    if kind == "parent_symlink":
        destination = tmp_path / "business"
        destination.mkdir()
        sessions.symlink_to(destination, target_is_directory=True)
    else:
        sessions.mkdir()
        path = sessions / "unsafe.json"
        if kind == "fifo":
            os.mkfifo(path)
        else:
            path.symlink_to(
                tmp_path / ("chats.json" if kind == "symlink" else "missing"),
            )
            (tmp_path / "chats.json").write_text("{}")
    with pytest.raises(ValueError, match="symlink|unsupported filesystem"):
        safe_input_entries(tmp_path, ["sessions"])
