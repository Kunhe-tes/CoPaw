# -*- coding: utf-8 -*-
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from swe.cli.conversation_storage_cmd import conversation_storage_group
from swe.app.conversation_storage import runtime


def test_prepare_defaults_to_metadata_and_preview_is_read_only(
    tmp_path,
    monkeypatch,
):
    from swe.database import config

    monkeypatch.setattr(
        config,
        "get_database_config",
        lambda: SimpleNamespace(database="test"),
    )
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "chats.json").write_text('{"version": 1, "chats": []}')
    mapping = tmp_path / "workspaces.json"
    mapping.write_text(
        json.dumps(
            [
                {
                    "root": str(root),
                    "scope": ["svc", "tenant", "source", "agent"],
                },
            ],
        ),
    )
    manifest = tmp_path / "manifest.json"
    runner = CliRunner()
    result = runner.invoke(
        conversation_storage_group,
        ["prepare", "--workspaces", str(mapping), "--manifest", str(manifest)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(manifest.read_text())["mode"] == "mysql-metadata"
    result = runner.invoke(
        conversation_storage_group,
        ["migrate", "--manifest", str(manifest), "--full-audit"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "preview"


def test_rejects_bundle_mode_and_manifest(tmp_path, monkeypatch):
    from swe.database import config

    monkeypatch.setattr(
        config,
        "get_database_config",
        lambda: SimpleNamespace(database="test"),
    )
    runner = CliRunner()
    result = runner.invoke(
        conversation_storage_group,
        [
            "prepare",
            "--mode",
            "bundle",
            "--workspaces",
            __file__,
            "--manifest",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code != 0
    manifest = tmp_path / "old.json"
    manifest.write_text('{"mode":"bundle","version":1}')
    result = runner.invoke(
        conversation_storage_group,
        ["migrate", "--manifest", str(manifest)],
    )
    assert result.exit_code != 0
    assert "invalid MySQL metadata manifest" in result.output


@pytest.mark.asyncio
async def test_runtime_rejects_removed_authority(monkeypatch):
    monkeypatch.setenv(runtime.AUTHORITY_ENV, "mysql")
    with pytest.raises(ValueError, match="authority"):
        await runtime.configure_runtime(
            SimpleNamespace(is_connected=True, fetch_all=AsyncMock()),
        )


@pytest.mark.parametrize("document", ["[]", "null", '"text"'])
@pytest.mark.parametrize("command", ["migrate", "export-metadata"])
def test_non_object_manifest_has_a_clear_error(
    tmp_path,
    monkeypatch,
    document,
    command,
):
    from swe.database import config

    monkeypatch.setattr(
        config,
        "get_database_config",
        lambda: SimpleNamespace(database="test"),
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(document)
    args = [command, "--manifest", str(manifest)]
    if command == "export-metadata":
        args += ["--destination", str(tmp_path / "export")]
    result = CliRunner().invoke(conversation_storage_group, args)
    assert result.exit_code != 0
    assert "invalid MySQL metadata manifest" in result.output
    assert isinstance(result.exception, SystemExit)


def test_partial_migration_exits_with_code_two(tmp_path, monkeypatch):
    from swe.cli import conversation_storage_workflow_cmd as workflow

    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    monkeypatch.setattr(
        workflow,
        "_execute_metadata",
        AsyncMock(return_value={"status": "partial_success"}),
    )
    result = CliRunner().invoke(
        conversation_storage_group,
        ["migrate", "--manifest", str(manifest)],
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["status"] == "partial_success"
