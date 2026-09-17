# -*- coding: utf-8 -*-
"""测试默认 Skill 扫描器加载 MVP 分析器."""

from __future__ import annotations

from pathlib import Path

from swe.security.skill_scanner.scanner import SkillScanner


def test_default_scanner_uses_package_pattern_and_ast_analyzers(
    tmp_path: Path,
) -> None:
    skill_root = tmp_path / "demo"
    skill_root.mkdir()
    (skill_root / "main.py").write_text(
        "def run(x):\n    return eval(x)\n",
        encoding="utf-8",
    )

    result = SkillScanner().scan_skill(skill_root, skill_name="demo")

    assert {"package", "pattern", "ast_behavior"}.issubset(
        set(result.analyzers_used),
    )
    assert any(f.rule_id == "AST_DANGEROUS_EVAL" for f in result.findings)
