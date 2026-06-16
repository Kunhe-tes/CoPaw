# -*- coding: utf-8 -*-
"""MCP 版本管理服务.

存储结构（与 SkillVersionService 平行）::

    <marketplace_root>/<source_id>/mcp_versions/<item_id>/
    ├── versions.json
    ├── 1.0.0/
    │   └── mcp.json
    └── 1.0.1/
        └── mcp.json
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .fs import _atomic_write_json
from .version_models import (
    MCPVersion,
    MCPVersionsManifest,
    VersionCompareResult,
    VersionDiffFile,
    VersionDiffStats,
)

logger = logging.getLogger(__name__)


# F4: MCP 签名只哈希影响行为的字段，避免 updated_at / created_at /
# version / received_version 等运维元数据导致 signature 漂移。
_SIGNATURE_FIELDS = (
    "name",
    "description",
    "transport",
    "url",
    "command",
    "args",
    "env",
    "headers",
    "cwd",
    "enabled",
    "lazy_load",
)


class MCPVersionService:
    """MCP 版本管理服务（与 SkillVersionService 对称）."""

    def __init__(self, marketplace_root: Path):
        self.marketplace_root = Path(marketplace_root)

    # ---------------------------------------------------------------- public

    def create_version_snapshot(
        self,
        source_id: str,
        item_id: str,
        mcp_dir: Path,
        version_id: str,
        creator: str = "",
        creator_name: str = "",
        description: str = "",
        source_user_id: str = "",
        source_user_name: str = "",
        source_user_version: str = "",
    ) -> MCPVersion:
        """创建 MCP 版本快照."""
        manifest = self._load_manifest(source_id, item_id)
        is_initial = len(manifest.versions) == 0

        new_signature = self._calculate_signature(mcp_dir)

        # R7: 同 version_id 同 signature → 完全 no-op
        existing = next(
            (v for v in manifest.versions if v.version_id == version_id),
            None,
        )
        if existing is not None:
            if existing.signature == new_signature:
                logger.info(
                    "MCP version %s already exists with same content (R7 no-op)",
                    version_id,
                )
                return existing
            raise ValueError(
                f"MCP version {version_id} already exists with different content. "
                f"Please specify a new version.",
            )

        # 在覆盖文件之前，记录上一版的 mcp.json 路径（用于自动生成 description）
        last_version_path: Path | None = None
        if manifest.versions:
            sorted_versions = sorted(
                manifest.versions,
                key=lambda v: v.created_at,
                reverse=True,
            )
            last_path = (
                self._get_version_dir(
                    source_id,
                    item_id,
                    sorted_versions[0].version_id,
                )
                / "mcp.json"
            )
            if last_path.exists():
                last_version_path = last_path

        # 复制 mcp.json 到版本目录
        version_dir = self._get_version_dir(source_id, item_id, version_id)
        if version_dir.exists():
            shutil.rmtree(version_dir)
        version_dir.mkdir(parents=True, exist_ok=True)
        src_mcp_json = mcp_dir / "mcp.json"
        if src_mcp_json.exists():
            shutil.copy2(src_mcp_json, version_dir / "mcp.json")

        # 自动生成 description（与 SkillVersionService 行为一致）：
        # - 调用方传了 description → 用之
        # - 初始版本 → "首次上传"
        # - 有上一版 → 行级 diff 统计："变更 1 个文件，新增 N 行，删除 M 行"
        if not description:
            if is_initial:
                description = "首次上传"
            elif last_version_path is not None:
                stats = self._compute_quick_diff_stats(
                    last_version_path,
                    version_dir / "mcp.json",
                )
                if stats["added_lines"] == 0 and stats["deleted_lines"] == 0:
                    description = "无变更"
                else:
                    parts = ["变更 1 个文件"]
                    if stats["added_lines"] > 0:
                        parts.append(f"新增 {stats['added_lines']} 行")
                    if stats["deleted_lines"] > 0:
                        parts.append(f"删除 {stats['deleted_lines']} 行")
                    description = "，".join(parts)

        # 翻转 is_current
        for v in manifest.versions:
            v.is_current = False

        new_version = MCPVersion(
            version_id=version_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=creator,
            created_by_name=creator_name,
            description=description,
            signature=new_signature,
            is_current=True,
            is_initial=is_initial,
            source_user_id=source_user_id,
            source_user_name=source_user_name,
            source_user_version=source_user_version,
        )
        manifest.versions.append(new_version)
        self._save_manifest(source_id, item_id, manifest)
        logger.info(
            "Created MCP version snapshot %s for item %s",
            version_id,
            item_id,
        )
        return new_version

    def _compute_quick_diff_stats(
        self,
        base_path: Path,
        target_path: Path,
    ) -> dict[str, int]:
        """对两个 mcp.json 做行级 diff 统计（用于自动生成 description）。"""
        try:
            base_text = self._read_pretty_for_diff(base_path)
            target_text = self._read_pretty_for_diff(target_path)
        except (UnicodeDecodeError, OSError):
            return {"added_lines": 0, "deleted_lines": 0}

        added = 0
        deleted = 0
        for line in difflib.unified_diff(
            base_text.splitlines(keepends=True),
            target_text.splitlines(keepends=True),
        ):
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                deleted += 1
        return {"added_lines": added, "deleted_lines": deleted}

    def _read_pretty_for_diff(self, path: Path) -> str:
        """读取 mcp.json 并以 sort_keys + indent=2 序列化，统一 diff 形态."""
        if not path.exists():
            return ""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return path.read_text(encoding="utf-8")
        return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)

    def list_versions(self, source_id: str, item_id: str) -> dict[str, Any]:
        """列出 MCP 版本（按 created_at 倒序）."""
        manifest = self._load_manifest(source_id, item_id)
        versions = sorted(
            manifest.versions,
            key=lambda v: v.created_at,
            reverse=True,
        )
        return {
            "client_key": manifest.client_key,
            "name": manifest.name,
            "versions": [v.model_dump() for v in versions],
        }

    def switch_version(
        self,
        source_id: str,
        item_id: str,
        target_version_id: str,
        current_mcp_dir: Path,
    ) -> dict[str, Any]:
        """切换到指定版本，将 mcp.json 拷回当前目录."""
        manifest = self._load_manifest(source_id, item_id)
        target = next(
            (
                v
                for v in manifest.versions
                if v.version_id == target_version_id
            ),
            None,
        )
        if target is None:
            return {
                "success": False,
                "previous_version": "",
                "current_version": "",
                "message": f"Version {target_version_id} not found",
            }

        target_dir = self._get_version_dir(
            source_id,
            item_id,
            target_version_id,
        )
        if not (target_dir / "mcp.json").exists():
            return {
                "success": False,
                "previous_version": "",
                "current_version": "",
                "message": f"Version dir {target_version_id} missing mcp.json",
            }

        current_mcp_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_dir / "mcp.json", current_mcp_dir / "mcp.json")

        previous = next(
            (v for v in manifest.versions if v.is_current),
            None,
        )
        for v in manifest.versions:
            v.is_current = v.version_id == target_version_id
        self._save_manifest(source_id, item_id, manifest)

        return {
            "success": True,
            "previous_version": previous.version_id if previous else "",
            "current_version": target_version_id,
            "message": f"Switched to version {target_version_id}",
        }

    def compare_versions(
        self,
        source_id: str,
        item_id: str,
        base_version_id: str,
        target_version_id: str,
    ) -> VersionCompareResult:
        """比对两个 MCP 版本快照（与 SkillVersionService.compare_versions 对称）.

        MCP 只有一个 mcp.json 文件，所以返回的 files 列表至多 1 项。
        通过 difflib.unified_diff 对 mcp.json 文本做行级 diff——使用与 Skill
        compare 同样的格式，便于前端复用同一套渲染。
        """
        base_dir = self._get_version_dir(source_id, item_id, base_version_id)
        target_dir = self._get_version_dir(
            source_id,
            item_id,
            target_version_id,
        )

        if not base_dir.exists():
            raise ValueError(f"Base version {base_version_id} not found")
        if not target_dir.exists():
            raise ValueError(f"Target version {target_version_id} not found")

        base_path = base_dir / "mcp.json"
        target_path = target_dir / "mcp.json"

        base_content = self._read_pretty_json(base_path)
        target_content = self._read_pretty_json(target_path)

        # 单文件 diff
        base_lines = base_content.splitlines(keepends=True)
        target_lines = target_content.splitlines(keepends=True)

        diff_text = "".join(
            difflib.unified_diff(
                base_lines,
                target_lines,
                fromfile="a/mcp.json",
                tofile="b/mcp.json",
            ),
        )

        added = 0
        deleted = 0
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                deleted += 1

        changed = 1 if (added > 0 or deleted > 0) else 0

        files: list[VersionDiffFile] = [
            VersionDiffFile(
                path="mcp.json",
                added_lines=added,
                deleted_lines=deleted,
                diff=diff_text,
                original_content=base_content,
                modified_content=target_content,
            ),
        ]

        return VersionCompareResult(
            base_version=base_version_id,
            target_version=target_version_id,
            stats=VersionDiffStats(
                added_lines=added,
                deleted_lines=deleted,
                changed_files=changed,
            ),
            files=files,
        )

    def _read_pretty_json(self, path: Path) -> str:
        """读 mcp.json 并以稳定的 pretty 格式返回，便于行级 diff 直观."""
        if not path.exists():
            return ""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            try:
                return path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                return ""
        return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)

    def delete_version(
        self,
        source_id: str,
        item_id: str,
        version_id: str,
    ) -> dict[str, Any]:
        """删除某个 MCP 版本快照（拒删 current/initial）."""
        manifest = self._load_manifest(source_id, item_id)
        target = next(
            (v for v in manifest.versions if v.version_id == version_id),
            None,
        )
        if target is None:
            return {
                "success": False,
                "deleted_version": "",
                "message": f"Version {version_id} not found",
            }
        if target.is_current:
            return {
                "success": False,
                "deleted_version": "",
                "message": "Cannot delete current version",
            }
        if target.is_initial:
            return {
                "success": False,
                "deleted_version": "",
                "message": "Cannot delete initial version",
            }
        manifest.versions = [
            v for v in manifest.versions if v.version_id != version_id
        ]
        self._save_manifest(source_id, item_id, manifest)
        version_dir = self._get_version_dir(source_id, item_id, version_id)
        if version_dir.exists():
            shutil.rmtree(version_dir, ignore_errors=True)
        return {
            "success": True,
            "deleted_version": version_id,
            "message": f"Deleted version {version_id}",
        }

    # -------------------------------------------------------------- internal

    def _get_version_root(self, source_id: str, item_id: str) -> Path:
        return self.marketplace_root / source_id / "mcp_versions" / item_id

    def _get_version_dir(
        self,
        source_id: str,
        item_id: str,
        version_id: str,
    ) -> Path:
        return self._get_version_root(source_id, item_id) / version_id

    def _get_manifest_path(self, source_id: str, item_id: str) -> Path:
        return self._get_version_root(source_id, item_id) / "versions.json"

    def _load_manifest(
        self,
        source_id: str,
        item_id: str,
    ) -> MCPVersionsManifest:
        path = self._get_manifest_path(source_id, item_id)
        if not path.exists():
            return MCPVersionsManifest()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return MCPVersionsManifest(**data)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return MCPVersionsManifest()

    def _save_manifest(
        self,
        source_id: str,
        item_id: str,
        manifest: MCPVersionsManifest,
    ) -> None:
        path = self._get_manifest_path(source_id, item_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(path, manifest.model_dump())

    def _calculate_signature(self, mcp_dir: Path) -> str:
        """SHA256(canonical_json(白名单字段))；mcp.json 缺失时为空 SHA.

        F4 修复：只对 _SIGNATURE_FIELDS 中影响行为的字段做 hash。
        排除 updated_at / created_at / version / received_version 等
        运维元数据，避免每次保存都触发 signature 漂移导致版本快照报"内容已变化"。
        """
        mcp_json_path = mcp_dir / "mcp.json"
        if not mcp_json_path.exists():
            return hashlib.sha256(b"").hexdigest()
        try:
            data = json.loads(mcp_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # 落到原始字节做 hash，避免完全失败
            return hashlib.sha256(mcp_json_path.read_bytes()).hexdigest()

        # save_mcp_config 写入的结构是 {"client_key": ..., "config": {...}}；
        # 历史调用方也可能直接写扁平结构。两种都兼容。
        config_section = data.get("config")
        if not isinstance(config_section, dict):
            config_section = data
        payload = {k: config_section.get(k) for k in _SIGNATURE_FIELDS}
        canonical = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
