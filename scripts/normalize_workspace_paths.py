#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校正所有租户配置中的 agent workspace_dir 路径。

只处理工作目录下每个租户根目录的 ``config.json`` 和
``workspaces/<agent>/agent.json``。默认只预览；传入 ``--apply`` 后才写盘。
每个被修改的 JSON 会先保留一个同目录 ``.bak`` 备份。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NormalizeResult:
    """路径校正结果。"""

    scanned_tenant_dirs: tuple[Path, ...]
    changed_files: tuple[Path, ...]
    invalid_json_files: tuple[Path, ...]


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    """备份并原子写入一个 JSON 对象。"""
    backup = path.with_name(f"{path.name}.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temp_path.unlink(missing_ok=True)


def _load_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_config(path: Path, *, apply: bool) -> bool | None:
    payload = _load_object(path)
    if payload is None:
        return None
    agents = payload.get("agents")
    profiles = agents.get("profiles") if isinstance(agents, dict) else None
    if not isinstance(profiles, dict):
        return False
    tenant_dir = path.parent
    changed = False
    for agent_id, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        workspace = tenant_dir / "workspaces" / str(agent_id)
        if not workspace.is_dir():
            continue
        expected = str(workspace.resolve())
        if profile.get("workspace_dir") != expected:
            profile["workspace_dir"] = expected
            changed = True
    if changed and apply:
        _write_json_atomically(path, payload)
    return changed


def _normalize_agent(path: Path, *, apply: bool) -> bool | None:
    payload = _load_object(path)
    if payload is None:
        return None
    expected = str(path.parent.resolve())
    if payload.get("workspace_dir") == expected:
        return False
    payload["workspace_dir"] = expected
    if apply:
        _write_json_atomically(path, payload)
    return True


def normalize_workspace_paths(
    working_dir: Path,
    *,
    apply: bool = False,
) -> NormalizeResult:
    """扫描并校正所有租户和来源模板的 workspace_dir 路径."""
    root = Path(working_dir).expanduser().resolve()
    tenant_dirs = (
        tuple(
            sorted(
                (
                    path
                    for path in root.iterdir()
                    if path.is_dir() and not path.name.startswith(".")
                ),
                key=lambda path: path.name,
            ),
        )
        if root.is_dir()
        else ()
    )
    changed: list[Path] = []
    invalid: list[Path] = []
    for tenant_dir in tenant_dirs:
        config_path = tenant_dir / "config.json"
        if config_path.is_file():
            status = _normalize_config(config_path, apply=apply)
            if status is None:
                invalid.append(config_path)
            elif status:
                changed.append(config_path)
        workspaces = tenant_dir / "workspaces"
        if not workspaces.is_dir():
            continue
        for agent_path in sorted(workspaces.glob("*/agent.json")):
            status = _normalize_agent(agent_path, apply=apply)
            if status is None:
                invalid.append(agent_path)
            elif status:
                changed.append(agent_path)
    return NormalizeResult(tuple(tenant_dirs), tuple(changed), tuple(invalid))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--working-dir", type=Path, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="写入修正并生成 .bak 备份",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    result = normalize_workspace_paths(args.working_dir, apply=args.apply)
    mode = "applied" if args.apply else "dry-run"
    print(f"mode: {mode}")
    print(f"tenant_dirs: {len(result.scanned_tenant_dirs)}")
    print(f"changed_files: {len(result.changed_files)}")
    for path in result.changed_files:
        print(f"  {'updated' if args.apply else 'would update'}: {path}")
    print(f"invalid_json_files: {len(result.invalid_json_files)}")
    for path in result.invalid_json_files:
        print(f"  invalid: {path}")
    return 1 if result.invalid_json_files else 0


if __name__ == "__main__":
    raise SystemExit(main())
