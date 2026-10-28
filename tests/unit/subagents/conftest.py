# -*- coding: utf-8 -*-
"""Test-owned definitions for runtime tests independent of shipped experts."""

import pytest

from swe.app.subagents.builtins import _builtin
from swe.app.subagents.registry import InMemoryDefinitionProvider


@pytest.fixture
def sample_builtin_definition():
    return _builtin(
        name="plan-researcher",
        description="Test researcher",
        instruction="Inspect the repository without modifying it.",
        trigger_keywords=["plan", "research"],
    )


@pytest.fixture(autouse=True)
def _runtime_test_definitions(request, monkeypatch):
    if request.module.__name__.rsplit(".", 1)[-1] not in {
        "test_background_tools",
        "test_background_worker",
        "test_runtime_and_delegation",
    }:
        return

    definition = request.getfixturevalue("sample_builtin_definition")

    def provider():
        return InMemoryDefinitionProvider(
            [definition],
        )

    monkeypatch.setattr(
        request.module, "builtin_definition_provider", provider,
    )
