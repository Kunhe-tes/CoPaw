# -*- coding: utf-8 -*-
"""Tests for skill invocation detection and custom skill recognition.

This test module covers:
1. SkillToolRegistry - tool ownership declarations
2. SkillFeatureInferencer - feature-based skill inference
3. SkillInvocationDetector - multi-layer skill attribution
4. SkillContextManager - execution context tracking
"""

# pylint: disable=protected-access,redefined-outer-name

import asyncio
import json
from datetime import datetime
import pytest
from unittest.mock import AsyncMock

from swe.agents.skill_tool_registry import (
    SkillToolRegistry,
    get_skill_tool_registry,
    reset_skill_tool_registry,
)
from swe.agents.skill_feature_inferencer import (
    SkillFeature,
    SkillFeatureInferencer,
    BUILTIN_SKILL_FEATURES,
    get_skill_feature_inferencer,
    reset_skill_feature_inferencer,
)
from swe.agents.skill_context_manager import (
    SkillExecutionContext,
    SkillContextManager,
    get_skill_context_manager,
    reset_skill_context_manager,
)
from swe.agents.skill_invocation_detector import (
    SkillInvocationDetector,
    get_skill_invocation_detector,
    reset_skill_invocation_detector,
)
from swe.agents.skill_runtime_profile import SkillRuntimeProfile
from swe.agents.skills_manager import get_workspace_skill_manifest_path


@pytest.fixture(autouse=True)
def reset_all_globals():
    """Reset all global instances before and after each test."""
    reset_skill_tool_registry()
    reset_skill_feature_inferencer()
    reset_skill_context_manager()
    reset_skill_invocation_detector()
    yield
    reset_skill_tool_registry()
    reset_skill_feature_inferencer()
    reset_skill_context_manager()
    reset_skill_invocation_detector()


# =============================================================================
# SkillToolRegistry Tests
# =============================================================================


class TestSkillToolRegistry:
    """Tests for SkillToolRegistry class."""

    def test_register_single_skill(self):
        """Test registering tools for a single skill."""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "pdf",
            ["read_file", "execute_shell_command"],
        )

        assert registry.skill_count == 1
        assert registry.get_tools_for_skill("pdf") == [
            "read_file",
            "execute_shell_command",
        ]

    def test_register_multiple_skills(self):
        """Test registering tools for multiple skills."""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "pdf",
            ["read_file", "execute_shell_command"],
        )
        registry.register_skill_tools("xlsx", ["read_file", "write_file"])

        assert registry.skill_count == 2
        assert (
            registry.tool_count == 3
        )  # read_file, execute_shell_command, write_file

    def test_get_skills_for_tool(self):
        """Test getting skills that claim a tool."""
        registry = SkillToolRegistry()
        registry.register_skill_tools("pdf", ["read_file"])
        registry.register_skill_tools("xlsx", ["read_file", "write_file"])
        registry.register_skill_tools("docx", ["read_file"])

        skills = registry.get_skills_for_tool("read_file")
        assert skills == ["docx", "pdf", "xlsx"]  # Sorted

    def test_wildcard_pattern_matching(self):
        """Test wildcard pattern matching for tool names."""
        registry = SkillToolRegistry()
        registry.register_skill_tools("browser", ["browser_*"])

        skills = registry.get_skills_for_tool("browser_click")
        assert skills == ["browser"]

        skills = registry.get_skills_for_tool("browser_navigate")
        assert skills == ["browser"]

        skills = registry.get_skills_for_tool("other_tool")
        assert skills == []

    def test_calculate_weights_single_skill(self):
        """Test weight calculation for single skill."""
        registry = SkillToolRegistry()
        weights = registry.calculate_weights(["pdf"])

        assert weights == {"pdf": 1.0}

    def test_calculate_weights_multiple_skills(self):
        """Test weight calculation for multiple skills."""
        registry = SkillToolRegistry()
        weights = registry.calculate_weights(["pdf", "xlsx"])

        assert weights == {"pdf": 0.5, "xlsx": 0.5}

    def test_calculate_weights_empty(self):
        """Test weight calculation for empty list."""
        registry = SkillToolRegistry()
        weights = registry.calculate_weights([])

        assert weights == {}

    def test_clear_registry(self):
        """Test clearing the registry."""
        registry = SkillToolRegistry()
        registry.register_skill_tools("pdf", ["read_file"])

        assert registry.skill_count == 1

        registry.clear()

        assert registry.skill_count == 0
        assert registry.tool_count == 0

    def test_global_registry(self):
        """Test global registry functions."""
        registry1 = get_skill_tool_registry()
        registry2 = get_skill_tool_registry()

        assert registry1 is registry2

        reset_skill_tool_registry()
        registry3 = get_skill_tool_registry()

        assert registry3 is not registry1


# =============================================================================
# SkillFeatureInferencer Tests
# =============================================================================


class TestSkillFeatureInferencer:
    """Tests for SkillFeatureInferencer class."""

    def test_glob_search_should_not_infer_skill_from_impl_script_extension(
        self,
    ):
        """实现脚本扩展名不应作为技能输入证据。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "fill-metadata": SkillFeature(
                    skill_name="fill-metadata",
                    file_extensions=[],
                    observed_file_extensions=[".py", ".json", ".md"],
                    keywords=["excel", "元数据", "中文名", "字段"],
                ),
            },
        )

        skill, confidence = inferencer.infer_skill_from_tool_input(
            "glob_search",
            {"pattern": "c_jp.py"},
            ["fill-metadata"],
        )

        assert skill is None
        assert confidence == 0.0

    def test_read_file_should_not_infer_skill_from_impl_script_extension(self):
        """实现脚本扩展名不应触发 read_file 技能识别。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "fill-metadata": SkillFeature(
                    skill_name="fill-metadata",
                    file_extensions=[],
                    observed_file_extensions=[".py", ".json", ".md"],
                    keywords=["excel", "元数据", "中文名", "字段"],
                ),
            },
        )

        skill, confidence = inferencer.infer_skill_from_tool_input(
            "read_file",
            {"file_path": "c_jp.py"},
            ["fill-metadata"],
        )

        assert skill is None
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_reading_step_markdown_should_not_infer_self_improvement(
        self,
    ):
        """步骤说明文档不应自动激活 self-improvement。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "self-improvement": SkillFeature(
                    skill_name="self-improvement",
                    file_extensions=[],
                    observed_file_extensions=[
                        ".com",
                        ".ext",
                        ".g",
                        ".git",
                        ".io",
                        ".json",
                        ".md",
                        ".sh",
                        ".yaml",
                    ],
                    keywords=["continuous", "learning", "improvement"],
                    description_keywords=["continuous", "learning"],
                ),
            },
        )

        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["self-improvement"])

        skill, weights = await detector.on_tool_call(
            "read_file",
            {"file_path": "steps/step0.md"},
        )

        assert skill is None
        assert weights == {}

    def test_grep_search_should_not_infer_skill_from_impl_script_extension(
        self,
    ):
        """实现脚本扩展名不应触发 grep_search 技能识别。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "fill-metadata": SkillFeature(
                    skill_name="fill-metadata",
                    file_extensions=[],
                    observed_file_extensions=[".py", ".json", ".md"],
                    keywords=["excel", "元数据", "中文名", "字段"],
                ),
            },
        )

        skill, confidence = inferencer.infer_skill_from_tool_input(
            "grep_search",
            {"pattern": "c_jp.py"},
            ["fill-metadata"],
        )

        assert skill is None
        assert confidence == 0.0

    def test_execute_shell_should_not_infer_skill_from_impl_script_name(
        self,
    ):
        """实现脚本文件名不应作为 execute_shell 的技能输入证据。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "fill-metadata": SkillFeature(
                    skill_name="fill-metadata",
                    file_extensions=[],
                    observed_file_extensions=[".py", ".json", ".md"],
                    keywords=["excel", "元数据", "中文名", "字段"],
                ),
            },
        )

        skill, confidence = inferencer.infer_skill_from_tool_input(
            "execute_shell_command",
            {"command": "rm -f c_jp.py"},
            ["fill-metadata"],
        )

        assert skill is None
        assert confidence == 0.0

    def test_execute_shell_with_keyword_keeps_semantic_skill_detection(self):
        """语义技能仍可通过关键词在执行型工具上被识别。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "fill-metadata": SkillFeature(
                    skill_name="fill-metadata",
                    file_extensions=[],
                    keywords=["excel", "元数据", "中文名", "字段"],
                ),
            },
        )

        skill, confidence = inferencer.infer_skill_from_tool_input(
            "execute_shell_command",
            {"command": "处理 excel 元数据 并补全 字段 中文名"},
            ["fill-metadata"],
        )

        assert skill == "fill-metadata"
        assert confidence >= 0.4

    def test_infer_from_file_extension(self):
        """Test skill inference from file extension in tool input."""
        inferencer = SkillFeatureInferencer()

        skill, confidence = inferencer.infer_skill_from_tool_input(
            "execute_shell_command",
            {"command": "python process.py data.xlsx"},
            ["xlsx", "pdf"],
        )

        assert skill == "xlsx"
        assert confidence == 0.8

    def test_infer_from_keyword(self):
        """Test skill inference from keywords in tool input."""
        inferencer = SkillFeatureInferencer()

        skill, confidence = inferencer.infer_skill_from_tool_input(
            "execute_shell_command",
            {"command": "convert this excel file"},
            ["xlsx", "pdf"],
        )

        assert skill == "xlsx"
        assert confidence >= 0.4

    def test_infer_from_tool_hint(self):
        """Test skill inference from tool hint."""
        inferencer = SkillFeatureInferencer()

        skill, confidence = inferencer.infer_skill_from_tool_input(
            "execute_shell_command",
            {"command": "do something generic"},
            ["xlsx"],
        )

        # execute_shell_command is in xlsx tools_hint
        assert skill == "xlsx"
        assert confidence == 0.5

    def test_infer_no_match(self):
        """Test no skill match returns None."""
        inferencer = SkillFeatureInferencer()

        skill, confidence = inferencer.infer_skill_from_tool_input(
            "unknown_tool",
            {"data": "generic content"},
            ["xlsx"],
        )

        assert skill is None
        assert confidence == 0.0

    def test_infer_from_tool_sequence(self):
        """Test skill inference from tool sequence pattern."""
        inferencer = SkillFeatureInferencer()

        # xlsx has pattern ["read_file", "execute_shell_command"]
        skill, confidence = inferencer.infer_skill_from_tool_sequence(
            ["other_tool", "read_file", "execute_shell_command"],
            ["xlsx"],
        )

        assert skill == "xlsx"
        assert confidence == 0.6

    def test_infer_sequence_no_match(self):
        """Test sequence inference with no pattern match."""
        inferencer = SkillFeatureInferencer()

        skill, _ = inferencer.infer_skill_from_tool_sequence(
            ["read_file", "write_file"],
            ["xlsx"],
        )

        assert skill is None

    def test_get_skills_for_tool(self):
        """Test getting skills that might use a tool."""
        inferencer = SkillFeatureInferencer()

        skills = inferencer.get_skills_for_tool(
            "execute_shell_command",
            ["xlsx", "pdf"],
        )

        assert len(skills) == 2
        assert ("xlsx", 0.4) in skills
        assert ("pdf", 0.4) in skills

    def test_register_custom_feature(self):
        """Test registering a custom skill feature."""
        inferencer = SkillFeatureInferencer()

        custom_feature = SkillFeature(
            skill_name="custom_skill",
            file_extensions=[".custom"],
            keywords=["custom_keyword"],
            tools_hint=["custom_tool"],
        )

        inferencer.register_feature(custom_feature)

        # Verify the feature is registered
        feature = inferencer.get_feature("custom_skill")
        assert feature is not None
        assert feature.skill_name == "custom_skill"

        # Test inference with custom skill
        skill, confidence = inferencer.infer_skill_from_tool_input(
            "custom_tool",
            {"file": "data.custom"},
            ["custom_skill"],
        )

        assert skill == "custom_skill"
        assert confidence == 0.8  # File extension match

    def test_builtin_features_loaded(self):
        """Test that built-in features are loaded by default."""
        inferencer = SkillFeatureInferencer()

        assert inferencer.get_feature("xlsx") is not None
        assert inferencer.get_feature("pdf") is not None
        assert inferencer.get_feature("docx") is not None
        assert inferencer.get_feature("pptx") is not None
        assert inferencer.get_feature("browser_cdp") is not None
        assert inferencer.get_feature("browser_visible") is not None
        assert inferencer.get_feature("cron") is not None

    def test_builtin_xlsx_feature_properties(self):
        """Test xlsx built-in feature properties."""
        feature = BUILTIN_SKILL_FEATURES["xlsx"]

        assert ".xlsx" in feature.file_extensions
        assert ".xls" in feature.file_extensions
        assert "excel" in feature.keywords
        assert "表格" in feature.keywords  # Chinese keyword
        assert "execute_shell_command" in feature.tools_hint

    def test_global_inferencer(self):
        """Test global inferencer functions."""
        inferencer1 = get_skill_feature_inferencer()
        inferencer2 = get_skill_feature_inferencer()

        assert inferencer1 is inferencer2

        reset_skill_feature_inferencer()
        inferencer3 = get_skill_feature_inferencer()

        assert inferencer3 is not inferencer1


# =============================================================================
# SkillContextManager Tests
# =============================================================================


class TestSkillContextManager:
    """Tests for SkillContextManager class."""

    def test_push_and_pop_skill(self):
        """Test pushing and popping skills from stack."""
        manager = SkillContextManager()

        manager.push_skill("xlsx", trigger_reason="declared")
        assert manager.current_skill == "xlsx"
        assert manager.skill_depth == 1

        context = manager.pop_skill()
        assert context is not None
        assert context.skill_name == "xlsx"
        assert manager.current_skill is None
        assert manager.skill_depth == 0

    def test_nested_skills(self):
        """Test nested skill execution."""
        manager = SkillContextManager()

        manager.push_skill("xlsx", trigger_reason="declared")
        manager.push_skill("pdf", trigger_reason="inferred")

        assert manager.skill_depth == 2
        assert manager.current_skill == "pdf"
        assert manager.active_skills == ["xlsx", "pdf"]

        manager.pop_skill()
        assert manager.current_skill == "xlsx"

        manager.pop_skill()
        assert manager.current_skill is None

    def test_record_tool_call(self):
        """Test recording tool calls in skill context."""
        manager = SkillContextManager()

        manager.push_skill("xlsx", trigger_reason="declared")
        manager.record_tool_call("read_file")
        manager.record_tool_call("execute_shell_command")

        context = manager.current_context
        assert context is not None
        assert "read_file" in context.tools_called
        assert "execute_shell_command" in context.tools_called

    def test_record_mcp_tool_call(self):
        """Test recording MCP tool calls in skill context."""
        manager = SkillContextManager()

        manager.push_skill("browser", trigger_reason="declared")
        manager.record_tool_call("navigate", mcp_server="puppeteer")

        context = manager.current_context
        assert context is not None
        assert "puppeteer:navigate" in context.mcp_tools_called

    def test_pop_empty_stack(self):
        """Test popping from empty stack returns None."""
        manager = SkillContextManager()

        context = manager.pop_skill()
        assert context is None

    def test_clear_context(self):
        """Test clearing the context."""
        manager = SkillContextManager()

        manager.push_skill("xlsx")
        manager.push_skill("pdf")

        assert manager.skill_depth == 2

        manager.clear()

        assert manager.skill_depth == 0
        assert manager.current_skill is None

    def test_get_all_contexts(self):
        """Test getting all contexts from stack."""
        manager = SkillContextManager()

        manager.push_skill("xlsx")
        manager.push_skill("pdf")

        contexts = manager.get_all_contexts()

        assert len(contexts) == 2
        assert contexts[0].skill_name == "xlsx"
        assert contexts[1].skill_name == "pdf"

    def test_global_context_manager(self):
        """Test global context manager functions."""
        manager1 = get_skill_context_manager()
        manager2 = get_skill_context_manager()

        assert manager1 is manager2

        reset_skill_context_manager()
        manager3 = get_skill_context_manager()

        assert manager3 is not manager1


# =============================================================================
# SkillInvocationDetector Tests
# =============================================================================


class TestSkillInvocationDetector:
    """Tests for SkillInvocationDetector class."""

    def test_set_enabled_skills(self):
        """Test setting enabled skills."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx", "pdf"])

        assert "xlsx" in detector._enabled_skills
        assert "pdf" in detector._enabled_skills

    def test_set_enabled_skills_reads_metadata_from_v2_manifest(
        self,
        tmp_path,
    ):
        workspace_dir = tmp_path / "workspace"
        manifest_path = get_workspace_skill_manifest_path(workspace_dir)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                {
                    "skills": {
                        "demo": {
                            "enabled": True,
                            "metadata": {
                                "description": "v2 description",
                                "skill_id": "skill-1",
                                "cn_name": "演示技能",
                            },
                        },
                    },
                },
            ),
            encoding="utf-8",
        )
        detector = SkillInvocationDetector(workspace_dir=workspace_dir)

        detector.set_enabled_skills(["demo"])

        assert detector._skill_descriptions["demo"] == "v2 description"
        assert detector._skill_ids["demo"] == "skill-1"
        assert detector._skill_cn_names["demo"] == "演示技能"

    @pytest.mark.asyncio
    async def test_declared_skill_attribution(self):
        """显式声明 + 输入证据仍可识别技能。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools("xlsx", ["read_file"])

        detector = SkillInvocationDetector(registry=registry)
        detector.set_enabled_skills(["xlsx"])

        skill, weights = await detector.on_tool_call(
            "read_file",
            {"path": "/data/test.xlsx"},
        )

        assert skill == "xlsx"
        assert weights.get("xlsx", 0) >= 0.8

    @pytest.mark.asyncio
    async def test_inferred_skill_from_extension(self):
        """Test skill inference from file extension."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx"])

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "python process data.xlsx"},
        )

        assert skill == "xlsx"
        assert weights.get("xlsx", 0) >= 0.8

    @pytest.mark.asyncio
    async def test_inferred_skill_from_keyword(self):
        """弱关键词证据不能单独启动技能。"""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx"])

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "process this excel file"},
        )

        assert skill is None
        assert weights == {}

    @pytest.mark.asyncio
    async def test_detector_should_not_activate_skill_from_impl_glob_py(
        self,
    ):
        """detector 不应因实现脚本扩展名激活技能。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "fill-metadata": SkillFeature(
                    skill_name="fill-metadata",
                    file_extensions=[],
                    observed_file_extensions=[".py", ".json", ".md"],
                    keywords=["excel", "元数据", "中文名", "字段"],
                ),
            },
        )
        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["fill-metadata"])

        skill, weights = await detector.on_tool_call(
            "glob_search",
            {"pattern": "c_jp.py"},
        )

        assert skill is None
        assert weights == {}

    @pytest.mark.asyncio
    async def test_detector_should_keep_xlsx_inference_for_execute_shell(
        self,
    ):
        """文件型技能在执行型工具上的扩展名识别能力应保留。"""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx"])

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "python analyze.py report.xlsx"},
        )

        assert skill == "xlsx"
        assert weights.get("xlsx", 0) >= 0.8

    @pytest.mark.asyncio
    async def test_detector_should_keep_xlsx_inference_for_read_file(self):
        """文件型技能在 read_file 上的扩展名识别能力应保留。"""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx"])

        skill, weights = await detector.on_tool_call(
            "read_file",
            {"file_path": "report.xlsx"},
        )

        assert skill == "xlsx"
        assert weights.get("xlsx", 0) >= 0.8

    @pytest.mark.asyncio
    async def test_detector_semantic_skill_still_detected_by_keywords(self):
        """语义关键词不能从 tool input 单独启动技能。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "fill-metadata": SkillFeature(
                    skill_name="fill-metadata",
                    file_extensions=[],
                    keywords=["excel", "元数据", "中文名", "字段"],
                ),
            },
        )
        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["fill-metadata"])

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "处理 excel 元数据 并补全 字段 中文名"},
        )

        assert skill is None
        assert weights == {}

    @pytest.mark.asyncio
    async def test_detector_prefers_file_skill_for_xlsx_when_multiple_skills(
        self,
    ):
        """多技能并存时，真正的 xlsx 输入应归因到文件型技能。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "xlsx": BUILTIN_SKILL_FEATURES["xlsx"],
                "fill-metadata": SkillFeature(
                    skill_name="fill-metadata",
                    file_extensions=[],
                    keywords=["excel", "元数据", "中文名", "字段"],
                ),
            },
        )
        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["xlsx", "fill-metadata"])

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "python analyze.py report.xlsx"},
        )

        assert skill == "xlsx"
        assert weights.get("xlsx", 0) >= 0.8

    @pytest.mark.asyncio
    async def test_detector_keeps_semantic_skill_for_keyword_only_command(
        self,
    ):
        """多技能并存时，仅语义关键词命中也不能单独启动技能。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "xlsx": BUILTIN_SKILL_FEATURES["xlsx"],
                "fill-metadata": SkillFeature(
                    skill_name="fill-metadata",
                    file_extensions=[],
                    keywords=["excel", "元数据", "中文名", "字段"],
                ),
            },
        )
        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["xlsx", "fill-metadata"])

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "补全 excel 元数据 的 字段 中文名"},
        )

        assert skill is None
        assert weights == {}

    @pytest.mark.asyncio
    async def test_declared_hook_runtime_skill_does_not_bootstrap_without_explicit_evidence(
        self,
    ):
        """带 hook 配置的技能不能仅凭 declared tool 自动启动。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "hook-http-demo",
            ["execute_shell_command"],
        )
        detector = SkillInvocationDetector(registry=registry)
        detector.set_enabled_skills(["hook-http-demo"])
        detector.set_skill_runtime_profiles(
            {
                "hook-http-demo": SkillRuntimeProfile(
                    skill_name="hook-http-demo",
                    trace_attributable=True,
                    has_hook_config=True,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=False,
                    reason="test_hook_runtime",
                ),
            },
        )

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'dir c_jp.py 2>nul || echo "文件不存在"'},
        )

        assert skill is None
        assert weights == {}

    @pytest.mark.asyncio
    async def test_declared_hook_runtime_skill_does_not_take_over_active_business_skill(
        self,
    ):
        """带 hook 配置的 declared skill 不应抢占已存在的业务技能上下文。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "hook-http-demo",
            ["execute_shell_command"],
        )
        context_manager = SkillContextManager()
        detector = SkillInvocationDetector(
            registry=registry,
            context_manager=context_manager,
        )
        detector.set_enabled_skills(["weather", "hook-http-demo"])
        detector.set_skill_runtime_profiles(
            {
                "hook-http-demo": SkillRuntimeProfile(
                    skill_name="hook-http-demo",
                    trace_attributable=True,
                    has_hook_config=True,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=False,
                    reason="test_hook_runtime",
                ),
            },
        )
        await detector.start_skill(
            "weather",
            trigger_tool="read_file",
            trigger_reason="skill_md",
            confidence=1.0,
        )

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'dir c_jp.py 2>nul || echo "文件不存在"'},
        )

        assert skill is None
        assert weights == {}
        assert context_manager.current_skill == "weather"

    @pytest.mark.asyncio
    async def test_declared_non_hook_skill_does_not_bootstrap_without_explicit_evidence(
        self,
    ):
        """非 hook 技能也不能仅凭 declared tools 自动启动。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "weather",
            ["execute_shell_command"],
        )
        detector = SkillInvocationDetector(registry=registry)
        detector.set_enabled_skills(["weather"])
        detector.set_skill_runtime_profiles(
            {
                "weather": SkillRuntimeProfile(
                    skill_name="weather",
                    trace_attributable=True,
                    has_hook_config=False,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=True,
                    reason="test_non_hook_runtime",
                ),
            },
        )

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'curl -s "wttr.in/Beijing?format=3"'},
        )

        assert skill is None
        assert weights == {}

    @pytest.mark.asyncio
    async def test_non_hook_declared_skill_keeps_continuation_after_message_activation(
        self,
    ):
        """显式激活后，非 hook declared skill 仍应持续接管共享工具。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "weather",
            ["execute_shell_command"],
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "weather": SkillFeature(
                    skill_name="weather",
                    trigger_keywords=["weather", "wttr", "天气"],
                ),
            },
        )
        detector = SkillInvocationDetector(
            registry=registry,
            inferencer=inferencer,
        )
        detector.set_enabled_skills(["weather"])
        detector.set_skill_runtime_profiles(
            {
                "weather": SkillRuntimeProfile(
                    skill_name="weather",
                    trace_attributable=True,
                    has_hook_config=False,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=True,
                    reason="test_non_hook_runtime",
                ),
            },
        )

        detected_skill, detected_confidence = (
            detector.detect_from_user_message(
                "请使用 weather 查询天气",
            )
        )
        assert detected_skill == "weather"
        assert detected_confidence >= 0.7

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'curl -s "wttr.in/Beijing?format=3"'},
        )

        assert skill == "weather"
        assert weights.get("weather", 0) >= 0.7

    @pytest.mark.asyncio
    async def test_non_hook_declared_skill_keeps_continuation_after_skill_md_activation(
        self,
        tmp_path,
    ):
        """读取 SKILL.md 显式激活后，非 hook declared skill 应持续接管共享工具。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "weather",
            ["execute_shell_command"],
        )
        detector = SkillInvocationDetector(registry=registry)
        detector.set_enabled_skills(["weather"])
        detector.set_skill_runtime_profiles(
            {
                "weather": SkillRuntimeProfile(
                    skill_name="weather",
                    trace_attributable=True,
                    has_hook_config=False,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=True,
                    reason="test_non_hook_runtime",
                ),
            },
        )

        skill_dir = tmp_path / "weather"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# Weather\n", encoding="utf-8")

        skill1, weights1 = await detector.on_tool_call(
            "read_file",
            {"file_path": str(skill_md)},
        )
        assert skill1 == "weather"
        assert weights1 == {"weather": 1.0}

        skill2, weights2 = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'curl -s "wttr.in/Beijing?format=3"'},
        )
        assert skill2 == "weather"
        assert weights2 == {"weather": 1.0}

    def test_hook_runtime_skill_still_detectable_from_user_message(self):
        """带 hook 配置的技能仍应支持显式消息触发。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "hook-http-demo": SkillFeature(
                    skill_name="hook-http-demo",
                    trigger_keywords=["hook", "hooks.json", "posttooluse"],
                ),
            },
        )
        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["hook-http-demo"])
        detector.set_skill_runtime_profiles(
            {
                "hook-http-demo": SkillRuntimeProfile(
                    skill_name="hook-http-demo",
                    trace_attributable=True,
                    has_hook_config=True,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=False,
                    reason="test_hook_runtime",
                ),
            },
        )

        skill, confidence = detector.detect_from_user_message(
            "请使用 hook-http-demo 展示 hooks.json 的样例",
        )

        assert skill == "hook-http-demo"
        assert confidence > 0

    @pytest.mark.asyncio
    async def test_hook_runtime_skill_tool_hint_cannot_bootstrap_without_explicit_evidence(
        self,
    ):
        """declared 被挡住后，tool hint 也不应再次把 hook skill 启起来。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "hook-http-demo",
            ["execute_shell_command"],
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "hook-http-demo": SkillFeature(
                    skill_name="hook-http-demo",
                    tools_hint=["execute_shell_command"],
                ),
            },
        )
        detector = SkillInvocationDetector(
            registry=registry,
            inferencer=inferencer,
        )
        detector.set_enabled_skills(["hook-http-demo"])
        detector.set_skill_runtime_profiles(
            {
                "hook-http-demo": SkillRuntimeProfile(
                    skill_name="hook-http-demo",
                    trace_attributable=True,
                    has_hook_config=True,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=False,
                    reason="test_hook_runtime",
                ),
            },
        )

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'dir c_jp.py 2>nul || echo "文件不存在"'},
        )

        assert skill is None
        assert weights == {}

    @pytest.mark.asyncio
    async def test_runtime_tool_hint_cannot_bootstrap_without_explicit_evidence(
        self,
    ):
        """通用 runtime tool hint 不应单独启动技能。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "weather": SkillFeature(
                    skill_name="weather",
                    tools_hint=["execute_shell_command"],
                ),
            },
        )
        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["weather"])

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'curl -s "wttr.in/Beijing?format=3"'},
        )

        assert skill is None
        assert weights == {}

    @pytest.mark.asyncio
    async def test_runtime_tool_sequence_cannot_bootstrap_without_explicit_evidence(
        self,
    ):
        """通用 runtime tool sequence 不应单独启动技能。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "weather": SkillFeature(
                    skill_name="weather",
                    tool_patterns=[
                        ["read_file", "execute_shell_command"],
                    ],
                ),
            },
        )
        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["weather"])

        skill1, weights1 = await detector.on_tool_call(
            "read_file",
            {"file_path": "notes.txt"},
        )
        assert skill1 is None
        assert weights1 == {}

        skill2, weights2 = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'curl -s "wttr.in/Beijing?format=3"'},
        )

        assert skill2 is None
        assert weights2 == {}

    def test_hook_runtime_skill_still_detectable_from_skill_md_read(self):
        """带 hook 配置的技能仍应支持通过读取 SKILL.md 显式激活。"""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["hook-http-demo"])
        detector.set_skill_runtime_profiles(
            {
                "hook-http-demo": SkillRuntimeProfile(
                    skill_name="hook-http-demo",
                    trace_attributable=True,
                    has_hook_config=True,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=False,
                    reason="test_hook_runtime",
                ),
            },
        )

        skill = detector._detect_skill_from_skill_md_read(
            "read_file",
            {"file_path": "/workspace/skills/hook-http-demo/SKILL.md"},
        )

        assert skill == "hook-http-demo"

    @pytest.mark.asyncio
    async def test_message_activated_hook_skill_keeps_declared_continuation(
        self,
    ):
        """消息显式激活后的 hook 技能应持续接管共享工具。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "hook-http-demo",
            ["execute_shell_command"],
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "hook-http-demo": SkillFeature(
                    skill_name="hook-http-demo",
                    trigger_keywords=["hook", "hooks.json", "posttooluse"],
                ),
            },
        )
        detector = SkillInvocationDetector(
            registry=registry,
            inferencer=inferencer,
        )
        detector.set_enabled_skills(["hook-http-demo"])
        detector.set_skill_runtime_profiles(
            {
                "hook-http-demo": SkillRuntimeProfile(
                    skill_name="hook-http-demo",
                    trace_attributable=True,
                    has_hook_config=True,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=False,
                    reason="test_hook_runtime",
                ),
            },
        )

        skill0, confidence0 = detector.detect_from_user_message(
            "请使用 hook-http-demo 展示 hooks.json 的样例",
        )
        assert skill0 == "hook-http-demo"
        assert confidence0 > 0

        skill1, weights1 = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "echo first"},
        )
        assert skill1 == "hook-http-demo"
        assert weights1 == {"hook-http-demo": 0.95}

        skill2, weights2 = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "echo second"},
        )
        assert skill2 == "hook-http-demo"
        assert weights2 == {"hook-http-demo": 1.0}

    @pytest.mark.asyncio
    async def test_skill_md_activated_hook_skill_keeps_declared_continuation(
        self,
        tmp_path,
    ):
        """SKILL.md 激活后的 hook 技能应持续接管共享工具。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "hook-http-demo",
            ["execute_shell_command"],
        )
        detector = SkillInvocationDetector(registry=registry)
        detector.set_enabled_skills(["hook-http-demo"])
        detector.set_skill_runtime_profiles(
            {
                "hook-http-demo": SkillRuntimeProfile(
                    skill_name="hook-http-demo",
                    trace_attributable=True,
                    has_hook_config=True,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=False,
                    reason="test_hook_runtime",
                ),
            },
        )

        skill_dir = tmp_path / "hook-http-demo"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# Hook Demo\n", encoding="utf-8")

        skill1, weights1 = await detector.on_tool_call(
            "read_file",
            {"file_path": str(skill_md)},
        )
        assert skill1 == "hook-http-demo"
        assert weights1 == {"hook-http-demo": 1.0}

        skill2, weights2 = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "echo first"},
        )
        assert skill2 == "hook-http-demo"
        assert weights2 == {"hook-http-demo": 1.0}

        skill3, weights3 = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "echo second"},
        )
        assert skill3 == "hook-http-demo"
        assert weights3 == {"hook-http-demo": 1.0}

    @pytest.mark.asyncio
    async def test_multi_skill_attribution(self):
        """Test multi-skill attribution when multiple skills declare tool."""
        registry = SkillToolRegistry()
        registry.register_skill_tools("xlsx", ["read_file"])
        registry.register_skill_tools("pdf", ["read_file"])
        registry.register_skill_tools("docx", ["read_file"])

        detector = SkillInvocationDetector(registry=registry)
        detector.set_enabled_skills(["xlsx", "pdf", "docx"])

        skill, weights = await detector.on_tool_call(
            "read_file",
            {"path": "/data/test.xlsx"},
        )

        # Should attribute to xlsx due to file extension
        assert skill == "xlsx"
        assert "xlsx" in weights
        assert weights["xlsx"] > 0

    @pytest.mark.asyncio
    async def test_skill_context_tracking(self):
        """仅凭 runtime declared 证据不应创建 skill context。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools("xlsx", ["execute_shell_command"])

        context_manager = SkillContextManager()
        detector = SkillInvocationDetector(
            registry=registry,
            context_manager=context_manager,
        )
        detector.set_enabled_skills(["xlsx"])

        await detector.on_tool_call(
            "execute_shell_command",
            {"command": "python process.py"},
        )

        assert context_manager.current_skill is None

    @pytest.mark.asyncio
    async def test_declared_hook_skill_does_not_override_active_skill_in_runtime_behavior(
        self,
    ):
        """hook runtime skill 不应仅凭 declared tools 覆盖当前业务 skill。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "hook-http-demo",
            ["execute_shell_command"],
        )

        context_manager = SkillContextManager()
        detector = SkillInvocationDetector(
            registry=registry,
            context_manager=context_manager,
        )
        detector.set_enabled_skills(["weather", "hook-http-demo"])
        detector.set_skill_runtime_profiles(
            {
                "hook-http-demo": SkillRuntimeProfile(
                    skill_name="hook-http-demo",
                    trace_attributable=True,
                    has_hook_config=True,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=False,
                    reason="test_hook_runtime",
                ),
            },
        )

        await detector.start_skill(
            "weather",
            trigger_tool="read_file",
            trigger_reason="inferred",
            confidence=1.0,
        )

        primary_skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'dir c_jp.py 2>nul || echo "文件不存在"'},
        )

        assert primary_skill is None
        assert weights == {}
        assert context_manager.current_skill == "weather"

    @pytest.mark.asyncio
    async def test_skill_md_continuation_does_not_activate_hook_declared_skill_without_explicit_activation(
        self,
        tmp_path,
    ):
        """其他 skill 的 SKILL.md 激活后，泛工具不应被误记到当前 skill。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "hook-http-demo",
            ["execute_shell_command"],
        )

        context_manager = SkillContextManager()
        detector = SkillInvocationDetector(
            registry=registry,
            context_manager=context_manager,
        )
        detector.set_enabled_skills(["weather", "hook-http-demo"])
        detector.set_skill_runtime_profiles(
            {
                "hook-http-demo": SkillRuntimeProfile(
                    skill_name="hook-http-demo",
                    trace_attributable=True,
                    has_hook_config=True,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=False,
                    reason="test_hook_runtime",
                ),
            },
        )

        weather_dir = tmp_path / "weather"
        weather_dir.mkdir()
        skill_md = weather_dir / "SKILL.md"
        skill_md.write_text("# Weather\n", encoding="utf-8")

        primary_skill, weights = await detector.on_tool_call(
            "read_file",
            {"file_path": str(skill_md)},
        )
        assert primary_skill == "weather"
        assert weights == {"weather": 1.0}
        assert context_manager.current_skill == "weather"

        primary_skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'dir c_jp.py 2>nul || echo "文件不存在"'},
        )

        assert primary_skill is None
        assert weights == {}
        assert context_manager.current_skill == "weather"

    @pytest.mark.asyncio
    async def test_declared_hook_skill_does_not_take_over_when_no_active_skill(
        self,
    ):
        """没有显式证据时，hook runtime skill 不能凭 declared tool 接管。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "hook-http-demo",
            ["execute_shell_command"],
        )

        context_manager = SkillContextManager()
        detector = SkillInvocationDetector(
            registry=registry,
            context_manager=context_manager,
        )
        detector.set_enabled_skills(["hook-http-demo"])
        detector.set_skill_runtime_profiles(
            {
                "hook-http-demo": SkillRuntimeProfile(
                    skill_name="hook-http-demo",
                    trace_attributable=True,
                    has_hook_config=True,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=False,
                    reason="test_hook_runtime",
                ),
            },
        )

        primary_skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'dir c_jp.py 2>nul || echo "文件不存在"'},
        )

        assert primary_skill is None
        assert weights == {}
        assert context_manager.current_skill is None

    @pytest.mark.asyncio
    async def test_active_declared_skill_switches_on_stronger_file_evidence(
        self,
    ):
        """已有 declared-skill 活跃时，明确的新文件证据仍可切换技能。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools("weather", ["execute_shell_command"])

        context_manager = SkillContextManager()
        detector = SkillInvocationDetector(
            registry=registry,
            context_manager=context_manager,
        )
        detector.set_enabled_skills(["weather", "xlsx"])

        await detector.start_skill(
            "weather",
            trigger_tool="execute_shell_command",
            trigger_reason="declared",
            confidence=1.0,
        )

        primary_skill, weights = await detector.on_tool_call(
            "read_file",
            {"file_path": "report.xlsx"},
        )

        assert primary_skill == "xlsx"
        assert weights.get("xlsx", 0) >= 0.8
        assert context_manager.current_skill == "xlsx"

    @pytest.mark.asyncio
    async def test_active_hook_skill_switches_on_stronger_file_evidence(
        self,
    ):
        """hook 技能活跃时，明确的新文件证据不应被旧上下文卡住。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools(
            "hook-http-demo",
            ["execute_shell_command"],
        )

        context_manager = SkillContextManager()
        detector = SkillInvocationDetector(
            registry=registry,
            context_manager=context_manager,
        )
        detector.set_enabled_skills(["hook-http-demo", "xlsx"])
        detector.set_skill_runtime_profiles(
            {
                "hook-http-demo": SkillRuntimeProfile(
                    skill_name="hook-http-demo",
                    trace_attributable=True,
                    has_hook_config=True,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=False,
                    reason="test_hook_runtime",
                ),
            },
        )

        await detector.start_skill(
            "hook-http-demo",
            trigger_tool="read_file",
            trigger_reason="skill_md",
            confidence=1.0,
        )

        primary_skill, weights = await detector.on_tool_call(
            "read_file",
            {"file_path": "report.xlsx"},
        )

        assert primary_skill == "xlsx"
        assert weights.get("xlsx", 0) >= 0.8
        assert context_manager.current_skill == "xlsx"

    @pytest.mark.asyncio
    async def test_restored_confirmed_skill_allows_one_shot_continuation(
        self,
        tmp_path,
    ):
        """从 session 恢复的已确认 skill 仅允许一次无证据续接。"""
        skill_dir = tmp_path / "skills" / "fill-metadata" / "steps"
        skill_dir.mkdir(parents=True)
        (skill_dir / "step1.md").write_text("# step1", encoding="utf-8")
        (skill_dir / "step2.md").write_text("# step2", encoding="utf-8")

        detector = SkillInvocationDetector(workspace_dir=tmp_path)
        detector.set_enabled_skills(["fill-metadata"])
        detector.restore_confirmed_skill(
            "fill-metadata",
            allow_one_shot_continuation=True,
        )

        skill1, weights1 = await detector.on_tool_call(
            "read_file",
            {"file_path": "steps/step1.md"},
        )
        assert skill1 == "fill-metadata"
        assert weights1 == {"fill-metadata": 1.0}

        skill2, weights2 = await detector.on_tool_call(
            "read_file",
            {"file_path": "steps/step2.md"},
        )
        assert skill2 is None
        assert weights2 == {}

    @pytest.mark.asyncio
    async def test_restored_confirmed_skill_does_not_consume_unrelated_shell_command(
        self,
    ):
        """恢复后的 one-shot continuation 不应吞掉明显无关的命令执行。"""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(
            ["fill-metadata", "hook-http-demo", "self-improvement"],
        )
        detector.restore_confirmed_skill(
            "fill-metadata",
            allow_one_shot_continuation=True,
        )

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'dir c_jp.py 2>nul || echo "文件不存在"'},
        )

        assert skill is None
        assert weights == {}

    @pytest.mark.asyncio
    async def test_restored_confirmed_skill_continues_related_step_read(
        self,
        tmp_path,
    ):
        """恢复后的 one-shot continuation 仍应允许同技能步骤文件的续接。"""
        skill_dir = tmp_path / "skills" / "fill-metadata" / "steps"
        skill_dir.mkdir(parents=True)
        (skill_dir / "step1.md").write_text("# step1", encoding="utf-8")

        detector = SkillInvocationDetector(workspace_dir=tmp_path)
        detector.set_enabled_skills(["fill-metadata"])
        detector.restore_confirmed_skill(
            "fill-metadata",
            allow_one_shot_continuation=True,
        )

        skill, weights = await detector.on_tool_call(
            "read_file",
            {"file_path": "steps/step1.md"},
        )

        assert skill == "fill-metadata"
        assert weights == {"fill-metadata": 1.0}

    @pytest.mark.asyncio
    async def test_restored_confirmed_skill_does_not_hijack_unrelated_declared_read_file(
        self,
    ):
        """恢复态 current_skill 不应劫持无关的 generic declared tool。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools("fill-metadata", ["read_file"])

        detector = SkillInvocationDetector(registry=registry)
        detector.set_enabled_skills(["fill-metadata", "xlsx"])
        detector.restore_confirmed_skill(
            "fill-metadata",
            allow_one_shot_continuation=True,
        )

        skill, weights = await detector.on_tool_call(
            "read_file",
            {"file_path": "report.xlsx"},
        )

        assert skill == "xlsx"
        assert weights.get("xlsx", 0) >= 0.8

    @pytest.mark.asyncio
    async def test_unrelated_tool_does_not_consume_pending_continuation(
        self,
        tmp_path,
    ):
        """无关工具不应消费恢复态 pending，后续相关工具仍可正确续接。"""
        skill_dir = tmp_path / "skills" / "fill-metadata" / "steps"
        skill_dir.mkdir(parents=True)
        (skill_dir / "step1.md").write_text("# step1", encoding="utf-8")

        detector = SkillInvocationDetector(workspace_dir=tmp_path)
        detector.set_enabled_skills(["fill-metadata"])
        detector.restore_confirmed_skill(
            "fill-metadata",
            allow_one_shot_continuation=True,
        )

        unrelated_skill, unrelated_weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'dir c_jp.py 2>nul || echo "文件不存在"'},
        )
        related_skill, related_weights = await detector.on_tool_call(
            "read_file",
            {"file_path": "steps/step1.md"},
        )

        assert unrelated_skill is None
        assert unrelated_weights == {}
        assert related_skill == "fill-metadata"
        assert related_weights == {"fill-metadata": 1.0}

    @pytest.mark.asyncio
    async def test_pending_continuation_supports_nested_tool_input_paths(
        self,
        tmp_path,
    ):
        """恢复态 pending 应识别嵌套参数中的 skill 资源路径。"""
        skill_dir = tmp_path / "skills" / "fill-metadata" / "steps"
        skill_dir.mkdir(parents=True)
        (skill_dir / "step1.md").write_text("# step1", encoding="utf-8")

        detector = SkillInvocationDetector(workspace_dir=tmp_path)
        detector.set_enabled_skills(["fill-metadata"])
        detector.restore_confirmed_skill(
            "fill-metadata",
            allow_one_shot_continuation=True,
        )

        skill, weights = await detector.on_tool_call(
            "read_file",
            {"payload": {"paths": ["steps/step1.md"]}},
        )

        assert skill == "fill-metadata"
        assert weights == {"fill-metadata": 1.0}

    @pytest.mark.asyncio
    async def test_mixed_message_does_not_attribute_unrelated_tool(
        self,
        tmp_path,
    ):
        """混合消息中的前置无关工具不应仅因消息命中而归因到技能。"""
        skill_dir = tmp_path / "skills" / "fill-metadata" / "steps"
        skill_dir.mkdir(parents=True)
        (skill_dir / "step1.md").write_text("# step1", encoding="utf-8")

        detector = SkillInvocationDetector(workspace_dir=tmp_path)
        detector.set_enabled_skills(["fill-metadata"])
        detector.restore_confirmed_skill(
            "fill-metadata",
            allow_one_shot_continuation=True,
        )
        detector.detect_from_user_message(
            '先执行命令 dir c_jp.py 2>nul || echo "文件不存在"，然后再读取 '
            "fill-metadata 的 steps/step1.md",
        )

        unrelated_skill, unrelated_weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'dir c_jp.py 2>nul || echo "文件不存在"'},
        )
        related_skill, related_weights = await detector.on_tool_call(
            "read_file",
            {"file_path": "steps/step1.md"},
        )

        assert unrelated_skill is None
        assert unrelated_weights == {}
        assert related_skill == "fill-metadata"
        assert related_weights == {"fill-metadata": 1.0}

    @pytest.mark.asyncio
    async def test_mixed_message_reattributes_later_skill_asset_read(
        self,
        tmp_path,
    ):
        """混合消息里后续明确的 skill 资产读取应能重新命中该技能。"""
        skill_dir = tmp_path / "skills" / "fill-metadata" / "steps"
        skill_dir.mkdir(parents=True)
        (skill_dir / "step1.md").write_text("# step1", encoding="utf-8")

        detector = SkillInvocationDetector(workspace_dir=tmp_path)
        detector.set_enabled_skills(["fill-metadata"])
        detector.detect_from_user_message(
            '先执行命令 dir c_jp.py 2>nul || echo "文件不存在"，然后再读取 '
            "fill-metadata 的 steps/step1.md",
        )

        unrelated_skill, unrelated_weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'dir c_jp.py 2>nul || echo "文件不存在"'},
        )
        related_skill, related_weights = await detector.on_tool_call(
            "read_file",
            {"file_path": "steps/step1.md"},
        )

        assert unrelated_skill is None
        assert unrelated_weights == {}
        assert related_skill == "fill-metadata"
        assert related_weights == {"fill-metadata": 1.0}

    @pytest.mark.asyncio
    async def test_skill_md_lock_does_not_attribute_unrelated_tool(
        self,
        tmp_path,
    ):
        """读取 SKILL.md/步骤文件后，无关命令不应再因 lock 被强制归因。"""
        skill_dir = tmp_path / "skills" / "fill-metadata"
        steps_dir = skill_dir / "steps"
        steps_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "# Fill Metadata\n",
            encoding="utf-8",
        )
        (steps_dir / "step1.md").write_text("# step1", encoding="utf-8")

        detector = SkillInvocationDetector(workspace_dir=tmp_path)
        detector.set_enabled_skills(["fill-metadata"])

        skill1, weights1 = await detector.on_tool_call(
            "read_file",
            {"file_path": str(skill_dir / "SKILL.md")},
        )
        unrelated_skill, unrelated_weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": 'dir c_jp.py 2>nul || echo "文件不存在"'},
        )
        related_skill, related_weights = await detector.on_tool_call(
            "read_file",
            {"file_path": str(steps_dir / "step1.md")},
        )

        assert skill1 == "fill-metadata"
        assert weights1 == {"fill-metadata": 1.0}
        assert unrelated_skill is None
        assert unrelated_weights == {}
        assert related_skill == "fill-metadata"
        assert related_weights == {"fill-metadata": 1.0}

    @pytest.mark.asyncio
    async def test_skill_md_lock_does_not_hijack_unrelated_non_generic_tool(
        self,
        tmp_path,
    ):
        """SKILL.md lock 只能续接 skill 资产，不能吞掉无关非通用工具。"""
        skill_dir = tmp_path / "skills" / "fill-metadata"
        steps_dir = skill_dir / "steps"
        steps_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "# Fill Metadata\n",
            encoding="utf-8",
        )
        (steps_dir / "step1.md").write_text("# step1", encoding="utf-8")

        detector = SkillInvocationDetector(workspace_dir=tmp_path)
        detector.set_enabled_skills(["fill-metadata"])

        skill1, weights1 = await detector.on_tool_call(
            "read_file",
            {"file_path": str(skill_dir / "SKILL.md")},
        )
        unrelated_skill, unrelated_weights = await detector.on_tool_call(
            "mcp_read_file",
            {"path": str(tmp_path / "report.xlsx")},
            mcp_server="filesystem",
        )

        assert skill1 == "fill-metadata"
        assert weights1 == {"fill-metadata": 1.0}
        assert unrelated_skill is None
        assert unrelated_weights == {}

    @pytest.mark.asyncio
    async def test_start_skill_invokes_session_hook_loader_without_tracing(
        self,
    ):
        """Skill hook loading should not depend on trace emission."""
        loaded = []

        async def load_skill_hooks(skill_name: str) -> None:
            loaded.append(skill_name)

        detector = SkillInvocationDetector(
            skill_hook_loader=load_skill_hooks,
        )

        await detector.start_skill(
            "xlsx",
            trigger_tool="user_message",
            trigger_reason="declared",
        )

        assert loaded == ["xlsx"]

    @pytest.mark.asyncio
    async def test_start_skill_invokes_confirmed_skill_callback(
        self,
    ):
        """确认技能后的会话快照回调不应受 tracing 策略影响。"""
        confirmed = []

        async def confirmed_skill(skill_name: str) -> None:
            confirmed.append(skill_name)

        detector = SkillInvocationDetector(
            confirmed_skill_callback=confirmed_skill,
        )

        await detector.start_skill(
            "hook-http-demo",
            trigger_tool="read_file",
            trigger_reason="skill_md",
        )

        assert confirmed == ["hook-http-demo"]

    @pytest.mark.asyncio
    async def test_hook_runtime_skill_start_keeps_loader_and_callback(
        self,
    ):
        """带 hook 配置的技能启动时仍应触发主流程回调。"""
        confirmed = []
        loaded = []

        async def confirmed_skill(skill_name: str) -> None:
            confirmed.append(skill_name)

        async def load_skill_hooks(skill_name: str) -> None:
            loaded.append(skill_name)

        detector = SkillInvocationDetector(
            skill_hook_loader=load_skill_hooks,
            confirmed_skill_callback=confirmed_skill,
        )
        detector.set_skill_runtime_profiles(
            {
                "hook-http-demo": SkillRuntimeProfile(
                    skill_name="hook-http-demo",
                    trace_attributable=True,
                    has_hook_config=True,
                    declared_tools=["execute_shell_command"],
                    declared_tool_bootstrap_allowed=False,
                    reason="test_hook_runtime",
                ),
            },
        )

        await detector.start_skill(
            "hook-http-demo",
            trigger_tool="read_file",
            trigger_reason="skill_md",
        )

        assert confirmed == ["hook-http-demo"]
        assert loaded == ["hook-http-demo"]

    @pytest.mark.asyncio
    async def test_no_attribution_for_unknown_tool(self):
        """Test no attribution for unknown tool."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx"])

        skill, weights = await detector.on_tool_call(
            "unknown_tool_xyz",
            {"data": "something"},
        )

        assert skill is None
        assert weights == {}

    @pytest.mark.asyncio
    async def test_idle_threshold_ends_skill(self):
        """Test that idle threshold ends active skill."""
        registry = SkillToolRegistry()
        registry.register_skill_tools("xlsx", ["read_file"])

        context_manager = SkillContextManager()
        detector = SkillInvocationDetector(
            registry=registry,
            context_manager=context_manager,
            idle_threshold=2,
        )
        detector.set_enabled_skills(["xlsx"])

        # Start skill with declared tool
        await detector.on_tool_call("read_file", {"path": "test.xlsx"})
        assert context_manager.current_skill == "xlsx"

        # Call non-declared tools to increment idle counter
        # The idle counter only increments when current skill is NOT in declared skills
        # For tools not in registry, no attribution happens, so idle counter won't increment
        # This test verifies the skill stays active until reasoning ends
        await detector.on_tool_call("unknown_tool", {})
        # The skill should still be active because the tool call didn't trigger any skill
        # Idle threshold logic only applies when a tool belongs to different skills
        assert context_manager.current_skill == "xlsx"

        # End reasoning to clear skill context
        await detector.on_reasoning_end()
        assert context_manager.current_skill is None

    @pytest.mark.asyncio
    async def test_on_reasoning_end_clears_all(self):
        """Test that on_reasoning_end clears all active skills."""
        context_manager = SkillContextManager()

        detector = SkillInvocationDetector(context_manager=context_manager)
        detector.set_enabled_skills(["xlsx"])

        # Manually push skills
        context_manager.push_skill("xlsx")
        context_manager.push_skill("pdf")

        assert context_manager.skill_depth == 2

        await detector.on_reasoning_end()

        assert context_manager.skill_depth == 0

    def test_reset_detector(self):
        """Test resetting detector state."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx"])
        detector._skill_activation_time["xlsx"] = "some_time"

        detector.reset()

        assert len(detector._skill_activation_time) == 0
        assert len(detector._skill_call_history) == 0

    def test_global_detector(self):
        """Test global detector functions."""
        detector1 = get_skill_invocation_detector()
        detector2 = get_skill_invocation_detector()

        assert detector1 is detector2

        reset_skill_invocation_detector()
        detector3 = get_skill_invocation_detector()

        assert detector3 is not detector1


# =============================================================================
# Integration Tests
# =============================================================================


class TestSkillDetectionIntegration:
    """Integration tests for skill detection flow."""

    @pytest.mark.asyncio
    async def test_full_detection_flow(self):
        """统一证据模型下，弱 runtime 信号只能续接当前技能。"""
        # Setup registry with explicit declarations
        registry = SkillToolRegistry()
        registry.register_skill_tools("xlsx", ["read_file", "write_file"])
        registry.register_skill_tools("pdf", ["read_file"])

        # Setup context manager
        context_manager = SkillContextManager()

        # Setup detector
        detector = SkillInvocationDetector(
            registry=registry,
            context_manager=context_manager,
        )
        detector.set_enabled_skills(["xlsx", "pdf"])

        # Step 1: Call read_file with xlsx file (declared + inferred)
        skill1, weights1 = await detector.on_tool_call(
            "read_file",
            {"path": "/data/report.xlsx"},
        )

        assert skill1 == "xlsx"
        assert "xlsx" in weights1
        assert context_manager.current_skill == "xlsx"

        # Step 2: Call write_file (declared for xlsx only)
        skill2, _ = await detector.on_tool_call(
            "write_file",
            {"path": "/data/output.xlsx"},
        )

        assert skill2 == "xlsx"
        assert context_manager.current_skill == "xlsx"

        # Step 3: 弱关键词不能切走当前技能；若有 runtime 续接则保持当前技能
        skill3, _ = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "convert to pdf"},
        )

        assert skill3 == "xlsx"
        assert context_manager.current_skill == "xlsx"

    @pytest.mark.asyncio
    async def test_custom_skill_feature_inference(self):
        """Test custom skill feature inference."""
        # Create custom feature
        custom_feature = SkillFeature(
            skill_name="image_processor",
            file_extensions=[".png", ".jpg", ".jpeg"],
            keywords=["image", "图片", "photo"],
            tools_hint=["execute_shell_command"],
        )

        # Setup with custom features
        inferencer = SkillFeatureInferencer(
            builtin_features={"image_processor": custom_feature},
        )

        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["image_processor"])

        # Test inference from extension
        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "resize photo.png"},
        )

        assert skill == "image_processor"
        # on_tool_call returns (skill_name, weights_dict)
        # weights dict contains the confidence for the skill
        assert weights.get("image_processor", 0) >= 0.8

    @pytest.mark.asyncio
    async def test_mcp_tool_attribution(self):
        """MCP runtime 证据不能单独启动技能。"""
        registry = SkillToolRegistry()
        registry.register_skill_tools("browser", ["browser_*"])

        detector = SkillInvocationDetector(registry=registry)
        detector.set_enabled_skills(["browser"])

        skill, weights = await detector.on_tool_call(
            "browser_click",
            {"selector": "#submit"},
            mcp_server="puppeteer",
        )

        assert skill is None
        assert weights == {}


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_tool_list(self):
        """Test registering empty tool list."""
        registry = SkillToolRegistry()
        registry.register_skill_tools("empty_skill", [])

        assert registry.skill_count == 0

    def test_duplicate_tool_registration(self):
        """Test registering same tool multiple times."""
        registry = SkillToolRegistry()
        registry.register_skill_tools("skill1", ["read_file"])
        registry.register_skill_tools("skill1", ["read_file", "write_file"])

        # Should overwrite, not merge
        tools = registry.get_tools_for_skill("skill1")
        assert tools == ["read_file", "write_file"]

    @pytest.mark.asyncio
    async def test_empty_enabled_skills(self):
        """Test detection with no enabled skills."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills([])

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "python process.xlsx"},
        )

        assert skill is None
        assert weights == {}

    def test_skill_feature_no_features(self):
        """Test inference with feature having no attributes."""
        feature = SkillFeature(skill_name="empty_feature")
        inferencer = SkillFeatureInferencer(
            builtin_features={"empty_feature": feature},
        )

        skill, confidence = inferencer.infer_skill_from_tool_input(
            "any_tool",
            {"data": "anything"},
            ["empty_feature"],
        )

        assert skill is None
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_concurrent_tool_calls(self):
        """Test handling concurrent tool calls in sequence."""
        registry = SkillToolRegistry()
        registry.register_skill_tools("xlsx", ["read_file"])
        registry.register_skill_tools("pdf", ["read_file"])

        detector = SkillInvocationDetector(registry=registry)
        detector.set_enabled_skills(["xlsx", "pdf"])

        # First call with xlsx file - should start xlsx skill
        skill1, _ = await detector.on_tool_call(
            "read_file",
            {"path": "/data/file.xlsx"},
        )
        assert skill1 == "xlsx"

        # Reset for next call (simulating new conversation)
        detector.reset()

        # Second call with pdf file - should start pdf skill
        skill2, _ = await detector.on_tool_call(
            "read_file",
            {"path": "/data/file.pdf"},
        )
        assert skill2 == "pdf"


# =============================================================================
# Layer 0 User Message Detection Tests
# =============================================================================


class TestUserMessageDetection:
    """Tests for Layer 0 user message detection."""

    def test_detect_from_user_message_with_trigger_keywords(self):
        """Test detection from user message with trigger keywords."""
        # Create a custom feature with trigger keywords
        custom_feature = SkillFeature(
            skill_name="黄金产品问答",
            trigger_keywords=["黄金", "金价", "金条"],
            is_conversational=True,
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={"黄金产品问答": custom_feature},
        )

        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["黄金产品问答"])

        skill, confidence = detector.detect_from_user_message(
            "黄金定期利率多少？",
        )

        assert skill == "黄金产品问答"
        assert confidence >= 0.7

    def test_detect_from_user_message_with_no_match(self):
        """Test detection when user message doesn't match any skill."""
        custom_feature = SkillFeature(
            skill_name="黄金产品问答",
            trigger_keywords=["黄金", "金价"],
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={"黄金产品问答": custom_feature},
        )

        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["黄金产品问答"])

        skill, confidence = detector.detect_from_user_message(
            "今天天气怎么样？",
        )

        assert skill is None
        assert confidence == 0.0

    def test_detect_from_user_message_clears_on_reset(self):
        """Test that reset clears message detection cache."""
        custom_feature = SkillFeature(
            skill_name="test_skill",
            trigger_keywords=["keyword"],
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={"test_skill": custom_feature},
        )

        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["test_skill"])

        # Detect from message
        detector.detect_from_user_message("keyword test")
        assert detector._message_detected_skill == "test_skill"

        # Reset should clear cache
        detector.reset()
        assert detector._message_detected_skill is None
        assert detector._message_detected_confidence == 0.0

    def test_detect_from_user_message_clears_stale_cache_on_miss(self):
        """Test that a message miss clears previous cached detection."""
        custom_feature = SkillFeature(
            skill_name="test_skill",
            trigger_keywords=["keyword"],
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={"test_skill": custom_feature},
        )

        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["test_skill"])

        detector.detect_from_user_message("keyword hit")
        assert detector._message_detected_skill == "test_skill"

        skill, confidence = detector.detect_from_user_message(
            "no related text",
        )

        assert skill is None
        assert confidence == 0.0
        assert detector._message_detected_skill is None
        assert detector._message_detected_confidence == 0.0

    @pytest.mark.asyncio
    async def test_set_enabled_skills_clears_disabled_message_cache(self):
        """Test enabled skill changes clear disabled message detection."""
        inferencer = SkillFeatureInferencer()
        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["xlsx", "pdf"])

        detected_skill, detected_confidence = (
            detector.detect_from_user_message(
                "please use pdf skill",
            )
        )
        assert detected_skill == "pdf"
        assert detected_confidence >= 0.7

        detector.set_enabled_skills(["xlsx"])

        skill, weights = await detector.on_tool_call(
            "unknown_tool",
            {"data": "generic"},
        )

        assert skill is None
        assert weights == {}
        assert detector._message_detected_skill is None
        assert detector._message_detected_confidence == 0.0

    @pytest.mark.asyncio
    async def test_tool_input_evidence_beats_message_cache(self):
        """Test strong tool evidence can override cached message detection."""
        inferencer = SkillFeatureInferencer()
        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["xlsx", "pdf"])

        detected_skill, detected_confidence = (
            detector.detect_from_user_message(
                "please use pdf skill",
            )
        )
        assert detected_skill == "pdf"
        assert detected_confidence >= 0.7

        skill, weights = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "python analyze.py report.xlsx"},
        )

        assert skill == "xlsx"
        assert weights.get("xlsx", 0) >= 0.8


class TestMcpServerInference:
    """Tests for MCP server-based inference."""

    def test_infer_skill_from_mcp_server(self):
        """Test inferring skill from MCP server name."""
        custom_feature = SkillFeature(
            skill_name="filesystem_skill",
            mcp_servers=["filesystem"],
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={"filesystem_skill": custom_feature},
        )

        skill, confidence = inferencer.infer_skill_from_mcp_server(
            "filesystem",
            ["filesystem_skill"],
        )

        assert skill == "filesystem_skill"
        assert confidence >= 0.85

    def test_infer_skill_from_mcp_server_no_match(self):
        """Test MCP server inference with no matching skill."""
        custom_feature = SkillFeature(
            skill_name="filesystem_skill",
            mcp_servers=["filesystem"],
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={"filesystem_skill": custom_feature},
        )

        skill, confidence = inferencer.infer_skill_from_mcp_server(
            "unknown_server",
            ["filesystem_skill"],
        )

        assert skill is None
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_mcp_server_detection_requires_explicit_activation(self):
        """MCP server 只作为 runtime 续接证据，不能单独启动技能。"""
        custom_feature = SkillFeature(
            skill_name="filesystem_skill",
            mcp_servers=["filesystem"],
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={"filesystem_skill": custom_feature},
        )

        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["filesystem_skill"])

        # Call tool with MCP server
        skill, weights = await detector.on_tool_call(
            "mcp_read_file",
            {"path": "/some/path"},
            mcp_server="filesystem",
        )

        assert skill is None
        assert weights == {}

    @pytest.mark.asyncio
    async def test_mcp_server_detection_continues_explicitly_activated_skill(
        self,
    ):
        """显式激活后，MCP server 证据仍可续接当前技能。"""
        custom_feature = SkillFeature(
            skill_name="filesystem_skill",
            mcp_servers=["filesystem"],
            trigger_keywords=["filesystem_skill", "filesystem"],
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={"filesystem_skill": custom_feature},
        )

        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["filesystem_skill"])

        detected_skill, detected_confidence = (
            detector.detect_from_user_message(
                "请使用 filesystem_skill 读取文件",
            )
        )
        assert detected_skill == "filesystem_skill"
        assert detected_confidence >= 0.7

        skill, weights = await detector.on_tool_call(
            "mcp_read_file",
            {"path": "/some/path"},
            mcp_server="filesystem",
        )

        assert skill == "filesystem_skill"
        assert weights.get("filesystem_skill", 0) >= 0.85

    @pytest.mark.asyncio
    async def test_mcp_server_evidence_keeps_higher_priority_than_tool_input(
        self,
    ):
        """多层同时命中时，MCP server 证据优先级应高于 tool input。"""
        inferencer = SkillFeatureInferencer(
            builtin_features={
                "filesystem_skill": SkillFeature(
                    skill_name="filesystem_skill",
                    mcp_servers=["filesystem"],
                    trigger_keywords=["filesystem_skill"],
                ),
                "xlsx": SkillFeature(
                    skill_name="xlsx",
                    file_extensions=[".xlsx"],
                ),
            },
        )

        detector = SkillInvocationDetector(inferencer=inferencer)
        detector.set_enabled_skills(["filesystem_skill", "xlsx"])

        detected_skill, detected_confidence = (
            detector.detect_from_user_message(
                "请使用 filesystem_skill 读取文件",
            )
        )
        assert detected_skill == "filesystem_skill"
        assert detected_confidence >= 0.7

        skill, weights = await detector.on_tool_call(
            "mcp_read_file",
            {"path": "/some/path/report.xlsx"},
            mcp_server="filesystem",
        )

        assert skill == "filesystem_skill"
        assert weights.get("filesystem_skill", 0) >= 0.85


class TestInferencerUserMessageMethods:
    """Tests for SkillFeatureInferencer user message methods."""

    def test_infer_from_user_message_trigger_keywords(self):
        """Test inference with trigger keywords (high confidence)."""
        feature = SkillFeature(
            skill_name="test_skill",
            trigger_keywords=["keyword1", "keyword2"],
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={"test_skill": feature},
        )

        skill, confidence = inferencer.infer_skill_from_user_message(
            "This has keyword1 in it",
            ["test_skill"],
        )

        assert skill == "test_skill"
        assert confidence >= 0.7

    def test_infer_from_user_message_multiple_keywords(self):
        """Test that multiple keyword matches increase confidence."""
        feature = SkillFeature(
            skill_name="test_skill",
            trigger_keywords=["kw1", "kw2", "kw3"],
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={"test_skill": feature},
        )

        # Single keyword match
        _, conf1 = inferencer.infer_skill_from_user_message(
            "kw1 test",
            ["test_skill"],
        )

        # Multiple keyword matches
        _, conf2 = inferencer.infer_skill_from_user_message(
            "kw1 and kw2 and kw3 test",
            ["test_skill"],
        )

        assert conf2 >= conf1

    def test_infer_from_user_message_description_keywords(self):
        """Test inference with description keywords."""
        feature = SkillFeature(
            skill_name="test_skill",
            description_keywords=["finance", "money", "bank"],
            is_conversational=True,
        )
        inferencer = SkillFeatureInferencer(
            builtin_features={"test_skill": feature},
        )

        skill, confidence = inferencer.infer_skill_from_user_message(
            "How do I open a bank account?",
            ["test_skill"],
        )

        assert skill == "test_skill"
        # Description keywords should have lower confidence than trigger keywords
        assert confidence >= 0.4
        assert confidence <= 0.85


class TestSkillMdReadDetection:
    """Test skill detection from SKILL.md file reads."""

    @pytest.mark.asyncio
    async def test_detect_skill_from_skill_md_read(self):
        """Test that reading a SKILL.md file activates the corresponding skill."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx", "pdf", "docx"])

        # 模拟读取xlsx技能的SKILL.md
        skill = detector._detect_skill_from_skill_md_read(
            "read_file",
            {"file_path": "/workspace/skills/xlsx/SKILL.md"},
        )

        assert skill == "xlsx"

    @pytest.mark.asyncio
    async def test_detect_skill_from_skill_md_read_not_enabled(self):
        """Test that reading SKILL.md for non-enabled skill returns None."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx", "pdf"])

        # 尝试读取未启用的技能
        skill = detector._detect_skill_from_skill_md_read(
            "read_file",
            {"file_path": "/workspace/skills/docx/SKILL.md"},
        )

        assert skill is None

    @pytest.mark.asyncio
    async def test_detect_skill_from_skill_md_read_not_skill_md(self):
        """Test that reading non-SKILL.md files returns None."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx"])

        skill = detector._detect_skill_from_skill_md_read(
            "read_file",
            {"file_path": "/workspace/skills/xlsx/README.md"},
        )

        assert skill is None

    @pytest.mark.asyncio
    async def test_detect_skill_from_skill_md_read_wrong_tool(self):
        """Test that non-read_file tools return None."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx"])

        skill = detector._detect_skill_from_skill_md_read(
            "write_file",
            {"file_path": "/workspace/skills/xlsx/SKILL.md"},
        )

        assert skill is None

    @pytest.mark.asyncio
    async def test_detect_skill_from_skill_md_read_empty_path(self):
        """Test that empty file_path returns None."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx"])

        skill = detector._detect_skill_from_skill_md_read(
            "read_file",
            {"file_path": ""},
        )

        assert skill is None

    @pytest.mark.asyncio
    async def test_skill_md_read_activates_skill(self):
        """Test full flow: reading SKILL.md activates the skill."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx", "pdf"])

        # 调用on_tool_call读取SKILL.md
        skill, weights = await detector.on_tool_call(
            "read_file",
            {"file_path": "/workspace/skills/xlsx/SKILL.md"},
        )

        assert skill == "xlsx"
        assert weights == {"xlsx": 1.0}

    @pytest.mark.asyncio
    async def test_skill_md_read_priority_over_other_detection(self):
        """Test that SKILL.md read has highest priority."""
        # 设置一个技能声明使用了read_file工具
        registry = get_skill_tool_registry()
        registry.register_skill_tools("pdf", ["read_file"])

        detector = SkillInvocationDetector(registry=registry)
        detector.set_enabled_skills(["xlsx", "pdf"])

        # pdf声明了read_file，但读取的是xlsx的SKILL.md
        skill, weights = await detector.on_tool_call(
            "read_file",
            {"file_path": "/workspace/skills/xlsx/SKILL.md"},
        )

        # 应该识别为xlsx，而不是pdf
        assert skill == "xlsx"
        assert weights == {"xlsx": 1.0}

    @pytest.mark.asyncio
    async def test_skill_md_read_continues_active_skill_without_new_evidence(
        self,
    ):
        """Test active skill continues after SKILL.md read without new evidence."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["weather"])

        skill1, weights1 = await detector.on_tool_call(
            "read_file",
            {"file_path": "/workspace/skills/weather/SKILL.md"},
        )

        assert skill1 == "weather"
        assert weights1 == {"weather": 1.0}

        skill2, weights2 = await detector.on_tool_call(
            "weather_query",
            {"location": "Shanghai"},
        )

        assert skill2 == "weather"
        assert weights2 == {"weather": 1.0}

    @pytest.mark.asyncio
    async def test_skill_md_read_continuation_only_applies_once(self):
        """SKILL.md 不应把后续无关工具整轮锁死到当前技能。"""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["weather"])

        await detector.on_tool_call(
            "read_file",
            {"file_path": "/workspace/skills/weather/SKILL.md"},
        )

        skill1, weights1 = await detector.on_tool_call(
            "weather_query",
            {"location": "Shanghai"},
        )
        assert skill1 == "weather"
        assert weights1 == {"weather": 1.0}

        skill2, weights2 = await detector.on_tool_call(
            "unknown_tool",
            {"data": "generic"},
        )
        assert skill2 is None
        assert weights2 == {}

    @pytest.mark.asyncio
    async def test_skill_md_read_continuation_expires_after_next_tool_attempt(
        self,
    ):
        """SKILL.md 之后出现更强的新证据时，应允许切换到新技能。"""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["weather", "xlsx"])

        await detector.on_tool_call(
            "read_file",
            {"file_path": "/workspace/skills/weather/SKILL.md"},
        )

        skill1, weights1 = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "python analyze.py report.xlsx"},
        )
        assert skill1 == "xlsx"
        assert weights1.get("xlsx", 0) >= 0.8

        skill2, weights2 = await detector.on_tool_call(
            "unknown_tool",
            {"data": "generic"},
        )
        assert skill2 is None
        assert weights2 == {}

    @pytest.mark.asyncio
    async def test_skill_md_read_continuation_consumed_by_next_same_skill_match(
        self,
    ):
        """同技能强证据仍应正常续接，但不应继续污染后续无关工具。"""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["xlsx"])

        await detector.on_tool_call(
            "read_file",
            {"file_path": "/workspace/skills/xlsx/SKILL.md"},
        )

        skill1, weights1 = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "python analyze.py report.xlsx"},
        )
        assert skill1 == "xlsx"
        assert weights1.get("xlsx", 0) >= 0.8

        skill2, weights2 = await detector.on_tool_call(
            "unknown_tool",
            {"data": "generic"},
        )
        assert skill2 is None
        assert weights2 == {}

    @pytest.mark.asyncio
    async def test_skill_md_continuation_beats_stale_message_cache(self):
        """SKILL.md 不应让旧消息缓存继续污染后续无关工具。"""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["pdf", "xlsx"])

        detected_skill, detected_confidence = (
            detector.detect_from_user_message(
                "please use pdf skill",
            )
        )
        assert detected_skill == "pdf"
        assert detected_confidence >= 0.7

        skill1, weights1 = await detector.on_tool_call(
            "read_file",
            {"file_path": "/workspace/skills/xlsx/SKILL.md"},
        )
        assert skill1 == "xlsx"
        assert weights1 == {"xlsx": 1.0}

        skill2, weights2 = await detector.on_tool_call(
            "unknown_tool",
            {"data": "generic"},
        )
        assert skill2 is None
        assert weights2 == {}

    @pytest.mark.asyncio
    async def test_skill_md_locks_round_primary_skill(self):
        """读取 SKILL.md 后，无关工具不应再被整轮锁定到该技能。"""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["weather", "xlsx", "pdf"])

        skill1, weights1 = await detector.on_tool_call(
            "read_file",
            {"file_path": "/workspace/skills/weather/SKILL.md"},
        )
        assert skill1 == "weather"
        assert weights1 == {"weather": 1.0}

        skill2, weights2 = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "python analyze.py report.xlsx"},
        )
        assert skill2 == "xlsx"
        assert weights2.get("xlsx", 0) >= 0.8

        detector.detect_from_user_message("please use pdf skill")
        skill3, weights3 = await detector.on_tool_call(
            "unknown_tool",
            {"data": "generic"},
        )
        assert skill3 is None
        assert weights3 == {}

    @pytest.mark.asyncio
    async def test_set_enabled_skills_clears_locked_skill_when_disabled(self):
        """Test locked skill is cleared when it is no longer enabled."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["weather", "xlsx"])

        skill1, weights1 = await detector.on_tool_call(
            "read_file",
            {"file_path": "/workspace/skills/weather/SKILL.md"},
        )
        assert skill1 == "weather"
        assert weights1 == {"weather": 1.0}

        detector.set_enabled_skills(["xlsx"])

        skill2, weights2 = await detector.on_tool_call(
            "execute_shell_command",
            {"command": "python analyze.py report.xlsx"},
        )
        assert skill2 == "xlsx"
        assert weights2.get("xlsx", 0) >= 0.8
        assert detector._context_manager.current_skill == "xlsx"
        assert detector._context_manager.active_skills == ["xlsx"]

    @pytest.mark.asyncio
    async def test_set_enabled_skills_clears_disabled_active_context(self):
        """Test enabled skill changes also clear disabled active contexts."""
        detector = SkillInvocationDetector()
        detector.set_enabled_skills(["weather", "xlsx"])

        skill1, weights1 = await detector.on_tool_call(
            "read_file",
            {"file_path": "/workspace/skills/weather/SKILL.md"},
        )
        assert skill1 == "weather"
        assert weights1 == {"weather": 1.0}
        assert detector._context_manager.current_skill == "weather"

        detector.set_enabled_skills(["xlsx"])

        assert detector._context_manager.current_skill is None
        assert detector._context_manager.active_skills == []

    @pytest.mark.asyncio
    async def test_set_enabled_skills_ends_disabled_skill_tracing(self):
        """Test disabling an active skill still closes its tracing span."""
        trace_manager = AsyncMock()
        trace_manager.emit_skill_invocation = AsyncMock(
            return_value="span-weather",
        )
        trace_manager.end_skill_invocation = AsyncMock()

        detector = SkillInvocationDetector(trace_manager=trace_manager)
        detector.set_tracing_context(
            trace_manager,
            "trace-1",
            "user-1",
            "session-1",
            "console",
            "source-1",
        )
        detector.set_enabled_skills(["weather", "xlsx"])

        skill1, weights1 = await detector.on_tool_call(
            "read_file",
            {"file_path": "/workspace/skills/weather/SKILL.md"},
        )
        assert skill1 == "weather"
        assert weights1 == {"weather": 1.0}

        detector._context_manager.record_tool_call("read_file")
        detector.set_enabled_skills(["xlsx"])
        await asyncio.sleep(0)

        trace_manager.end_skill_invocation.assert_awaited_once()
        assert (
            trace_manager.end_skill_invocation.await_args.kwargs["trace_id"]
            == "trace-1"
        )
        assert (
            trace_manager.end_skill_invocation.await_args.kwargs["span_id"]
            == "span-weather"
        )

    def test_reset_flushes_pending_pruned_context_tracing(self):
        """Test reset drains deferred pruned contexts before clearing state."""
        trace_manager = AsyncMock()
        trace_manager.end_skill_invocation = AsyncMock()

        detector = SkillInvocationDetector(trace_manager=trace_manager)
        detector.set_tracing_context(
            trace_manager,
            "trace-1",
            "user-1",
            "session-1",
            "console",
            "source-1",
        )
        detector._pending_pruned_contexts = [
            SkillExecutionContext(
                skill_name="weather",
                start_time=datetime.now(),
                tools_called=["read_file"],
                span_id="span-weather",
            ),
        ]

        detector.reset()

        trace_manager.end_skill_invocation.assert_awaited_once()
        assert (
            trace_manager.end_skill_invocation.await_args.kwargs["trace_id"]
            == "trace-1"
        )
        assert (
            trace_manager.end_skill_invocation.await_args.kwargs["span_id"]
            == "span-weather"
        )
        assert detector._pending_pruned_contexts == []

    @pytest.mark.asyncio
    async def test_set_tracing_context_updates_source_id_for_emitted_skill(
        self,
    ):
        """Test tracing context update reuses source_id in skill spans."""
        trace_manager = AsyncMock()
        trace_manager.emit_skill_invocation = AsyncMock(
            return_value="span-1",
        )
        detector = SkillInvocationDetector(trace_manager=trace_manager)
        detector.set_enabled_skills(["xlsx"])
        detector.set_tracing_context(
            trace_manager,
            "trace-1",
            "user-1",
            "session-1",
            "console",
            "source-1",
        )

        await detector.start_skill(
            "xlsx",
            trigger_tool="user_message",
            trigger_reason="declared",
        )

        trace_manager.emit_skill_invocation.assert_awaited_once()
        assert (
            trace_manager.emit_skill_invocation.await_args.kwargs["source_id"]
            == "source-1"
        )
