# -*- coding: utf-8 -*-
"""Regression tests for the workspace-path normalization script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_script_module():
    script_path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "normalize_workspace_paths.py"
    )
    spec = importlib.util.spec_from_file_location(
        "normalize_workspace_paths",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_normalize_workspace_paths_updates_templates_and_tenants(
    tmp_path: Path,
) -> None:
    module = _load_script_module()
    working_dir = tmp_path / "working"
    tenant_dirs = (
        working_dir / "default",
        working_dir / "default_RMASSIST",
        working_dir / "tenant-a",
    )
    for tenant_dir in tenant_dirs:
        default_workspace = tenant_dir / "workspaces" / "default"
        alpha_workspace = tenant_dir / "workspaces" / "alpha"
        _write_json(
            tenant_dir / "config.json",
            {
                "agents": {
                    "profiles": {
                        "default": {"workspace_dir": "/old/default"},
                        "alpha": {"workspace_dir": "/old/alpha"},
                    },
                },
            },
        )
        _write_json(
            default_workspace / "agent.json",
            {"id": "default", "workspace_dir": "/old/default"},
        )
        _write_json(
            alpha_workspace / "agent.json",
            {"id": "alpha", "workspace_dir": "/old/alpha"},
        )

    result = module.normalize_workspace_paths(working_dir, apply=True)

    assert result.scanned_tenant_dirs == tenant_dirs
    assert len(result.changed_files) == 9
    for tenant_dir in tenant_dirs:
        config = json.loads((tenant_dir / "config.json").read_text())
        assert config["agents"]["profiles"]["default"]["workspace_dir"] == str(
            tenant_dir / "workspaces" / "default",
        )
        assert config["agents"]["profiles"]["alpha"]["workspace_dir"] == str(
            tenant_dir / "workspaces" / "alpha",
        )
        for agent_id in ("default", "alpha"):
            agent = json.loads(
                (
                    tenant_dir / "workspaces" / agent_id / "agent.json"
                ).read_text(),
            )
            assert agent["workspace_dir"] == str(
                tenant_dir / "workspaces" / agent_id,
            )


def test_normalize_workspace_paths_dry_run_and_invalid_json_are_non_mutating(
    tmp_path: Path,
) -> None:
    module = _load_script_module()
    working_dir = tmp_path / "working"
    tenant_dir = working_dir / "default_RMASSIST"
    config_path = tenant_dir / "config.json"
    agent_path = tenant_dir / "workspaces" / "default" / "agent.json"
    _write_json(
        config_path,
        {"agents": {"profiles": {"default": {"workspace_dir": "/old"}}}},
    )
    agent_path.parent.mkdir(parents=True)
    agent_path.write_text("{broken", encoding="utf-8")

    result = module.normalize_workspace_paths(working_dir)

    assert result.changed_files == (config_path,)
    assert result.invalid_json_files == (agent_path,)
    assert (
        json.loads(config_path.read_text())["agents"]["profiles"]["default"][
            "workspace_dir"
        ]
        == "/old"
    )
    assert agent_path.read_text() == "{broken"
    assert not list(working_dir.rglob("*.bak"))
