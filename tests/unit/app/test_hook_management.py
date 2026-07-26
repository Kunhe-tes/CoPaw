# -*- coding: utf-8 -*-
"""Default Agent Profile Hook-management service tests."""

import json
from pathlib import Path

import pytest

from swe.app.hook_management import (
    HookAuditActor,
    HookManagementConflict,
    HookManagementService,
    HookManagementValidationError,
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
