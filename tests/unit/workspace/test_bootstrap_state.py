# -*- coding: utf-8 -*-
"""Strict readiness and persistence tests for tenant bootstrap artifacts."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "src"))

from swe.app.workspace.bootstrap_state import (
    inspect_bootstrap_readiness,
    move_to_recovery_backup,
    write_bootstrap_json,
)
from swe.config.config import (
    AgentProfileConfig,
    AgentProfileRef,
    AgentsConfig,
    Config,
)


@pytest.fixture
def good_tenant(tmp_path: Path) -> Path:
    tenant_dir = tmp_path / "tenant-a"
    workspace_dir = tenant_dir / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)
    config = Config(
        agents=AgentsConfig(
            active_agent="default",
            profiles={
                "default": AgentProfileRef(
                    id="default",
                    workspace_dir=str(workspace_dir),
                    enabled=True,
                ),
            },
        ),
    )
    (tenant_dir / "config.json").write_text(
        json.dumps(config.model_dump(mode="json")),
        encoding="utf-8",
    )
    agent = AgentProfileConfig(
        id="default",
        name="Default Agent",
        workspace_dir=str(workspace_dir),
    )
    (workspace_dir / "agent.json").write_text(
        json.dumps(agent.model_dump(mode="json")),
        encoding="utf-8",
    )
    for file_name in (
        "AGENTS.md",
        "HEARTBEAT.md",
        "MEMORY.md",
        "PROFILE.md",
        "SOUL.md",
    ):
        (workspace_dir / file_name).write_text(
            "# required\n",
            encoding="utf-8",
        )
    for directory in ("sessions", "memory", "skills"):
        (workspace_dir / directory).mkdir()
    for file_name, payload in (
        ("chats.json", {"version": 1, "chats": []}),
        ("jobs.json", {"version": 1, "jobs": []}),
        ("token_usage.json", {}),
        ("skill.json", {"version": 1, "skills": {}}),
    ):
        (workspace_dir / file_name).write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
    skill_pool = tenant_dir / "skill_pool"
    skill_pool.mkdir()
    (skill_pool / "skill.json").write_text(
        json.dumps({"version": 1, "skills": {}}),
        encoding="utf-8",
    )
    return tenant_dir


def test_readiness_rejects_corrupt_root_config(good_tenant: Path) -> None:
    config_path = good_tenant / "config.json"
    config_path.write_text("{broken", encoding="utf-8")

    readiness = inspect_bootstrap_readiness(good_tenant)

    assert not readiness.ready
    assert readiness.invalid_json_paths == (config_path,)


def test_readiness_rejects_disabled_default_profile(good_tenant: Path) -> None:
    config_path = good_tenant / "config.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["agents"]["profiles"]["default"]["enabled"] = False
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    readiness = inspect_bootstrap_readiness(good_tenant)

    assert not readiness.ready
    assert readiness.invalid_json_paths == (config_path,)


def test_readiness_allows_a_non_default_active_agent(
    good_tenant: Path,
) -> None:
    config_path = good_tenant / "config.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["agents"]["active_agent"] = "alpha"
    payload["agents"]["profiles"]["alpha"] = {
        "id": "alpha",
        "workspace_dir": str(good_tenant / "workspaces" / "alpha"),
        "enabled": True,
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    readiness = inspect_bootstrap_readiness(good_tenant)

    assert readiness.ready


def test_readiness_ignores_skill_manifests_and_directories(
    good_tenant: Path,
) -> None:
    workspace_dir = good_tenant / "workspaces" / "default"
    (good_tenant / "skill_pool" / "skill.json").write_text(
        "{broken",
        encoding="utf-8",
    )
    (workspace_dir / "skill.json").write_text("{broken", encoding="utf-8")
    (workspace_dir / "skills").rmdir()

    readiness = inspect_bootstrap_readiness(good_tenant)

    assert readiness.ready


def test_ready_marker_does_not_hide_damaged_agent(good_tenant: Path) -> None:
    agent_path = good_tenant / "workspaces" / "default" / "agent.json"
    agent_path.write_text("{broken", encoding="utf-8")
    (good_tenant / ".bootstrap.ready").write_text("ready", encoding="utf-8")

    readiness = inspect_bootstrap_readiness(good_tenant)

    assert not readiness.ready
    assert readiness.invalid_json_paths == (agent_path,)


def test_atomic_write_fsyncs_and_cleans_its_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fsync_calls: list[int] = []
    monkeypatch.setattr(os, "fsync", fsync_calls.append)
    path = tmp_path / "config.json"

    write_bootstrap_json(path, {"version": 1})

    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1}
    assert len(fsync_calls) == 2
    assert list(tmp_path.glob(".config.json.*.tmp")) == []


def test_backup_moves_only_the_explicit_invalid_file(tmp_path: Path) -> None:
    invalid_path = tmp_path / "config.json"
    unrelated_tmp = tmp_path / ".keep.tmp"
    invalid_path.write_text("{broken", encoding="utf-8")
    unrelated_tmp.write_text("preserve", encoding="utf-8")

    backup_path = move_to_recovery_backup(invalid_path)

    assert backup_path.suffix == ".bak"
    assert backup_path.read_text(encoding="utf-8") == "{broken"
    assert not invalid_path.exists()
    assert unrelated_tmp.exists()
