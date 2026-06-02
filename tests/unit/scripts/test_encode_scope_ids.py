# -*- coding: utf-8 -*-
"""scope 编码脚本的回归测试。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_script_module():
    """按文件路径加载脚本模块，避免依赖 scripts 成为包。"""
    script_path = (
        Path(__file__).resolve().parents[3] / "scripts" / "encode_scope_ids.py"
    )
    spec = importlib.util.spec_from_file_location(
        "encode_scope_ids",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_encode_scope_id_returns_canonical_scope() -> None:
    """tenant/source 应能编码为 canonical scope。"""
    module = _load_script_module()

    encoded = module.encode_canonical_scope_id("tenant-a", "source-a")

    assert encoded.tenant_id == "tenant-a"
    assert encoded.source_id == "source-a"
    assert encoded.scope_id == "dGVuYW50LWE.c291cmNlLWE"


def test_parse_identity_ids_supports_comma_separated_input() -> None:
    """批量参数应支持逗号分隔并忽略两侧空白。"""
    module = _load_script_module()

    assert module.parse_identity_ids(
        "tenant-a, source-a",
        "tenant_ids",
    ) == ("tenant-a", "source-a")


def test_parse_identity_ids_rejects_empty_values() -> None:
    """空字符串必须被拒绝，避免生成非法 scope。"""
    module = _load_script_module()

    with pytest.raises(ValueError):
        module.parse_identity_ids("tenant-a, ", "tenant_ids")
