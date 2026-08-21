# -*- coding: utf-8 -*-
"""社区专家版本管理服务."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .fs import _atomic_write_json, _validate_path_segment
from .models import ExpertVersion, ExpertVersionsManifest

logger = logging.getLogger(__name__)

_IGNORED_ARTIFACTS = {
    "__pycache__",
    "__MACOSX",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".git",
    "versions",
    "versions.json",
    "scan_result.json",
}

_TEXT_EXTENSIONS = {
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".toml",
}


class ExpertVersionService:
    """社区专家版本管理服务."""

    def __init__(self, marketplace_root: Path):
        self.marketplace_root = Path(marketplace_root)

    def create_version_snapshot(
        self,
        source_id: str,
        item_id: str,
        source_dir: Path,
        version_id: str,
        expert_name: str,
        creator: str = "",
        creator_name: str = "",
        description: str = "",
        signature: str = "",
    ) -> ExpertVersion:
        """创建专家版本快照."""
        manifest = self._load_versions_manifest(source_id, item_id)
        existing = next(
            (v for v in manifest.versions if v.version_id == version_id),
            None,
        )
        if existing is not None:
            if existing.signature == signature:
                return existing
            raise ValueError(
                f"Version {version_id} already exists with different content",
            )

        version_dir = self._get_version_dir(source_id, item_id, version_id)
        if version_dir.exists():
            shutil.rmtree(version_dir)
        version_dir.mkdir(parents=True, exist_ok=True)
        self._copy_package_tree(source_dir, version_dir)

        now = datetime.now(timezone.utc).isoformat()
        is_initial = len(manifest.versions) == 0
        new_version = ExpertVersion(
            version_id=version_id,
            created_at=now,
            created_by=creator,
            created_by_name=creator_name,
            description=description or ("首次上传" if is_initial else ""),
            signature=signature,
            is_current=True,
            is_initial=is_initial,
        )
        for version in manifest.versions:
            version.is_current = False
        manifest.expert_name = expert_name or manifest.expert_name
        manifest.versions.append(new_version)
        self._save_versions_manifest(source_id, item_id, manifest)
        return new_version

    def list_versions(self, source_id: str, item_id: str) -> dict[str, Any]:
        """列出版本历史."""
        manifest = self._load_versions_manifest(source_id, item_id)
        versions = sorted(
            manifest.versions,
            key=lambda item: item.created_at,
            reverse=True,
        )
        return {
            "expert_name": manifest.expert_name,
            "versions": [version.model_dump() for version in versions],
        }

    def get_version_detail(
        self,
        source_id: str,
        item_id: str,
        version_id: str,
    ) -> dict[str, Any]:
        """获取版本详情."""
        manifest = self._load_versions_manifest(source_id, item_id)
        version_info = next(
            (v for v in manifest.versions if v.version_id == version_id),
            None,
        )
        if version_info is None:
            raise ValueError(f"Version {version_id} not found")

        version_dir = self._get_version_dir(source_id, item_id, version_id)
        if not version_dir.exists():
            raise ValueError(f"Version directory {version_id} not found")
        return {
            "version_info": version_info.model_dump(),
            "file_tree": self._build_file_tree(version_dir),
        }

    def restore_version(
        self,
        source_id: str,
        item_id: str,
        version_id: str,
        expert_root: Path,
    ) -> ExpertVersion:
        """恢复某个历史版本为当前版本."""
        manifest = self._load_versions_manifest(source_id, item_id)
        target = next(
            (v for v in manifest.versions if v.version_id == version_id),
            None,
        )
        if target is None:
            raise ValueError(f"Version {version_id} not found")

        version_dir = self._get_version_dir(source_id, item_id, version_id)
        if not version_dir.exists():
            raise ValueError(f"Version directory {version_id} not found")

        self._copy_package_tree(version_dir, expert_root)
        for version in manifest.versions:
            version.is_current = version.version_id == version_id
        self._save_versions_manifest(source_id, item_id, manifest)
        return target

    def calculate_signature(self, package_dir: Path) -> str:
        """计算包内容签名."""
        digest = hashlib.sha256()
        for path in sorted(package_dir.rglob("*")):
            if path.is_file() and not self._is_ignored(path):
                rel = path.relative_to(package_dir)
                digest.update(str(rel).encode("utf-8"))
                if path.suffix.lower() in _TEXT_EXTENSIONS:
                    try:
                        content = path.read_text(encoding="utf-8")
                    except (UnicodeDecodeError, OSError):
                        digest.update(path.read_bytes())
                    else:
                        digest.update(
                            content.replace("\r\n", "\n").encode("utf-8"),
                        )
                else:
                    digest.update(path.read_bytes())
        return digest.hexdigest()

    def _get_version_root(self, source_id: str, item_id: str) -> Path:
        _validate_path_segment(source_id, "source_id")
        _validate_path_segment(item_id, "item_id")
        return (
            self.marketplace_root
            / source_id
            / "experts"
            / item_id
            / "versions"
        )

    def _get_version_dir(
        self,
        source_id: str,
        item_id: str,
        version_id: str,
    ) -> Path:
        _validate_path_segment(version_id, "version_id")
        return self._get_version_root(source_id, item_id) / version_id

    def _get_versions_json_path(self, source_id: str, item_id: str) -> Path:
        _validate_path_segment(source_id, "source_id")
        _validate_path_segment(item_id, "item_id")
        return (
            self.marketplace_root
            / source_id
            / "experts"
            / item_id
            / "versions.json"
        )

    def _load_versions_manifest(
        self,
        source_id: str,
        item_id: str,
    ) -> ExpertVersionsManifest:
        path = self._get_versions_json_path(source_id, item_id)
        if not path.exists():
            return ExpertVersionsManifest()
        try:
            return ExpertVersionsManifest(
                **json.loads(path.read_text(encoding="utf-8")),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return ExpertVersionsManifest()

    def _save_versions_manifest(
        self,
        source_id: str,
        item_id: str,
        manifest: ExpertVersionsManifest,
    ) -> None:
        path = self._get_versions_json_path(source_id, item_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(path, manifest.model_dump())

    def _copy_package_tree(self, source_dir: Path, target_dir: Path) -> None:
        preserve = {"versions", "versions.json"}
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{target_dir.name}-", dir=target_dir.parent))
        backup = target_dir.with_name(f".{target_dir.name}.backup")
        try:
            for entry in source_dir.iterdir():
                if entry.name in preserve:
                    continue
                target = staging / entry.name
                if entry.is_dir():
                    shutil.copytree(entry, target)
                else:
                    shutil.copy2(entry, target)
            if target_dir.is_dir():
                for name in preserve:
                    existing = target_dir / name
                    if existing.is_dir():
                        shutil.copytree(existing, staging / name)
                    elif existing.is_file():
                        shutil.copy2(existing, staging / name)
            if backup.exists():
                shutil.rmtree(backup)
            if target_dir.exists():
                os.replace(target_dir, backup)
            os.replace(staging, target_dir)
            if backup.exists():
                shutil.rmtree(backup)
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            if not target_dir.exists() and backup.exists():
                os.replace(backup, target_dir)
            raise

    def _is_ignored(self, path: Path) -> bool:
        return bool(_IGNORED_ARTIFACTS & set(path.parts))

    def _build_file_tree(self, root: Path) -> list[dict[str, Any]]:
        if not root.exists():
            return []

        def build_tree(path: Path) -> dict[str, Any]:
            relative = path.relative_to(root).as_posix()
            if path.is_file():
                return {"name": path.name, "type": "file", "path": relative}
            children = []
            for child in sorted(path.iterdir()):
                if (
                    child.name.startswith(".")
                    or child.name in _IGNORED_ARTIFACTS
                ):
                    continue
                children.append(build_tree(child))
            return {
                "name": path.name,
                "type": "directory",
                "path": relative,
                "children": children,
            }

        return [
            build_tree(item)
            for item in sorted(root.iterdir())
            if not item.name.startswith(".")
            and item.name not in _IGNORED_ARTIFACTS
        ]
