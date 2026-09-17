# -*- coding: utf-8 -*-
"""测试 Skill 包体安全分析器."""

from __future__ import annotations

import os
import stat
import zipfile
from pathlib import Path

from swe.security.skill_scanner.analyzers.package_analyzer import (
    PackageAnalyzer,
)
from swe.security.skill_scanner.models import Severity, ThreatCategory


def _write_skill(skill_root: Path) -> None:
    """创建最小 Skill 目录."""
    skill_root.mkdir(parents=True, exist_ok=True)
    (skill_root / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill package\n---\n",
        encoding="utf-8",
    )


def test_package_analyzer_flags_symlink_escape(tmp_path: Path) -> None:
    skill_root = tmp_path / "demo"
    _write_skill(skill_root)
    os.symlink("/etc/passwd", skill_root / "passwd_link")

    findings = PackageAnalyzer().analyze(skill_root, [], skill_name="demo")

    assert any(f.rule_id == "PACKAGE_SYMLINK_ESCAPE" for f in findings)
    finding = next(
        f for f in findings if f.rule_id == "PACKAGE_SYMLINK_ESCAPE"
    )
    assert finding.severity == Severity.CRITICAL
    assert finding.category == ThreatCategory.SUPPLY_CHAIN_ATTACK


def test_package_analyzer_flags_binary_extension(tmp_path: Path) -> None:
    skill_root = tmp_path / "demo"
    _write_skill(skill_root)
    binary_path = skill_root / "bin" / "helper"
    binary_path.parent.mkdir()
    binary_path.write_bytes(b"\x7fELF\x02\x01\x01\x00payload")

    findings = PackageAnalyzer().analyze(skill_root, [], skill_name="demo")

    assert any(f.rule_id == "PACKAGE_EXECUTABLE_BINARY" for f in findings)


def test_package_analyzer_flags_hidden_executable_script(
    tmp_path: Path,
) -> None:
    skill_root = tmp_path / "demo"
    _write_skill(skill_root)
    hidden_script = skill_root / ".hidden.py"
    hidden_script.write_text("print('hidden')\n", encoding="utf-8")
    hidden_script.chmod(hidden_script.stat().st_mode | stat.S_IXUSR)

    findings = PackageAnalyzer().analyze(skill_root, [], skill_name="demo")

    assert any(f.rule_id == "PACKAGE_HIDDEN_EXECUTABLE" for f in findings)


def test_package_analyzer_flags_zip_slip_archive_entry(
    tmp_path: Path,
) -> None:
    skill_root = tmp_path / "demo"
    _write_skill(skill_root)
    archive_path = skill_root / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("../../escape.py", "print('escape')\n")

    findings = PackageAnalyzer().analyze(skill_root, [], skill_name="demo")

    assert any(f.rule_id == "PACKAGE_ARCHIVE_PATH_TRAVERSAL" for f in findings)


def test_package_analyzer_flags_backslash_zip_slip_archive_entry(
    tmp_path: Path,
) -> None:
    """嵌套 ZIP 使用反斜杠时同样视为路径穿越."""
    skill_root = tmp_path / "demo"
    _write_skill(skill_root)
    archive_path = skill_root / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr(r"..\..\escape.py", "print('escape')\n")

    findings = PackageAnalyzer().analyze(skill_root, [], skill_name="demo")

    assert any(f.rule_id == "PACKAGE_ARCHIVE_PATH_TRAVERSAL" for f in findings)


def test_package_analyzer_flags_oversized_file(tmp_path: Path) -> None:
    skill_root = tmp_path / "demo"
    _write_skill(skill_root)
    large_path = skill_root / "large.dat"
    large_path.write_bytes(b"abcd")

    findings = PackageAnalyzer(max_file_bytes=3).analyze(
        skill_root,
        [],
        skill_name="demo",
    )

    assert any(f.rule_id == "PACKAGE_OVERSIZED_FILE" for f in findings)
