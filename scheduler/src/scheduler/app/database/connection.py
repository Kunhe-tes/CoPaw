# -*- coding: utf-8 -*-
"""Async database connection pool for the standalone Scheduler service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from scheduler.config.constant import (
    SchedulerDatabaseConfig,
    get_scheduler_database_config,
)

logger = logging.getLogger(__name__)

try:
    import aiomysql

    AIOMYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without optional dep
    aiomysql = None
    AIOMYSQL_AVAILABLE = False


class DatabaseConnection:
    """Small aiomysql-backed database wrapper used by Scheduler."""

    def __init__(self, config: SchedulerDatabaseConfig) -> None:
        self.config = config
        self._pool: Any | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._pool is not None

    async def connect(self) -> None:
        if not AIOMYSQL_AVAILABLE:
            raise RuntimeError(
                "aiomysql is not installed. Install scheduler dependencies first.",
            )
        if self._pool is not None:
            return
        try:
            self._pool = await aiomysql.create_pool(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                db=self.config.database,
                charset=self.config.charset,
                minsize=self.config.min_connections,
                maxsize=self.config.max_connections,
                autocommit=True,
            )
            self._connected = True
            logger.info(
                "Scheduler database pool created: %s:%s/%s",
                self.config.host,
                self.config.port,
                self.config.database,
            )
        except Exception:
            self._connected = False
            logger.exception("Failed to create Scheduler database pool")
            raise

    async def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
            self._connected = False
            logger.info("Scheduler database pool closed")

    @asynccontextmanager
    async def acquire(self):
        if self._pool is None:
            raise RuntimeError("Scheduler database is not connected")
        async with self._pool.acquire() as conn:
            yield conn

    async def execute(self, query: str, params: tuple | None = None) -> int:
        async with self.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return cur.rowcount

    async def execute_many(self, query: str, params_list: list[tuple]) -> int:
        if not params_list:
            return 0
        async with self.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(query, params_list)
                return cur.rowcount

    async def fetch_one(
        self,
        query: str,
        params: tuple | None = None,
    ) -> dict | None:
        async with self.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                row = await cur.fetchone()
                return dict(row) if row else None

    async def fetch_all(
        self,
        query: str,
        params: tuple | None = None,
    ) -> list[dict]:
        async with self.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                rows = await cur.fetchall()
                return [dict(row) for row in rows] if rows else []


_db_connection: DatabaseConnection | None = None


def get_db_connection() -> DatabaseConnection:
    if _db_connection is None:
        raise RuntimeError(
            "Scheduler database connection not initialized. "
            "Call init_db_connection() first.",
        )
    return _db_connection


async def init_db_connection(
    config: SchedulerDatabaseConfig | None = None,
) -> DatabaseConnection:
    global _db_connection

    _db_connection = DatabaseConnection(config or get_scheduler_database_config())
    await _db_connection.connect()
    return _db_connection


async def close_db_connection() -> None:
    global _db_connection

    if _db_connection is not None:
        await _db_connection.close()
        _db_connection = None
