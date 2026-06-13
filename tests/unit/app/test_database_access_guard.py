# -*- coding: utf-8 -*-
"""数据库访问拦截规则的 source 开关回归测试。"""

from pathlib import Path

from swe.app.source_system_config.models import (
    EffectiveSourceSystemConfig,
    SourceSystemConfig,
)
from swe.app.source_system_config.runtime import bind_source_system_config
from swe.security.tool_guard.guardians.rule_guardian import (
    RuleBasedToolGuardian,
)


def _build_effective_config(enabled: bool) -> EffectiveSourceSystemConfig:
    """构造带数据库访问拦截开关的 effective config。"""
    return EffectiveSourceSystemConfig(
        source_id="portal",
        config=SourceSystemConfig.model_validate(
            {
                "feature_switches": {
                    "database_access_guard_enabled": enabled,
                },
            },
        ),
        version=1,
    )


def _write_database_rule(rules_dir: Path) -> None:
    """写入最小数据库规则，用于验证自定义 rules 目录行为。"""
    rules_dir.joinpath("dangerous_database_commands.yaml").write_text(
        """
- id: DB_CLI_TOOL
  tools: [execute_shell_command]
  params: [command]
  category: data_exfiltration
  severity: CRITICAL
  patterns:
    - '\\bmysql\\b'
  description: '检测到数据库 CLI 工具调用'
  remediation: '请使用受控数据库查询入口。'
""".lstrip(),
        encoding="utf-8",
    )


def test_custom_rules_dir_database_rules_respect_source_switch(tmp_path):
    """自定义 rules 目录中的数据库规则不应绕过 source 级开关。"""
    _write_database_rule(tmp_path)
    guardian = RuleBasedToolGuardian(rules_dir=tmp_path)

    with bind_source_system_config(_build_effective_config(False)):
        findings = guardian.guard(
            "execute_shell_command",
            {"command": "mysql -uroot"},
        )

    assert [finding.rule_id for finding in findings] == []


def test_database_rules_block_when_source_switch_enabled(tmp_path):
    """开启 source 开关后，数据库规则应继续阻断直连命令。"""
    _write_database_rule(tmp_path)
    guardian = RuleBasedToolGuardian(rules_dir=tmp_path)

    with bind_source_system_config(_build_effective_config(True)):
        findings = guardian.guard(
            "execute_shell_command",
            {"command": "mysql -uroot"},
        )

    assert [finding.rule_id for finding in findings] == ["DB_CLI_TOOL"]
