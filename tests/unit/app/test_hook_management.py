# -*- coding: utf-8 -*-
"""Default Agent Profile Hook-management service tests."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from swe.app import hook_management
from swe.agents.hook_runtime.models import HookContext, HookHandlerResult
from swe.app.hook_management import (
    HookAuditActor,
    HookManagementConflict,
    HookManagementService,
    HookManagementValidationError,
    UploadFilePayload,
)


def _write_default_agent(workspace_dir: Path) -> None:
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "agent.json").write_text(
        json.dumps({"id": "default", "name": "Default Agent"}),
        encoding="utf-8",
    )


def _actor() -> HookAuditActor:
    return HookAuditActor(user_id="user-a", tenant_id="tenant-a")


def _duplicate_handler_ids() -> dict[str, object]:
    return {
        "enabled": True,
        "events": {
            "PreToolUse": [
                {
                    "id": "shells",
                    "hooks": [
                        {
                            "id": "duplicate",
                            "type": "command",
                            "argv": ["echo"],
                        },
                    ],
                },
                {
                    "id": "network",
                    "hooks": [
                        {
                            "id": "duplicate",
                            "type": "command",
                            "argv": ["printf"],
                        },
                    ],
                },
            ],
        },
    }


def test_save_rejects_stale_revision(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspaces" / "default"
    _write_default_agent(workspace_dir)
    service = HookManagementService(workspace_dir, tenant_id="tenant-a")
    original = service.get_configuration()

    service.save_configuration(
        hooks={"enabled": True, "events": {}},
        expected_revision=original.revision,
        actor=_actor(),
    )

    with pytest.raises(HookManagementConflict):
        service.save_configuration(
            hooks={"enabled": False, "events": {}},
            expected_revision=original.revision,
            actor=_actor(),
        )


def test_save_rejects_duplicate_handler_ids_across_matcher_groups(
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspaces" / "default"
    _write_default_agent(workspace_dir)
    service = HookManagementService(workspace_dir, tenant_id="tenant-a")

    with pytest.raises(
        HookManagementValidationError,
        match="duplicate handler id",
    ):
        service.save_configuration(
            hooks=_duplicate_handler_ids(),
            expected_revision=service.get_configuration().revision,
            actor=_actor(),
        )


def test_save_rejects_duplicate_matcher_group_ids_across_events(
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspaces" / "default"
    _write_default_agent(workspace_dir)
    service = HookManagementService(workspace_dir, tenant_id="tenant-a")
    hooks = {
        "enabled": True,
        "events": {
            "SessionStart": [{"id": "duplicate-group", "hooks": []}],
            "Stop": [{"id": "duplicate-group", "hooks": []}],
        },
    }

    with pytest.raises(
        HookManagementValidationError,
        match="duplicate matcher group id",
    ):
        service.save_configuration(
            hooks=hooks,
            expected_revision=service.get_configuration().revision,
            actor=_actor(),
        )


def test_save_preserves_non_hook_agent_configuration(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspaces" / "default"
    _write_default_agent(workspace_dir)
    agent_path = workspace_dir / "agent.json"
    agent_data = json.loads(agent_path.read_text(encoding="utf-8"))
    agent_data["language"] = "zh"
    agent_path.write_text(json.dumps(agent_data), encoding="utf-8")
    service = HookManagementService(workspace_dir, tenant_id="tenant-a")

    service.save_configuration(
        hooks={"enabled": True, "events": {}},
        expected_revision=service.get_configuration().revision,
        actor=_actor(),
    )

    saved = json.loads(agent_path.read_text(encoding="utf-8"))
    assert saved["language"] == "zh"
    assert saved["hooks"] == {"enabled": True, "events": {}}


def test_batch_keeps_valid_file_when_another_file_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspaces" / "default"
    _write_default_agent(workspace_dir)
    monkeypatch.setattr(
        hook_management,
        "scan_skill_directory",
        lambda *args, **kwargs: None,
    )
    service = HookManagementService(workspace_dir, tenant_id="tenant-a")

    result = service.upload_scripts(
        files=[
            UploadFilePayload("guard.py", b"print('ok')"),
            UploadFilePayload("bad.exe", b"MZ"),
        ],
        overwrite_names=set(),
        actor=_actor(),
    )

    assert result.accepted_names == ["guard.py"]
    assert result.failed[0].filename == "bad.exe"
    assert (workspace_dir / "hooks" / "scripts" / "guard.py").read_bytes() == (
        b"print('ok')"
    )


def test_list_scripts_returns_controlled_library_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspaces" / "default"
    _write_default_agent(workspace_dir)
    monkeypatch.setattr(
        hook_management,
        "scan_skill_directory",
        lambda *args, **kwargs: None,
    )
    service = HookManagementService(workspace_dir, tenant_id="tenant-a")
    service.upload_scripts(
        files=[UploadFilePayload("guard.py", b"print('ok')")],
        overwrite_names=set(),
        actor=_actor(),
    )

    scripts = service.list_scripts()

    assert scripts[0]["filename"] == "guard.py"
    assert scripts[0]["size"] == len(b"print('ok')")
    assert len(scripts[0]["sha256"]) == 64


@pytest.mark.asyncio
async def test_manual_test_runs_one_draft_handler_without_persisting_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspaces" / "default"
    _write_default_agent(workspace_dir)
    original_config = (workspace_dir / "agent.json").read_text(
        encoding="utf-8",
    )
    execute = AsyncMock(
        return_value=HookHandlerResult(
            handler_id="check-command",
            order=0,
            reason="completed",
        ),
    )
    monkeypatch.setattr(hook_management, "execute_handler", execute)
    service = HookManagementService(workspace_dir, tenant_id="tenant-a")

    result = await service.manual_test(
        handler={"id": "check-command", "type": "command", "argv": ["echo"]},
        context=HookContext(
            session_id="test-session",
            transcript_path="",
            cwd=str(workspace_dir),
            hook_event_name="PreToolUse",
            tenant_id="tenant-a",
            effective_tenant_id="tenant-a",
            user_id="user-a",
            agent_id="default",
            channel="test",
            workspace_dir=str(workspace_dir),
        ),
        actor=_actor(),
    )

    execute.assert_awaited_once()
    assert result.redacted_summary["reason"] == "completed"
    assert (workspace_dir / "agent.json").read_text(
        encoding="utf-8",
    ) == original_config
