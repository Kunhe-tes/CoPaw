# -*- coding: utf-8 -*-
"""Shell 命令拦截器的租户与来源注入回归测试。"""

import logging
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace

import pytest

from swe.agents.tool_failure import ToolExecutionError
from swe.agents.tools.shell_interceptor import intercept_command
from swe.config.context import resolve_scope_id, tenant_context


def test_intercept_swe_cron_injects_logical_tenant_and_source():
    with tenant_context(
        tenant_id="tenant-a",
        user_id="user-a",
        source_id="source-a",
    ):
        command, intercepted = intercept_command("swe cron list")

    assert intercepted is True
    assert "--tenant-id tenant-a" in command
    assert "--source-id source-a" in command
    assert "dGVuYW50" not in command


def test_intercept_swe_cron_create_injects_source_and_user_fields():
    with tenant_context(
        tenant_id="tenant-a",
        user_id="user-a",
        source_id="source-a",
    ):
        command, intercepted = intercept_command(
            "swe cron create --type agent --name demo --cron '* * * * *'",
        )

    assert intercepted is True
    assert "--tenant-id tenant-a" in command
    assert "--source-id source-a" in command
    assert "--target-user user-a" in command
    assert "--creator-user user-a" in command


def test_intercept_swe_cron_list_does_not_inject_create_only_user_fields():
    with tenant_context(
        tenant_id="tenant-a",
        user_id="user-a",
        source_id="source-a",
    ):
        command, intercepted = intercept_command("swe cron list")

    assert intercepted is True
    assert "--tenant-id tenant-a" in command
    assert "--source-id source-a" in command
    assert "--target-user" not in command
    assert "--creator-user" not in command


def test_intercept_swe_cron_keeps_explicit_source_id():
    with tenant_context(
        tenant_id="tenant-a",
        user_id="user-a",
        source_id="source-a",
    ):
        command, intercepted = intercept_command(
            "swe cron list --source-id explicit-source",
        )

    assert intercepted is True
    assert command.count("--source-id") == 1
    assert "--source-id explicit-source" in command


def test_intercept_swe_cron_after_shell_and_operator():
    with tenant_context(
        tenant_id="tenant-a",
        user_id="user-a",
        source_id="source-a",
    ):
        command, intercepted = intercept_command("echo ready && swe cron list")

    assert intercepted is True
    assert command == (
        "echo ready && swe cron list "
        "--tenant-id tenant-a --source-id source-a"
    )


def test_intercept_swe_cron_before_shell_and_operator():
    with tenant_context(
        tenant_id="tenant-a",
        user_id="user-a",
        source_id="source-a",
    ):
        command, intercepted = intercept_command("swe cron list && echo done")

    assert intercepted is True
    assert command == (
        "swe cron list --tenant-id tenant-a --source-id source-a && echo done"
    )


def test_intercept_opencli_injects_resolved_credentials_for_effective_tenant(
    monkeypatch,
    tmp_path: Path,
):
    calls = []

    def fake_resolve_auth_token_for_execution(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            token="resolved-authorization",
            cookie_header="resolved-cookie",
        )

    monkeypatch.setattr(
        "swe.agents.tools.shell_interceptor."
        "resolve_auth_token_for_execution",
        fake_resolve_auth_token_for_execution,
    )

    with tenant_context(
        tenant_id="default",
        user_id="user-a",
        source_id="source-a",
        workspace_dir=tmp_path,
    ):
        command, intercepted = intercept_command("opencli apps list")

    assert intercepted is True
    assert command == (
        "opencli --authorization resolved-authorization "
        "--cookie resolved-cookie apps list"
    )
    assert calls == [
        {
            "tenant_id": resolve_scope_id("default", "source-a"),
            "workspace_dir": tmp_path,
        },
    ]


@pytest.mark.parametrize(
    "command",
    [
        (
            "opencli --authorization explicit-authorization "
            "--cookie explicit-cookie apps list"
        ),
        (
            "opencli --authorization=explicit-authorization "
            "--cookie=explicit-cookie apps list"
        ),
    ],
)
def test_intercept_opencli_keeps_both_explicit_credentials(
    monkeypatch,
    command: str,
):
    def unexpected_resolve(**_kwargs):
        raise AssertionError("explicit credentials must not be replaced")

    monkeypatch.setattr(
        "swe.agents.tools.shell_interceptor."
        "resolve_auth_token_for_execution",
        unexpected_resolve,
    )

    with tenant_context(tenant_id="tenant-a", user_id="user-a"):
        modified, intercepted = intercept_command(command)

    assert intercepted is False
    assert modified == command


@pytest.mark.parametrize(
    ("command", "resolved_authorization", "resolved_cookie", "expected"),
    [
        (
            "opencli --authorization explicit-authorization apps list",
            None,
            "resolved-cookie",
            (
                "opencli --cookie resolved-cookie "
                "--authorization explicit-authorization apps list"
            ),
        ),
        (
            "opencli --cookie explicit-cookie apps list",
            "resolved-authorization",
            None,
            (
                "opencli --authorization resolved-authorization "
                "--cookie explicit-cookie apps list"
            ),
        ),
    ],
)
def test_intercept_opencli_only_injects_missing_credential(
    monkeypatch,
    command: str,
    resolved_authorization: str | None,
    resolved_cookie: str | None,
    expected: str,
):
    monkeypatch.setattr(
        "swe.agents.tools.shell_interceptor."
        "resolve_auth_token_for_execution",
        lambda **_kwargs: SimpleNamespace(
            token=resolved_authorization,
            cookie_header=resolved_cookie,
        ),
    )

    with tenant_context(tenant_id="tenant-a", user_id="user-a"):
        modified, intercepted = intercept_command(command)

    assert intercepted is True
    assert modified == expected


def test_intercept_opencli_only_modifies_matching_and_segment(monkeypatch):
    monkeypatch.setattr(
        "swe.agents.tools.shell_interceptor."
        "resolve_auth_token_for_execution",
        lambda **_kwargs: SimpleNamespace(
            token="resolved-authorization",
            cookie_header="resolved-cookie",
        ),
    )

    with tenant_context(tenant_id="tenant-a", user_id="user-a"):
        command, intercepted = intercept_command(
            "echo ready && opencli apps list && echo done",
        )

    assert intercepted is True
    assert command == (
        "echo ready && opencli --authorization resolved-authorization "
        "--cookie resolved-cookie apps list && echo done"
    )


def test_intercept_opencli_quotes_resolved_credentials_for_platform(monkeypatch):
    authorization = '{"name": "Alice Example"}'
    cookie = "session=Alice Example; mode=full"
    monkeypatch.setattr(
        "swe.agents.tools.shell_interceptor."
        "resolve_auth_token_for_execution",
        lambda **_kwargs: SimpleNamespace(
            token=authorization,
            cookie_header=cookie,
        ),
    )

    with tenant_context(tenant_id="tenant-a", user_id="user-a"):
        command, intercepted = intercept_command("opencli apps list")

    quote = (
        subprocess.list2cmdline
        if sys.platform == "win32"
        else lambda values: shlex.quote(values[0])
    )
    quoted_authorization = quote([authorization])
    quoted_cookie = quote([cookie])
    assert intercepted is True
    assert command == (
        f"opencli --authorization {quoted_authorization} "
        f"--cookie {quoted_cookie} apps list"
    )


def test_intercept_opencli_fails_when_authorization_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        "swe.agents.tools.shell_interceptor."
        "resolve_auth_token_for_execution",
        lambda **_kwargs: SimpleNamespace(
            token=None,
            cookie_header="resolved-cookie",
        ),
    )

    with (
        tenant_context(tenant_id="tenant-a", user_id="user-a"),
        pytest.raises(ToolExecutionError) as exc_info,
    ):
        intercept_command("opencli apps list")

    assert exc_info.value.error_type == "permission_denied"
    assert "OpenCLI authorization is not configured" in exc_info.value.detail


def test_intercept_opencli_fails_when_cookie_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        "swe.agents.tools.shell_interceptor."
        "resolve_auth_token_for_execution",
        lambda **_kwargs: SimpleNamespace(
            token="resolved-authorization",
            cookie_header=None,
        ),
    )

    with (
        tenant_context(tenant_id="tenant-a", user_id="user-a"),
        pytest.raises(ToolExecutionError) as exc_info,
    ):
        intercept_command("opencli apps list")

    assert exc_info.value.error_type == "permission_denied"
    assert "OpenCLI cookie is not configured" in exc_info.value.detail


def test_intercept_opencli_maps_expired_auth_state_to_tool_failure(monkeypatch):
    def expired_auth_state(**_kwargs):
        raise ValueError("cron auth user_info is expired")

    monkeypatch.setattr(
        "swe.agents.tools.shell_interceptor."
        "resolve_auth_token_for_execution",
        expired_auth_state,
    )

    with (
        tenant_context(tenant_id="tenant-a", user_id="user-a"),
        pytest.raises(ToolExecutionError) as exc_info,
    ):
        intercept_command("opencli apps list")

    assert exc_info.value.error_type == "permission_denied"
    assert "OpenCLI authentication has expired" in exc_info.value.detail


def test_intercept_opencli_does_not_log_credentials(
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(
        "swe.agents.tools.shell_interceptor."
        "resolve_auth_token_for_execution",
        lambda **_kwargs: SimpleNamespace(
            token="secret-authorization",
            cookie_header="secret-cookie",
        ),
    )

    with (
        tenant_context(tenant_id="tenant-a", user_id="user-a"),
        caplog.at_level(
            logging.INFO,
            logger="swe.agents.tools.shell_interceptor",
        ),
    ):
        intercept_command("opencli apps list")

    assert "secret-authorization" not in caplog.text
    assert "secret-cookie" not in caplog.text
    assert "opencli apps list" not in caplog.text
    assert "Shell command intercepted" in caplog.text
