# -*- coding: utf-8 -*-
"""测试 Python AST 行为分析器."""

from __future__ import annotations

from pathlib import Path

from swe.security.skill_scanner.analyzers.ast_behavior_analyzer import (
    AstBehaviorAnalyzer,
)
from swe.security.skill_scanner.models import SkillFile


def _skill_file(path: Path, skill_root: Path) -> SkillFile:
    """按扫描器发现结果构造 SkillFile."""
    return SkillFile.from_path(path, skill_root)


def test_ast_behavior_flags_eval(tmp_path: Path) -> None:
    skill_root = tmp_path / "demo"
    skill_root.mkdir()
    code_path = skill_root / "main.py"
    code_path.write_text(
        "def run(user_code):\n    return eval(user_code)\n",
        encoding="utf-8",
    )

    findings = AstBehaviorAnalyzer().analyze(
        skill_root,
        [_skill_file(code_path, skill_root)],
        skill_name="demo",
    )

    assert any(f.rule_id == "AST_DANGEROUS_EVAL" for f in findings)


def test_ast_behavior_flags_subprocess_shell_true(tmp_path: Path) -> None:
    skill_root = tmp_path / "demo"
    skill_root.mkdir()
    code_path = skill_root / "main.py"
    code_path.write_text(
        "import subprocess\n"
        "def run(cmd):\n"
        "    return subprocess.run(cmd, shell=True)\n",
        encoding="utf-8",
    )

    findings = AstBehaviorAnalyzer().analyze(
        skill_root,
        [_skill_file(code_path, skill_root)],
        skill_name="demo",
    )

    assert any(f.rule_id == "AST_SUBPROCESS_SHELL_TRUE" for f in findings)


def test_ast_behavior_ignores_documentation_markdown(
    tmp_path: Path,
) -> None:
    skill_root = tmp_path / "demo"
    skill_root.mkdir()
    doc_path = skill_root / "README.md"
    doc_path.write_text("Example: eval(user_code)\n", encoding="utf-8")

    findings = AstBehaviorAnalyzer().analyze(
        skill_root,
        [_skill_file(doc_path, skill_root)],
        skill_name="demo",
    )

    assert findings == []
