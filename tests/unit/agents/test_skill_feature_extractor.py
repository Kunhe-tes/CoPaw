# -*- coding: utf-8 -*-
"""Unit tests for skill_feature_extractor module."""

# pylint: disable=protected-access, redefined-outer-name

import pytest

from swe.agents.skill_feature_extractor import (
    ExtractedSkillFeatures,
    SkillFeatureExtractor,
    get_skill_feature_extractor,
    reset_skill_feature_extractor,
)
from swe.agents.skill_feature_inferencer import (
    SkillFeature,
    reset_skill_feature_inferencer,
)


@pytest.fixture
def extractor():
    """Create a fresh extractor for each test."""
    return SkillFeatureExtractor()


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global instances before and after each test."""
    reset_skill_feature_extractor()
    reset_skill_feature_inferencer()
    yield
    reset_skill_feature_extractor()
    reset_skill_feature_inferencer()


class TestExtractedSkillFeatures:
    """Tests for ExtractedSkillFeatures dataclass."""

    def test_default_values(self):
        """Test default values are empty lists/False."""
        features = ExtractedSkillFeatures()
        assert features.trigger_keywords == []
        assert features.description_keywords == []
        assert features.file_extensions == []
        assert features.mcp_servers == []
        assert features.uses_tools == []
        assert features.is_conversational is False
        assert features.source == "extracted"

    def test_custom_values(self):
        """Test custom values are preserved."""
        features = ExtractedSkillFeatures(
            trigger_keywords=["黄金", "金价"],
            file_extensions=[".xlsx"],
            mcp_servers=["filesystem"],
            is_conversational=True,
        )
        assert features.trigger_keywords == ["黄金", "金价"]
        assert features.file_extensions == [".xlsx"]
        assert features.mcp_servers == ["filesystem"]
        assert features.is_conversational is True


class TestSkillFeatureExtractor:
    """Tests for SkillFeatureExtractor class."""

    def test_directory_listing_extensions_should_not_be_input_features(
        self,
        extractor,
    ):
        """目录结构和脚本文件名不应被当作技能输入文件特征。"""
        content = """---
name: fill-metadata
description: 补全Excel文件中缺失的表元数据和字段元数据的中文名。
---

## 目录结构

```text
fill-metadata/
├── scripts/
│   ├── fill.py
│   ├── verify.py
│   └── ex_index.json
└── steps/
    └── step0.md
```

## 输入文件格式要求

Excel文件应包含表名和字段中文名列。
"""
        features = extractor.extract_from_content(content, "fill-metadata")

        assert ".py" not in features.file_extensions
        assert ".json" not in features.file_extensions
        assert ".md" not in features.file_extensions

    def test_code_block_script_paths_should_not_be_input_features(
        self,
        extractor,
    ):
        """命令示例中的脚本路径不应被当作输入文件特征。"""
        content = """---
name: fill-metadata
description: 补全Excel文件中的字段中文名。
---

## 使用方法

```bash
python scripts/fill.py --input demo.xlsx --index scripts/ex_index.json
python scripts/verify.py --input demo.xlsx
```
"""
        features = extractor.extract_from_content(content, "fill-metadata")

        assert ".py" not in features.file_extensions
        assert ".json" not in features.file_extensions
        assert ".xlsx" in features.file_extensions

    def test_natural_language_file_extensions_are_still_extracted(
        self,
        extractor,
    ):
        """正文里明确声明的输入文件扩展名仍应保留。"""
        content = """---
name: document-skill
description: 处理办公文档。
---

该技能处理 .xlsx 文件和 .pdf 文档，并输出汇总结果。
"""
        features = extractor.extract_from_content(content, "document-skill")

        assert ".xlsx" in features.file_extensions
        assert ".pdf" in features.file_extensions

    def test_english_reads_prose_keeps_input_extensions(
        self,
        extractor,
    ):
        """普通英文描述中的 reads/handles 不应被误判为实现说明。"""
        content = """---
name: pdf-reader
description: Read uploaded documents.
---

This skill reads .pdf files and handles .docx inputs from users.
"""
        features = extractor.extract_from_content(content, "pdf-reader")

        assert ".pdf" in features.file_extensions
        assert ".docx" in features.file_extensions

    def test_script_explanation_section_should_not_treat_impl_files_as_input(
        self,
        extractor,
    ):
        """脚本说明区中的实现文件不应污染输入文件特征。"""
        content = """---
name: fill-metadata
description: 补全Excel文件中的字段中文名。
---

## 脚本说明

### scripts/fill.py

填充脚本，用于读取 Excel 文件。

### scripts/ex_index.json

索引配置文件，供脚本执行时使用。

## 输入文件格式要求

输入为 .xlsx 文件。
"""
        features = extractor.extract_from_content(content, "fill-metadata")

        assert ".py" not in features.file_extensions
        assert ".json" not in features.file_extensions
        assert ".xlsx" in features.file_extensions

    def test_actual_fill_metadata_skill_keeps_python_as_observed_only(
        self,
        extractor,
    ):
        """真实 fill-metadata 文案中的实现脚本不应进入输入扩展名。"""
        content = """---
name: fill-metadata
description: 补全Excel文件中缺失的表元数据和字段元数据的中文名。当用户需要处理包含元数据缺失的Excel文件、补全中文名称、修复表字段信息时使用此技能。触发词：补全元数据、填充中文名、修复Excel元数据、表字段缺失、字段中文名补全。
---

## 目录结构

```text
fill-metadata/
├── scripts/
│   ├── ex_index.json
│   ├── fill.py
│   ├── merge.py
│   ├── validata.py
│   └── verify.py
└── steps/
    ├── step0.md
    ├── step1.md
    └── step2.md
```

## 使用步骤

### Step 1: 执行填充

阅读 `steps/step1.md` 了解如何使用填充脚本补全元数据。

## 脚本说明

### scripts/fill.py

填充脚本，用于读取Excel文件并根据索引配置补全缺失的中文名。

**使用方法：**

```bash
python scripts/fill.py --input <excel_file> --index scripts/ex_index.json --output <output_file>
```

**参数说明：**
- `--input`: 输入的Excel文件路径
- `--index`: 索引配置文件路径
- `--output`: 输出的Excel文件路径（可选，默认覆盖原文件）
"""
        features = extractor.extract_from_content(content, "fill-metadata")

        assert ".py" not in features.file_extensions
        assert ".json" not in features.file_extensions
        assert ".md" not in features.file_extensions
        assert ".py" in features.observed_file_extensions
        assert ".json" in features.observed_file_extensions
        assert ".md" in features.observed_file_extensions

    def test_ip_address_should_not_produce_fake_extensions(
        self,
        extractor,
    ):
        """IP 地址和端口片段不应生成 .0/.1 这类伪扩展名。"""
        content = """---
name: hook-http-demo
description: hook demo
---

回调地址为 http://127.0.0.1:9000/hooks/mcp-posttool
"""
        features = extractor.extract_from_content(content, "hook-http-demo")

        assert ".0" not in features.file_extensions
        assert ".1" not in features.file_extensions
        assert ".0" not in features.observed_file_extensions
        assert ".1" not in features.observed_file_extensions

    def test_reference_urls_and_repo_suffixes_should_not_be_input_features(
        self,
        extractor,
    ):
        """安装链接和仓库后缀不应被识别成输入文件特征。"""
        content = """---
name: self-improvement
description: 记录经验
---

## Installation

```bash
git clone https://github.com/example/project.git ~/.skills/project
```

Follow the spec at https://agentskills.io/specification .
"""
        features = extractor.extract_from_content(content, "self-improvement")

        assert ".com" not in features.file_extensions
        assert ".git" not in features.file_extensions
        assert ".io" not in features.file_extensions

    def test_placeholder_and_example_extensions_should_not_be_input_features(
        self,
        extractor,
    ):
        """占位示例和缩写片段不应被识别成输入文件特征。"""
        content = """---
name: self-improvement
description: 记录经验
---

## Metadata

- Related Files: path/to/file.ext
- Example IDs: e.g. `001`, `A7B`
- Lock file is `pnpm-lock.yaml`
"""
        features = extractor.extract_from_content(content, "self-improvement")

        assert ".ext" not in features.file_extensions
        assert ".g" not in features.file_extensions
        assert ".yaml" not in features.file_extensions

    def test_internal_log_file_listings_should_not_be_input_features(
        self,
        extractor,
    ):
        """内部工作文件清单不应被识别成用户输入文件特征。"""
        content = """---
name: self-improvement
description: 记录经验
---

## Create learning files

- `LEARNINGS.md` - corrections and best practices
- `ERRORS.md` - command failures
- `FEATURE_REQUESTS.md` - capability requests
"""
        features = extractor.extract_from_content(content, "self-improvement")

        assert ".md" not in features.file_extensions
        assert ".md" in features.observed_file_extensions

    def test_extract_trigger_keywords_explicit(self, extractor):
        """Test extraction of explicit trigger keywords from section."""
        content = """---
name: 测试技能
description: 测试技能描述
---

## 触发关键词

- 黄金、金价、金子、贵金属
- 实物金、金条、金币
"""
        features = extractor.extract_from_content(content, "test_skill")
        assert "黄金" in features.trigger_keywords
        assert "金价" in features.trigger_keywords
        assert "金子" in features.trigger_keywords
        assert "贵金属" in features.trigger_keywords
        assert "实物金" in features.trigger_keywords
        assert "金条" in features.trigger_keywords
        assert "金币" in features.trigger_keywords

    def test_extract_trigger_keywords_with_english_header(self, extractor):
        """Test extraction with English header."""
        content = """---
name: Test Skill
---

## Trigger Keywords

- excel, spreadsheet, table
"""
        features = extractor.extract_from_content(content, "test_skill")
        assert "excel" in features.trigger_keywords
        assert "spreadsheet" in features.trigger_keywords
        assert "table" in features.trigger_keywords

    def test_extract_description_keywords_chinese(self, extractor):
        """Test extraction of keywords from Chinese description."""
        content = """---
name: 黄金产品问答
description: 黄金产品问答技能。当客户询问黄金投资、黄金产品、金价等相关问题时触发。
---
"""
        features = extractor.extract_from_content(content, "test_skill")
        # Should contain Chinese keywords from description
        assert len(features.description_keywords) > 0
        # Check that some expected keywords are present
        keywords_str = " ".join(features.description_keywords)
        assert "黄金" in keywords_str or "金价" in keywords_str

    def test_extract_description_keywords_english(self, extractor):
        """Test extraction of keywords from English description."""
        content = """---
name: Excel Skill
description: A skill for processing Excel spreadsheets and CSV files.
---
"""
        features = extractor.extract_from_content(content, "test_skill")
        # Should contain English keywords
        assert "excel" in features.description_keywords
        assert "spreadsheets" in features.description_keywords
        assert "csv" in features.description_keywords

    def test_extract_file_extensions(self, extractor):
        """Test extraction of file extensions from content."""
        content = """---
name: Document Skill
---

This skill processes .xlsx files and .pdf documents.
Also handles .docx and .csv formats.
"""
        features = extractor.extract_from_content(content, "test_skill")
        assert ".xlsx" in features.file_extensions
        assert ".pdf" in features.file_extensions
        assert ".docx" in features.file_extensions
        assert ".csv" in features.file_extensions

    def test_extract_mcp_servers(self, extractor):
        """Test extraction of MCP server names from content."""
        content = """---
name: File Skill
---

Uses mcp_server: filesystem for file operations.
Also connects to server_name: "github" for repository access.
"""
        features = extractor.extract_from_content(content, "test_skill")
        assert "filesystem" in features.mcp_servers
        assert "github" in features.mcp_servers

    def test_extract_uses_tools_from_metadata(self, extractor):
        """Test extraction of uses_tools from frontmatter metadata."""
        content = """---
name: Test Skill
metadata:
  swe:
    uses_tools:
      - read_file
      - execute_shell_command
---
"""
        features = extractor.extract_from_content(content, "test_skill")
        assert "read_file" in features.uses_tools
        assert "execute_shell_command" in features.uses_tools

    def test_determine_conversational_with_trigger_keywords(self, extractor):
        """Test conversational detection with trigger keywords."""
        features = ExtractedSkillFeatures(
            trigger_keywords=["黄金", "金价"],
        )
        is_conv = extractor._determine_conversational(features)
        assert is_conv is True

    def test_determine_conversational_with_keywords_no_extensions(
        self,
        extractor,
    ):
        """Test conversational detection with keywords but no extensions."""
        features = ExtractedSkillFeatures(
            description_keywords=["黄金", "投资"],
            file_extensions=[],
            mcp_servers=[],
            uses_tools=[],
        )
        is_conv = extractor._determine_conversational(features)
        assert is_conv is True

    def test_determine_not_conversational_with_extensions(self, extractor):
        """Test non-conversational detection with file extensions."""
        features = ExtractedSkillFeatures(
            description_keywords=["excel"],
            file_extensions=[".xlsx"],
        )
        is_conv = extractor._determine_conversational(features)
        assert is_conv is False

    def test_build_skill_feature_basic(self, extractor):
        """Test building SkillFeature from extracted features."""
        extracted = ExtractedSkillFeatures(
            trigger_keywords=["黄金", "金价"],
            file_extensions=[".xlsx"],
            mcp_servers=["filesystem"],
            is_conversational=True,
        )
        feature = extractor.build_skill_feature("test_skill", extracted)

        assert feature.skill_name == "test_skill"
        assert feature.trigger_keywords == ["黄金", "金价"]
        assert feature.file_extensions == [".xlsx"]
        assert feature.mcp_servers == ["filesystem"]
        assert feature.is_conversational is True
        assert feature.keywords == [
            "黄金",
            "金价",
        ]  # Uses trigger_keywords as keywords

    def test_build_skill_feature_merge_existing(self, extractor):
        """Test merging with existing SkillFeature."""
        existing = SkillFeature(
            skill_name="test_skill",
            file_extensions=[".xls"],
            keywords=["excel"],
            tools_hint=["read_file"],
            mcp_servers=["old_server"],
        )

        extracted = ExtractedSkillFeatures(
            file_extensions=[".xlsx"],
            trigger_keywords=["表格"],
            uses_tools=["write_file"],
            mcp_servers=["filesystem"],
        )

        feature = extractor.build_skill_feature(
            "test_skill",
            extracted,
            existing,
        )

        # Should merge extensions
        assert ".xls" in feature.file_extensions
        assert ".xlsx" in feature.file_extensions

        # Should merge keywords
        assert "excel" in feature.keywords
        assert "表格" in feature.keywords

        # Should merge tools_hint
        assert "read_file" in feature.tools_hint
        assert "write_file" in feature.tools_hint

        # Should merge MCP servers
        assert "old_server" in feature.mcp_servers
        assert "filesystem" in feature.mcp_servers

    def test_extract_full_skill_md(self, extractor):
        """Test full extraction from a realistic SKILL.md."""
        content = """---
name: 黄金产品问答
description: 黄金产品问答技能。当客户询问黄金投资、黄金产品（实物金、黄金账户、金生利、黄金基金）、金价、黄金交易规则等相关问题时触发，提供专业的黄金产品咨询服务。

---

# 黄金产品问答

你是招商银行的零售客户经理，基于黄金知识库和数据库内容，解答客户关于黄金产品的各种问题。

## 触发关键词

- 黄金、金价、金子、贵金属
- 实物金、金条、金币、金饰
- 黄金账户、黄金活期、黄金定期
- 金生利、生息黄金
- 黄金基金、黄金ETF
"""
        features = extractor.extract_from_content(content, "黄金产品问答")

        # Check trigger keywords
        assert "黄金" in features.trigger_keywords
        assert "金价" in features.trigger_keywords
        assert "实物金" in features.trigger_keywords
        assert "黄金账户" in features.trigger_keywords
        assert "金生利" in features.trigger_keywords
        assert "黄金基金" in features.trigger_keywords

        # Should be marked as conversational
        assert features.is_conversational is True

        # Should have description keywords
        assert len(features.description_keywords) > 0


class TestGlobalExtractor:
    """Tests for global extractor functions."""

    def test_get_skill_feature_extractor_returns_instance(self):
        """Test that get_skill_feature_extractor returns an instance."""
        extractor = get_skill_feature_extractor()
        assert isinstance(extractor, SkillFeatureExtractor)

    def test_get_skill_feature_extractor_returns_same_instance(self):
        """Test that global extractor is singleton."""
        extractor1 = get_skill_feature_extractor()
        extractor2 = get_skill_feature_extractor()
        assert extractor1 is extractor2

    def test_reset_skill_feature_extractor(self):
        """Test that reset clears the global instance."""
        extractor1 = get_skill_feature_extractor()
        reset_skill_feature_extractor()
        extractor2 = get_skill_feature_extractor()
        assert extractor1 is not extractor2


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_content(self, extractor):
        """Test extraction from empty content."""
        features = extractor.extract_from_content("", "test_skill")
        assert features.trigger_keywords == []
        assert features.description_keywords == []
        assert features.file_extensions == []
        assert features.mcp_servers == []

    def test_no_frontmatter(self, extractor):
        """Test extraction from content without frontmatter."""
        content = """# Test Skill

## 触发关键词

- test, demo
"""
        features = extractor.extract_from_content(content, "test_skill")
        assert "test" in features.trigger_keywords
        assert "demo" in features.trigger_keywords

    def test_malformed_frontmatter(self, extractor):
        """Test extraction with malformed frontmatter."""
        content = """---
name: Test
invalid yaml content
---

## 触发关键词

- keyword
"""
        # Should not raise, but fall back gracefully
        features = extractor.extract_from_content(content, "test_skill")
        # Trigger keywords should still be extracted from body
        assert "keyword" in features.trigger_keywords

    def test_trigger_keywords_various_separators(self, extractor):
        """Test trigger keywords with various Chinese separators."""
        content = """---
name: Test
---

## 触发关键词

- 关键词1，关键词2、关键词3；关键词4
- 关键词5, 关键词6
"""
        features = extractor.extract_from_content(content, "test_skill")
        assert "关键词1" in features.trigger_keywords
        assert "关键词2" in features.trigger_keywords
        assert "关键词3" in features.trigger_keywords
        assert "关键词4" in features.trigger_keywords
        assert "关键词5" in features.trigger_keywords
        assert "关键词6" in features.trigger_keywords

    def test_min_keyword_length_filter(self):
        """Test that short keywords are filtered."""
        extractor = SkillFeatureExtractor(min_keyword_length=3)
        content = """---
name: Test
---

## 触发关键词

- ab
- abc
- abcd
"""
        features = extractor.extract_from_content(content, "test_skill")
        assert "ab" not in features.trigger_keywords
        assert "abc" in features.trigger_keywords
        assert "abcd" in features.trigger_keywords

    def test_max_keywords_limit(self):
        """Test that keywords are limited to max_keywords."""
        extractor = SkillFeatureExtractor(max_keywords=5)
        # Description with many Chinese characters
        content = """---
name: Test
description: 一二三四五六七八九十
---
"""
        features = extractor.extract_from_content(content, "test_skill")
        assert len(features.description_keywords) <= 5
