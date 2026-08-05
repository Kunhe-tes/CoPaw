# -*- coding: utf-8 -*-
"""Scheduler service app tests."""

import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI


def test_scheduler_app_is_separate_service() -> None:
    from scheduler.app._app import app

    assert app.title == "Cron Scheduler"


def test_scheduler_package_does_not_reference_other_service_app() -> None:
    scheduler_root = Path(__file__).parents[3] / "scheduler" / "src" / "scheduler"
    offenders = []
    for path in scheduler_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "".join(["mon", "itor", ".app"]) in text:
            offenders.append(path.relative_to(scheduler_root).as_posix())

    assert offenders == []


@pytest.mark.asyncio
async def test_scheduler_lifespan_does_not_start_loop_when_db_init_fails(
    monkeypatch,
) -> None:
    from scheduler.app import _app as scheduler_app

    fastapi_app = FastAPI()
    init_db = AsyncMock(side_effect=RuntimeError("db offline"))
    close_db = AsyncMock()
    service_factory = MagicMock()

    monkeypatch.setattr(scheduler_app, "DB_HOST", "localhost")
    monkeypatch.setattr(scheduler_app, "init_db_connection", init_db)
    monkeypatch.setattr(scheduler_app, "close_db_connection", close_db)
    monkeypatch.setattr(
        scheduler_app,
        "cron_scheduling_runtime_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        scheduler_app,
        "get_cron_scheduling_service",
        service_factory,
    )

    async with scheduler_app.lifespan(fastapi_app):
        assert not hasattr(fastapi_app.state, "scheduler_task")

    init_db.assert_awaited_once()
    service_factory.assert_not_called()
    close_db.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduler_lifespan_uses_scheduler_database_config(
    monkeypatch,
) -> None:
    from scheduler.app import _app as scheduler_app

    fastapi_app = FastAPI()
    db_config = object()
    init_db = AsyncMock()
    init_tables = AsyncMock()
    close_db = AsyncMock()

    monkeypatch.setattr(scheduler_app, "DB_HOST", "scheduler-db")
    monkeypatch.setattr(scheduler_app, "DB_INIT_TABLES", True, raising=False)
    monkeypatch.setattr(
        scheduler_app,
        "get_scheduler_database_config",
        lambda: db_config,
    )
    monkeypatch.setattr(scheduler_app, "init_db_connection", init_db)
    monkeypatch.setattr(
        scheduler_app,
        "init_database_tables",
        init_tables,
        raising=False,
    )
    monkeypatch.setattr(scheduler_app, "close_db_connection", close_db)
    monkeypatch.setattr(
        scheduler_app,
        "cron_scheduling_runtime_enabled",
        lambda: False,
    )

    async with scheduler_app.lifespan(fastapi_app):
        assert not hasattr(fastapi_app.state, "scheduler_task")

    init_db.assert_awaited_once_with(db_config)
    init_tables.assert_not_awaited()
    close_db.assert_awaited_once()
