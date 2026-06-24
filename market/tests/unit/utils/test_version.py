# -*- coding: utf-8 -*-
"""版本号工具单元测试."""

from __future__ import annotations

import pytest

from market.utils.version import bump_patch, normalize_version


class TestBumpPatch:
    def test_three_part(self):
        assert bump_patch("1.0.0") == "1.0.1"
        assert bump_patch("1.0.8") == "1.0.9"
        assert bump_patch("2.13.99") == "2.13.100"

    def test_two_part(self):
        # 1.5 → 1.5.1（与 service.py 现行 _bump_patch 行为一致）
        assert bump_patch("1.5") == "1.5.1"

    def test_invalid_format_appends_one(self):
        assert bump_patch("foo") == "foo.1"
        # 三段式但 patch 非整数 → 退化为 "<version>.1"
        assert bump_patch("1.0.a") == "1.0.a.1"

    def test_empty_string(self):
        assert bump_patch("") == ".1"


class TestNormalizeVersion:
    def test_strip_v_prefix(self):
        assert normalize_version("v1.0.0") == "1.0.0"
        assert normalize_version("V2.3.4") == "2.3.4"

    def test_strip_quotes(self):
        assert normalize_version('"1.2.3"') == "1.2.3"
        assert normalize_version("'1.2.3'") == "1.2.3"

    def test_strip_quotes_and_v(self):
        assert normalize_version('"v1.2.3"') == "1.2.3"

    def test_strip_whitespace(self):
        assert normalize_version("  1.0.0  ") == "1.0.0"

    def test_empty(self):
        assert normalize_version("") == ""
