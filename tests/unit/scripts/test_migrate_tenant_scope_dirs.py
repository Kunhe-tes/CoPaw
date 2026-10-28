# -*- coding: utf-8 -*-
"""租户目录迁移脚本的回归测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_script_module():
    """按文件路径加载迁移脚本，避免依赖 scripts 成为 Python 包。"""
    script_path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "migrate_tenant_scope_dirs.py"
    )
    spec = importlib.util.spec_from_file_location(
        "migrate_tenant_scope_dirs",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seed_working_dir(base_dir: Path, tenant_id: str) -> Path:
    """创建带路径引用的旧工作目录，模拟历史租户数据。"""
    tenant_dir = base_dir / tenant_id
    workspace_dir = tenant_dir / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)
    (tenant_dir / "config.json").write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": {
                        "default": {
                            "workspace_dir": str(workspace_dir),
                        },
                    },
                },
            },
        ),
        encoding="utf-8",
    )
    (workspace_dir / "agent.json").write_text(
        json.dumps({"workspace_dir": str(workspace_dir)}),
        encoding="utf-8",
    )
    return tenant_dir


def test_migrate_tenant_scope_dirs_moves_both_roots_and_rewrites_paths(
    tmp_path: Path,
) -> None:
    """迁移后工作目录和密钥目录都应切到 canonical scope。"""
    module = _load_script_module()
    working_dir = tmp_path / ".swe"
    secret_dir = tmp_path / ".swe.secret"
    old_working = _seed_working_dir(working_dir, "tenant-a")
    old_secret = secret_dir / "tenant-a"
    (old_secret / "providers").mkdir(parents=True)

    result = module.migrate_tenant_scope_dirs(
        tenant_id="tenant-a",
        source_id="source-a",
        working_dir=working_dir,
        secret_dir=secret_dir,
    )

    expected_scope = module.encode_scope_id("tenant-a", "source-a")
    new_working = working_dir / expected_scope
    new_secret = secret_dir / expected_scope
    assert result.scope_id == expected_scope
    assert not old_working.exists()
    assert not old_secret.exists()
    assert new_working.exists()
    assert new_secret.exists()

    config = json.loads((new_working / "config.json").read_text())
    agent = json.loads(
        (new_working / "workspaces" / "default" / "agent.json").read_text(),
    )
    expected_workspace = str(new_working / "workspaces" / "default")
    assert config["agents"]["profiles"]["default"]["workspace_dir"] == (
        expected_workspace
    )
    assert agent["workspace_dir"] == expected_workspace


def test_migrate_tenant_scope_dirs_refuses_existing_target(
    tmp_path: Path,
) -> None:
    """历史测试名；迁移会删除已存在的目标目录并覆盖其数据。"""
    module = _load_script_module()
    working_dir = tmp_path / ".swe"
    secret_dir = tmp_path / ".swe.secret"
    old_working = _seed_working_dir(working_dir, "tenant-a")
    expected_scope = module.encode_scope_id("tenant-a", "source-a")
    target = working_dir / expected_scope
    target.mkdir(parents=True)
    (target / "old-target.txt").write_text("will be removed")
    old_secret = secret_dir / "tenant-a"
    old_secret.mkdir(parents=True)
    (old_secret / "source.txt").write_text("source secret")
    target_secret = secret_dir / expected_scope
    target_secret.mkdir(parents=True)
    (target_secret / "old-target.txt").write_text("will be removed")

    module.migrate_tenant_scope_dirs(
        tenant_id="tenant-a",
        source_id="source-a",
        working_dir=working_dir,
        secret_dir=secret_dir,
    )

    assert not old_working.exists()
    assert (target / "config.json").exists()
    assert not (target / "old-target.txt").exists()
    assert (target_secret / "source.txt").read_text() == "source secret"
    assert not (target_secret / "old-target.txt").exists()


def test_migrate_tenant_scope_dirs_dry_run_keeps_files_in_place(
    tmp_path: Path,
) -> None:
    """dry-run 只能返回计划，不能修改现有目录。"""
    module = _load_script_module()
    working_dir = tmp_path / ".swe"
    secret_dir = tmp_path / ".swe.secret"
    old_working = _seed_working_dir(working_dir, "tenant-a")
    old_secret = secret_dir / "tenant-a"
    old_secret.mkdir(parents=True)

    result = module.migrate_tenant_scope_dirs(
        tenant_id="tenant-a",
        source_id="source-a",
        working_dir=working_dir,
        secret_dir=secret_dir,
        dry_run=True,
    )

    expected_scope = module.encode_scope_id("tenant-a", "source-a")
    assert result.scope_id == expected_scope
    assert old_working.exists()
    assert old_secret.exists()
    assert not (working_dir / expected_scope).exists()
    assert not (secret_dir / expected_scope).exists()


def test_parse_tenant_ids_supports_comma_separated_batch_input() -> None:
    """批量参数应支持逗号分隔并忽略两侧空白。"""
    module = _load_script_module()

    assert module.parse_tenant_ids("tenant-a, tenant-b,tenant-c") == (
        "tenant-a",
        "tenant-b",
        "tenant-c",
    )


def test_migrate_tenant_scope_dirs_batch_moves_all_tenants(
    tmp_path: Path,
) -> None:
    """批量迁移应复用同一 source 并依次迁移所有租户。"""
    module = _load_script_module()
    working_dir = tmp_path / ".swe"
    secret_dir = tmp_path / ".swe.secret"
    for tenant_id in ("tenant-a", "tenant-b"):
        _seed_working_dir(working_dir, tenant_id)
        (secret_dir / tenant_id / "providers").mkdir(parents=True)

    results = module.migrate_tenant_scope_dirs_batch(
        tenant_ids=("tenant-a", "tenant-b"),
        source_id="source-a",
        working_dir=working_dir,
        secret_dir=secret_dir,
    )

    assert tuple(result.scope_id for result in results) == (
        module.encode_scope_id("tenant-a", "source-a"),
        module.encode_scope_id("tenant-b", "source-a"),
    )
    for tenant_id, result in zip(("tenant-a", "tenant-b"), results):
        assert not (working_dir / tenant_id).exists()
        assert not (secret_dir / tenant_id).exists()
        assert result.new_working_dir.exists()
        assert result.new_secret_dir.exists()


def test_migrate_tenant_scope_dirs_batch_prechecks_before_any_move(
    tmp_path: Path,
) -> None:
    """历史测试名；批量迁移会覆盖已存在的租户目标目录。"""
    module = _load_script_module()
    working_dir = tmp_path / ".swe"
    secret_dir = tmp_path / ".swe.secret"
    first_old_working = _seed_working_dir(working_dir, "tenant-a")
    second_old_working = _seed_working_dir(working_dir, "tenant-b")
    conflicting_scope = module.encode_scope_id("tenant-b", "source-a")
    target = working_dir / conflicting_scope
    target.mkdir(parents=True)
    (target / "old-target.txt").write_text("will be removed")

    module.migrate_tenant_scope_dirs_batch(
        tenant_ids=("tenant-a", "tenant-b"),
        source_id="source-a",
        working_dir=working_dir,
        secret_dir=secret_dir,
    )

    assert not first_old_working.exists()
    assert not second_old_working.exists()
    first_target = working_dir / module.encode_scope_id("tenant-a", "source-a")
    assert (first_target / "config.json").exists()
    assert (target / "config.json").exists()
    assert not (target / "old-target.txt").exists()
