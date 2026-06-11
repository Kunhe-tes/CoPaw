# -*- coding: utf-8 -*-
"""Regression tests for providers package exports."""

import importlib
import sys

import pytest


def test_provider_manager_lazy_export_resolves_class():
    """ProviderManager package export should resolve to the concrete class."""
    pytest.importorskip("agentscope")
    from swe.providers import ProviderManager

    assert ProviderManager is not None
    assert ProviderManager.__name__ == "ProviderManager"


def test_importing_provider_models_does_not_require_agentscope():
    """导入 providers.models 时不应被完整 Provider 栈阻塞。"""
    for module_name in (
        "swe.providers",
        "swe.providers.models",
        "swe.providers.provider",
    ):
        sys.modules.pop(module_name, None)

    module = importlib.import_module("swe.providers.models")

    assert module.ModelSlotConfig is not None
