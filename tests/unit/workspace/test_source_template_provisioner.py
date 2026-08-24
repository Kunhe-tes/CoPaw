# -*- coding: utf-8 -*-
"""Tests for explicit, idempotent source-template provisioning."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "src"))

from swe.app.workspace.bootstrap_state import SourceTemplateUnavailable
from swe.app.workspace.source_template_provisioner import (
    SourceTemplateProvisioner,
    inspect_source_template_readiness,
)
from swe.app.workspace.tenant_initializer import TenantInitializer
from swe.config.config import (
    AgentProfileConfig,
    AgentProfileRef,
    AgentsConfig,
    Config,
)


def _create_ready_template(base_dir: Path, name: str = "default") -> Path:
    tenant_dir = base_dir / name
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


@pytest.fixture
def ready_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import swe.app.workspace.source_template_provisioner as provisioner_module

    secret_dir = tmp_path / "secrets"
    monkeypatch.setattr(provisioner_module, "SECRET_DIR", secret_dir)
    (secret_dir / "default" / "providers").mkdir(parents=True)
    (secret_dir / "default" / "providers" / "model.json").write_text(
        "{}",
        encoding="utf-8",
    )
    return _create_ready_template(tmp_path)


@pytest.mark.asyncio
async def test_provisioner_creates_ready_source_template(
    ready_default: Path,
) -> None:
    provisioner = SourceTemplateProvisioner(ready_default.parent)

    result = await provisioner.ensure("ruice")

    assert result.status == "created"
    readiness = inspect_source_template_readiness(
        ready_default.parent,
        "ruice",
    )
    assert readiness.ready
    assert (
        ready_default.parent
        / "default_ruice"
        / "workspaces"
        / "default"
        / "agent.json"
    ).is_file()


@pytest.mark.asyncio
async def test_provisioner_keeps_ready_source_template_unchanged(
    ready_default: Path,
) -> None:
    provisioner = SourceTemplateProvisioner(ready_default.parent)
    await provisioner.ensure("ruice")
    profile_path = (
        ready_default.parent
        / "default_ruice"
        / "workspaces"
        / "default"
        / "PROFILE.md"
    )
    profile_path.write_text("# customized\n", encoding="utf-8")

    result = await provisioner.ensure("ruice")

    assert result.status == "ready"
    assert profile_path.read_text(encoding="utf-8") == "# customized\n"


@pytest.mark.asyncio
async def test_provisioner_repairs_incomplete_source_template(
    ready_default: Path,
) -> None:
    target = ready_default.parent / "default_ruice"
    target.mkdir()
    (target / "config.json").write_text("{broken", encoding="utf-8")

    result = await SourceTemplateProvisioner(ready_default.parent).ensure(
        "ruice",
    )

    assert result.status == "repaired"
    assert inspect_source_template_readiness(
        ready_default.parent,
        "ruice",
    ).ready
    assert list(ready_default.parent.glob("default_ruice.*.bak")) == []


@pytest.mark.asyncio
async def test_provisioner_fails_closed_when_global_default_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import swe.app.workspace.source_template_provisioner as provisioner_module

    monkeypatch.setattr(provisioner_module, "SECRET_DIR", tmp_path / "secrets")
    default_dir = tmp_path / "default"
    default_dir.mkdir()
    (default_dir / "config.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(SourceTemplateUnavailable):
        await SourceTemplateProvisioner(tmp_path).ensure("ruice")

    assert not (tmp_path / "default_ruice").exists()


def test_initializer_never_creates_missing_source_template(
    tmp_path: Path,
) -> None:
    initializer = TenantInitializer(tmp_path, "tenant-a", source_id="ruice")

    assert initializer.template_name == "default_ruice"
    assert not (tmp_path / "default_ruice").exists()
