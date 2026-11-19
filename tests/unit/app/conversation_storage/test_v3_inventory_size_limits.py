# -*- coding: utf-8 -*-
"""Nonconversation files stay outside workspace discovery."""

import os

import pytest

from swe.app.conversation_storage.migration import inventory_v3


def workspace(root):
    return {
        "root": str(root),
        "service_unit_id": "svc",
        "tenant_id": "tenant",
        "source_id": "source",
        "agent_id": "agent",
        "position": "workspace-position",
    }


@pytest.mark.parametrize("size", [0, 16, 17])
def test_native_file_outside_conversation_inputs_is_ignored(tmp_path, size):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "native.bin").write_bytes(b"x" * size)
    result = inventory_v3.inventory_discovery(
        {"workspaces": [workspace(root)], "shares": [], "fingerprints": []},
        workspace_offset=41,
    )
    assert result["ready"]
    assert result["files"] == []
    assert result["workspaces"][0]["sessions"] == []
    assert result["workspaces"][0]["chats"] == []
    assert result["blockers"] == []


def test_empty_workspace_remains_valid(tmp_path):
    result = inventory_v3.inventory_discovery(
        {
            "workspaces": [workspace(tmp_path)],
            "shares": [],
            "fingerprints": [],
        },
    )
    assert result["ready"]
    assert result["files"] == result["blockers"] == []


@pytest.mark.parametrize("kind", ["fifo", "directory"])
def test_share_snapshot_without_cutoff_skips_nonregular_path(
    tmp_path,
    monkeypatch,
    kind,
):
    path = tmp_path / "snapshot.json"
    if kind == "fifo":
        os.mkfifo(path)
    else:
        path.mkdir()

    def unexpected_read(*_args, **_kwargs):
        pytest.fail("unsafe share snapshot must not be read")

    monkeypatch.setattr(type(path), "read_bytes", unexpected_read)
    with pytest.raises(ValueError, match="symlink|unsupported|regular file"):
        inventory_v3.inventory_discovery(
            {
                "workspaces": [],
                "shares": [
                    {"snapshot_path": str(path), "position": "share"},
                ],
                "fingerprints": [],
            },
        )
