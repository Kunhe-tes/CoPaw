# -*- coding: utf-8 -*-
"""Skill 包体安全分析器."""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path

from ..models import Finding, Severity, SkillFile, ThreatCategory
from . import BaseAnalyzer

_BINARY_EXTENSIONS = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".o",
    ".a",
}
_ARCHIVE_EXTENSIONS = {".zip"}
_EXECUTABLE_MAGIC = (b"\x7fELF", b"MZ")
_DEFAULT_MAX_FILE_BYTES = 20 * 1024 * 1024


class PackageAnalyzer(BaseAnalyzer):
    """检查 Skill 包体结构中的高风险文件."""

    def __init__(
        self,
        *,
        max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES,
    ) -> None:
        super().__init__(name="package")
        self._max_file_bytes = max_file_bytes

    def analyze(
        self,
        skill_dir: Path,
        files: list[SkillFile],
        *,
        skill_name: str | None = None,
    ) -> list[Finding]:
        """扫描包体层风险并返回发现项."""
        del files, skill_name
        findings: list[Finding] = []
        for path in sorted(skill_dir.rglob("*")):
            rel_path = _relative_path(path, skill_dir)
            if path.is_symlink():
                findings.append(
                    _finding(
                        "PACKAGE_SYMLINK_ESCAPE",
                        Severity.CRITICAL,
                        "Skill 包中包含符号链接",
                        rel_path,
                        "移除 Skill 包中的符号链接，改用可审计的普通文件。",
                    ),
                )
                continue
            if not path.is_file():
                continue
            if path.stat().st_size > self._max_file_bytes:
                findings.append(
                    _finding(
                        "PACKAGE_OVERSIZED_FILE",
                        Severity.HIGH,
                        "Skill 包中包含超大文件",
                        rel_path,
                        "移除不必要的大文件，或拆分为外部受控资源。",
                    ),
                )
            if _is_executable_binary(path):
                findings.append(
                    _finding(
                        "PACKAGE_EXECUTABLE_BINARY",
                        Severity.CRITICAL,
                        "Skill 包中包含可执行二进制内容",
                        rel_path,
                        "移除二进制可执行文件，改用可审计脚本或受控工具。",
                    ),
                )
            if _is_hidden_executable(path, skill_dir):
                findings.append(
                    _finding(
                        "PACKAGE_HIDDEN_EXECUTABLE",
                        Severity.HIGH,
                        "Skill 包中包含隐藏可执行代码",
                        rel_path,
                        "将可执行代码放在显式路径中，并补充用途说明。",
                    ),
                )
            if path.suffix.lower() in _ARCHIVE_EXTENSIONS:
                findings.extend(_scan_zip(path, rel_path))
        return findings


def _relative_path(path: Path, skill_dir: Path) -> str:
    """返回用于 Finding 展示的 Skill 内相对路径."""
    try:
        return str(path.relative_to(skill_dir))
    except ValueError:
        return str(path)


def _is_executable_binary(path: Path) -> bool:
    """识别常见二进制扩展名或可执行文件魔数."""
    if path.suffix.lower() in _BINARY_EXTENSIONS:
        return True
    try:
        with path.open("rb") as handle:
            head = handle.read(4)
    except OSError:
        return False
    return any(head.startswith(magic) for magic in _EXECUTABLE_MAGIC)


def _is_hidden_executable(path: Path, skill_dir: Path) -> bool:
    """隐藏路径具备执行位时视为高风险入口."""
    rel_parts = path.relative_to(skill_dir).parts
    if not any(part.startswith(".") for part in rel_parts):
        return False
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    return bool(mode & stat.S_IXUSR)


def _scan_zip(path: Path, rel_path: str) -> list[Finding]:
    """检查嵌套 ZIP 中最直接的路径穿越风险."""
    findings: list[Finding] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in Path(name).parts:
                    findings.append(
                        _finding(
                            "PACKAGE_ARCHIVE_PATH_TRAVERSAL",
                            Severity.CRITICAL,
                            "嵌套压缩包包含路径穿越成员",
                            rel_path,
                            "移除嵌套压缩包中的路径穿越成员。",
                            snippet=name,
                        ),
                    )
    except zipfile.BadZipFile:
        findings.append(
            _finding(
                "PACKAGE_ARCHIVE_UNREADABLE",
                Severity.MEDIUM,
                "嵌套压缩包无法被检查",
                rel_path,
                "将不可读压缩包替换为可审计的普通文件。",
            ),
        )
    return findings


def _finding(
    rule_id: str,
    severity: Severity,
    title: str,
    file_path: str,
    remediation: str,
    *,
    snippet: str | None = None,
) -> Finding:
    """创建包体分析器统一 Finding."""
    return Finding(
        id=f"{rule_id}:{file_path}",
        rule_id=rule_id,
        category=ThreatCategory.SUPPLY_CHAIN_ATTACK,
        severity=severity,
        title=title,
        description=title,
        file_path=file_path,
        snippet=snippet,
        remediation=remediation,
        analyzer="package",
    )
