# -*- coding: utf-8 -*-
"""Python AST 行为安全分析器."""

from __future__ import annotations

import ast
from pathlib import Path

from ..models import Finding, Severity, SkillFile, ThreatCategory
from . import BaseAnalyzer

_DANGEROUS_BUILTINS = {
    "eval": "AST_DANGEROUS_EVAL",
    "exec": "AST_DANGEROUS_EXEC",
    "compile": "AST_DANGEROUS_COMPILE",
}


class AstBehaviorAnalyzer(BaseAnalyzer):
    """通过 AST 识别 Python 技能中的危险行为."""

    def __init__(self) -> None:
        super().__init__(name="ast_behavior")

    def analyze(
        self,
        skill_dir: Path,
        files: list[SkillFile],
        *,
        skill_name: str | None = None,
    ) -> list[Finding]:
        """扫描 Python 文件并返回 AST 行为发现项."""
        del skill_dir, skill_name
        findings: list[Finding] = []
        for sf in files:
            if sf.file_type != "python":
                continue
            content = sf.read_content()
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            visitor = _DangerousCallVisitor(sf.relative_path)
            visitor.visit(tree)
            findings.extend(visitor.findings)
        return findings


class _DangerousCallVisitor(ast.NodeVisitor):
    """收集危险函数调用."""

    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.findings: list[Finding] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """记录命中的调用并继续遍历嵌套表达式."""
        rule_id = self._rule_for_call(node)
        if rule_id is not None:
            self.findings.append(
                _finding(
                    rule_id,
                    self.relative_path,
                    node.lineno,
                ),
            )
        self.generic_visit(node)

    def _rule_for_call(self, node: ast.Call) -> str | None:
        """将 AST 调用表达式映射到检测规则."""
        if isinstance(node.func, ast.Name):
            return _DANGEROUS_BUILTINS.get(node.func.id)
        if _is_subprocess_shell_true(node):
            return "AST_SUBPROCESS_SHELL_TRUE"
        if _is_os_system(node):
            return "AST_OS_SYSTEM"
        return None


def _is_subprocess_shell_true(node: ast.Call) -> bool:
    """识别 subprocess.* 且显式 shell=True 的调用."""
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in {"run", "call", "Popen"}:
        return False
    if not isinstance(node.func.value, ast.Name):
        return False
    if node.func.value.id != "subprocess":
        return False
    return any(
        kw.arg == "shell"
        and isinstance(kw.value, ast.Constant)
        and kw.value.value is True
        for kw in node.keywords
    )


def _is_os_system(node: ast.Call) -> bool:
    """识别 os.system() 命令执行调用."""
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "system":
        return False
    return isinstance(node.func.value, ast.Name) and node.func.value.id == "os"


def _finding(rule_id: str, file_path: str, line_number: int) -> Finding:
    """创建 AST 行为分析器统一 Finding."""
    title = {
        "AST_DANGEROUS_EVAL": "检测到 Python eval() 动态执行",
        "AST_DANGEROUS_EXEC": "检测到 Python exec() 动态执行",
        "AST_DANGEROUS_COMPILE": "检测到 Python compile() 动态编译",
        "AST_SUBPROCESS_SHELL_TRUE": "检测到 shell=True 的 subprocess 调用",
        "AST_OS_SYSTEM": "检测到 os.system() 命令执行",
    }[rule_id]
    severity = (
        Severity.CRITICAL
        if rule_id in {"AST_DANGEROUS_EVAL", "AST_DANGEROUS_EXEC"}
        else Severity.HIGH
    )
    return Finding(
        id=f"{rule_id}:{file_path}:{line_number}",
        rule_id=rule_id,
        category=ThreatCategory.COMMAND_INJECTION,
        severity=severity,
        title=title,
        description=title,
        file_path=file_path,
        line_number=line_number,
        remediation="移除动态代码执行，或替换为参数受限且经过校验的 API。",
        analyzer="ast_behavior",
    )
