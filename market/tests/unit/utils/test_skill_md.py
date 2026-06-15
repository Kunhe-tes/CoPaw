# -*- coding: utf-8 -*-
"""SKILL.md frontmatter 工具单元测试."""

from __future__ import annotations

from market.utils.skill_md import (
    extract_metadata,
    extract_version,
    parse_frontmatter,
)

SAMPLE_MD = """---
name: 测试技能
description: 一个测试用的技能
version: "1.2.3"
chinese_name: 测试
---

# 测试技能

正文内容。
"""

SAMPLE_MD_NO_VERSION = """---
name: no_version_skill
description: ""
---

正文。
"""

SAMPLE_MD_V_PREFIX = """---
name: prefix_skill
version: v2.0.0
---

正文。
"""


class TestParseFrontmatter:
    def test_basic(self):
        fm = parse_frontmatter(SAMPLE_MD)
        assert fm["name"] == "测试技能"
        assert fm["description"] == "一个测试用的技能"
        assert fm["version"] == "1.2.3"
        assert fm["chinese_name"] == "测试"

    def test_no_frontmatter(self):
        fm = parse_frontmatter("# Just a heading\n\nNo fm.")
        assert fm == {}

    def test_empty_input(self):
        assert parse_frontmatter("") == {}


class TestExtractVersion:
    def test_quoted(self):
        assert extract_version(SAMPLE_MD) == "1.2.3"

    def test_no_version(self):
        assert extract_version(SAMPLE_MD_NO_VERSION) == ""

    def test_v_prefix(self):
        assert extract_version(SAMPLE_MD_V_PREFIX) == "2.0.0"

    def test_no_frontmatter(self):
        assert extract_version("plain text") == ""

    def test_empty_input(self):
        assert extract_version("") == ""


class TestExtractMetadata:
    def test_returns_known_keys(self):
        meta = extract_metadata(SAMPLE_MD)
        assert meta["name"] == "测试技能"
        assert meta["description"] == "一个测试用的技能"
        assert meta["version"] == "1.2.3"
        assert meta["chinese_name"] == "测试"

    def test_missing_keys_return_empty_string(self):
        meta = extract_metadata(SAMPLE_MD_NO_VERSION)
        assert meta["name"] == "no_version_skill"
        assert meta["description"] == ""
        assert meta["version"] == ""
        assert meta["chinese_name"] == ""
