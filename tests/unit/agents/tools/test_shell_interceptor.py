# -*- coding: utf-8 -*-
"""Shell 命令拦截器的租户与来源注入回归测试。"""

from swe.agents.tools.shell_interceptor import intercept_command
from swe.config.context import tenant_context


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
