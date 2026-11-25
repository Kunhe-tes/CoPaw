# -*- coding: utf-8 -*-
"""应用停机顺序回归测试。

停机必须先停止事件生产者（manager、workspace pool），再排空并关闭
observability emitter，最后停止 projector 与观测数据库连接，避免
``attempt.ended`` / ``span.ended`` 等尾事件在 emitter 关闭后被丢弃。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from swe.app import _app as app_module
from swe.app.crons import auth_mirror
from swe.observability import emitter
from swe.security import skill_scanner


@pytest.mark.asyncio
async def test_shutdown_drains_emitter_after_producers(monkeypatch):
    events: list[str] = []

    async def stop_system_cron_tasks(*_args, **_kwargs) -> None:
        events.append("system_cron")

    async def stop_heartbeat() -> None:
        events.append("heartbeat")

    async def stop_manager(*_args, **_kwargs) -> bool:
        events.append("manager")
        return True

    async def stop_pool(*_args, **_kwargs) -> bool:
        events.append("pool")
        return True

    def shutdown_emitter() -> int:
        events.append("emitter")
        return 0

    projector = SimpleNamespace(
        stop=AsyncMock(side_effect=lambda: events.append("projector")),
    )
    observability_connection = SimpleNamespace(
        close=AsyncMock(side_effect=lambda: events.append("observability_db")),
    )
    database = SimpleNamespace(
        close=AsyncMock(side_effect=lambda: events.append("db")),
    )
    app: Any = SimpleNamespace(
        state=SimpleNamespace(
            agent_observability_projector=projector,
            agent_observability_connection=observability_connection,
        ),
    )

    monkeypatch.setattr(
        app_module,
        "_stop_system_cron_tasks",
        stop_system_cron_tasks,
    )
    monkeypatch.setattr(app_module, "stop_service_heartbeat", stop_heartbeat)
    monkeypatch.setattr(app_module, "_stop_multi_agent_manager", stop_manager)
    monkeypatch.setattr(app_module, "_stop_tenant_workspace_pool", stop_pool)
    monkeypatch.setattr(app_module, "close_trace_manager", AsyncMock())
    monkeypatch.setattr(app_module, "shutdown_global_tracer", MagicMock())
    monkeypatch.setattr(
        app_module.runtime_diagnostic_manager,
        "stop",
        AsyncMock(),
    )
    monkeypatch.setattr(
        app_module.runtime_diagnostic_manager,
        "set_workspace_metrics",
        MagicMock(),
    )
    monkeypatch.setattr(app_module, "shutdown_logger", MagicMock())
    # 函数内部按模块属性导入，因此需要替换来源模块上的符号。
    monkeypatch.setattr(emitter, "shutdown_default_emitter", shutdown_emitter)
    monkeypatch.setattr(
        skill_scanner,
        "install_skill_scan_history_recorder",
        MagicMock(),
    )
    monkeypatch.setattr(
        auth_mirror,
        "set_cron_auth_repository",
        MagicMock(),
    )

    await app_module._shutdown_lifespan_resources_impl(app, database)

    # 生产者 -> emitter -> projector -> 观测 DB -> 业务 DB
    assert events == [
        "system_cron",
        "heartbeat",
        "manager",
        "pool",
        "emitter",
        "projector",
        "observability_db",
        "db",
    ]
