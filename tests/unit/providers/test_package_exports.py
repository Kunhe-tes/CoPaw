# -*- coding: utf-8 -*-
"""Regression tests for providers package exports."""

import subprocess
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
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from swe.providers.models import ModelSlotConfig; "
                "assert ModelSlotConfig is not None; "
                "assert not any(name == 'agentscope' or "
                "name.startswith('agentscope.') for name in sys.modules)"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
