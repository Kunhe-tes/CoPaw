# -*- coding: utf-8 -*-
"""Tests for skill runtime profile classification."""

from pathlib import Path

import pytest

from swe.agents.skill_runtime_profile import (
    SkillRuntimeProfile,
    build_skill_runtime_profile,
    build_skill_runtime_profiles,
)
from swe.agents.skills_manager import get_builtin_skills_dir


def _write_skill(
    root: Path,
    *,
    skill_name: str,
    description: str,
    metadata_block: str = "",
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Create a temporary skill directory for runtime profile tests."""
    skill_dir = root / skill_name
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    content = "---\n"
    content += f"name: {skill_name}\n"
    content += f"description: {description}\n"
    if metadata_block:
        content += metadata_block.strip() + "\n"
    content += "---\n"
    skill_md.write_text(content, encoding="utf-8")

    for rel_path, file_content in (extra_files or {}).items():
        file_path = skill_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(file_content, encoding="utf-8")

    return skill_dir


class TestSkillRuntimeProfile:
    """Tests for platform-side skill attribution policy."""

    def test_build_skill_runtime_profiles_includes_builtin_skills(
        self,
        tmp_path: Path,
    ):
        """批量构建 runtime profile 时不能漏掉 builtin skill。"""
        profiles = build_skill_runtime_profiles(tmp_path, ["xlsx"])

        builtin_skill_dir = get_builtin_skills_dir() / "xlsx"
        if not builtin_skill_dir.exists():
            pytest.skip("xlsx builtin skill is not available")

        assert "xlsx" in profiles

    def test_business_skill_is_trace_attributable(self, tmp_path: Path):
        """无 hook 的普通技能允许通过 declared tools 启动归因。"""
        skill_dir = _write_skill(
            tmp_path,
            skill_name="fill-metadata",
            description="补全Excel文件中缺失的字段中文名。",
        )

        profile = build_skill_runtime_profile(skill_dir, "fill-metadata")

        assert isinstance(profile, SkillRuntimeProfile)
        assert profile.trace_attributable is True
        assert profile.has_hook_config is False
        assert profile.declared_tool_bootstrap_allowed is True

    def test_skill_with_enabled_hook_disables_declared_tool_bootstrap(
        self,
        tmp_path: Path,
    ):
        """带有效 hook 配置的技能不能仅靠 declared tools 启动归因。"""
        skill_dir = _write_skill(
            tmp_path,
            skill_name="hook-http-demo",
            description=(
                "Use this skill when the user wants a concrete example of "
                "skill-owned hook files and hooks.json demo scaffolding."
            ),
            metadata_block="""
metadata:
  swe:
    uses_tools:
      - execute_shell_command
""",
            extra_files={
                "hooks/hooks.json": '{"enabled": true, "events": {}}',
            },
        )

        profile = build_skill_runtime_profile(skill_dir, "hook-http-demo")

        assert profile.trace_attributable is True
        assert profile.has_hook_config is True
        assert profile.declared_tool_bootstrap_allowed is False

    def test_skill_with_enabled_hook_keeps_trace_attribution(
        self,
        tmp_path: Path,
    ):
        """带有效 hook 配置的业务技能在显式激活后仍可进入 tracing。"""
        skill_dir = _write_skill(
            tmp_path,
            skill_name="weather-audit",
            description=(
                "Get current weather forecasts and attach a PostToolUse "
                "audit hook for execution summaries."
            ),
            metadata_block="""
metadata:
  swe:
    uses_tools:
      - execute_shell_command
""",
            extra_files={
                "hooks/hooks.json": '{"enabled": true, "events": {}}',
            },
        )

        profile = build_skill_runtime_profile(skill_dir, "weather-audit")

        assert profile.trace_attributable is True
        assert profile.declared_tool_bootstrap_allowed is False

    def test_malformed_frontmatter_falls_back_to_business(
        self,
        tmp_path: Path,
    ):
        """非法 frontmatter 不应导致整条 skill 注册链路失败。"""
        skill_dir = tmp_path / "broken-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: broken-skill\n"
            'description: 这是一个坏 skill: "unterminated\n'
            "---\n",
            encoding="utf-8",
        )

        profile = build_skill_runtime_profile(skill_dir, "broken-skill")

        assert profile.trace_attributable is True
        assert profile.declared_tool_bootstrap_allowed is True
        assert "frontmatter_parse_failed" in profile.reason

    def test_disabled_hook_config_does_not_make_skill_hook_source(
        self,
        tmp_path: Path,
    ):
        """禁用 hooks.json 不应关闭 declared tool bootstrap。"""
        skill_dir = _write_skill(
            tmp_path,
            skill_name="weather-audit",
            description="Get current weather forecasts and summaries.",
            metadata_block="""
metadata:
  swe:
    uses_tools:
      - execute_shell_command
""",
            extra_files={
                "hooks/hooks.json": '{"enabled": false, "events": {}}',
            },
        )

        profile = build_skill_runtime_profile(skill_dir, "weather-audit")

        assert profile.trace_attributable is True
        assert profile.has_hook_config is False
        assert profile.declared_tool_bootstrap_allowed is True

    def test_business_skill_with_enabled_hook_disables_bootstrap_without_keywords(
        self,
        tmp_path: Path,
    ):
        """是否禁用 bootstrap 只看 hook 结构事实，不看关键字。"""
        skill_dir = _write_skill(
            tmp_path,
            skill_name="ledger-runtime",
            description=(
                "Coordinate shipment reconciliation tasks for customer "
                "ledgers and generate execution summaries."
            ),
            metadata_block="""
metadata:
  swe:
    uses_tools:
      - execute_shell_command
""",
            extra_files={
                "hooks/hooks.json": '{"enabled": true, "events": {}}',
            },
        )

        profile = build_skill_runtime_profile(skill_dir, "ledger-runtime")

        assert profile.trace_attributable is True
        assert profile.has_hook_config is True
        assert profile.declared_tool_bootstrap_allowed is False
