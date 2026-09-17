"""Tests for server-owned W+ memory target binding."""

import pytest

from swe.app.wplus_sop.memory_policy import (
    WPlusMemoryPolicyError,
    normalize_anonymous_user_scope,
    resolve_memory_target,
)


def test_resolves_only_the_three_policy_targets() -> None:
    assert resolve_memory_target(
        "common_wplus_knowledge",
        user_scope=None,
    ) == ("common", "memory/common-wplus-knowledge.jsonl")
    assert resolve_memory_target("sop_case", user_scope=None) == (
        "cases",
        "memory/cases/sop-cases.jsonl",
    )
    assert resolve_memory_target(
        "user_wplus_usage",
        user_scope="anon_scope_123",
    ) == (
        "user",
        "memory/users/anon_scope_123/wplus-usage-preferences.jsonl",
    )


def test_personal_target_requires_anonymous_path_safe_scope() -> None:
    with pytest.raises(WPlusMemoryPolicyError):
        resolve_memory_target("user_wplus_usage", user_scope=None)
    with pytest.raises(WPlusMemoryPolicyError):
        normalize_anonymous_user_scope("../employee@example.com")
    with pytest.raises(WPlusMemoryPolicyError):
        normalize_anonymous_user_scope("12345678")
