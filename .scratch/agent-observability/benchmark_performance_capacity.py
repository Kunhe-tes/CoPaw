# -*- coding: utf-8 -*-
"""Reproduce the bounded performance-candidate MySQL capacity check.

Requires SWE_AGENTOBS_TEST_DB_HOST, SWE_AGENTOBS_TEST_DB_USER,
SWE_AGENTOBS_TEST_DB_PASSWORD, and an explicitly disposable *_test target.
The script creates and drops only a random swe_codex_capacity_*_test schema.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import resource
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import aiomysql

from swe.database import DatabaseConfig, DatabaseConnection
from swe.observability.store import ObservabilityStore

_CAPACITY_LIMIT = 50_000
_REPETITIONS = 7
_DDL_PATH = Path(__file__).with_name("schema-draft.sql")


def _database_config(database: str) -> DatabaseConfig:
    host = os.environ.get("SWE_AGENTOBS_TEST_DB_HOST", "").strip()
    user = os.environ.get("SWE_AGENTOBS_TEST_DB_USER", "").strip()
    password = os.environ.get("SWE_AGENTOBS_TEST_DB_PASSWORD", "")
    if not host or not user:
        raise RuntimeError(
            "disposable observability test DB credentials required",
        )
    return DatabaseConfig(
        host=host,
        port=int(os.environ.get("SWE_AGENTOBS_TEST_DB_PORT", "3306")),
        user=user,
        password=password,
        database=database,
        min_connections=1,
        max_connections=2,
        ssl_disabled=True,
        time_zone="+00:00",
        acquire_timeout=5,
        connect_timeout=8,
        read_timeout=10,
        write_timeout=10,
        cleanup_timeout=1,
    )


async def _admin_connection(database: str | None = None):
    config = _database_config(database or "")
    return await aiomysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        db=database,
        autocommit=True,
        connect_timeout=8,
    )


async def _install_schema(database: str) -> None:
    connection = await _admin_connection()
    try:
        async with connection.cursor() as cursor:
            await cursor.execute(
                f"CREATE DATABASE `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_bin",
            )
    finally:
        connection.close()

    connection = await _admin_connection(database)
    try:
        ddl = re.sub(r"(?m)^\s*--.*$", "", _DDL_PATH.read_text())
        async with connection.cursor() as cursor:
            for statement in ddl.split(";"):
                if statement.strip():
                    await cursor.execute(statement)
    finally:
        connection.close()


async def _assert_schema_absent(database: str) -> None:
    connection = await _admin_connection()
    try:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.schemata "
                "WHERE schema_name=%s",
                (database,),
            )
            if int((await cursor.fetchone())[0]):
                raise RuntimeError("random capacity schema already exists")
    finally:
        connection.close()


async def _insert_synthetic_spans(
    database: str,
    source_id: str,
    run_id: str,
    started_at: datetime,
) -> None:
    digits = (
        "(SELECT 0 d UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL "
        "SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL "
        "SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9)"
    )
    insert = (
        "INSERT INTO swe_agentobs_spans "
        "(span_id,run_id,span_type,operation,kind,name,started_at,ended_at,"
        "status,quality,duration_us,metadata_text) "
        "SELECT CONCAT('00000000-0000-4000-8000-',LPAD(n,12,'0')),%s,"
        "'LLM','chat','CLIENT','model.call',"
        "TIMESTAMPADD(MICROSECOND,n,%s),"
        "TIMESTAMPADD(MICROSECOND,n+1000,%s),"
        "'succeeded','observed',1000,'{}' "
        f"FROM (SELECT a.d+b.d*10+c.d*100+d.d*1000+e.d*10000 AS n "
        f"FROM {digits} a CROSS JOIN {digits} b CROSS JOIN {digits} c "
        f"CROSS JOIN {digits} d CROSS JOIN {digits} e) numbers "
        "WHERE n<%s"
    )
    config = _database_config(database)
    from swe.database.connection import DatabaseConnection as SweConnection

    connection = SweConnection(config)
    await connection.connect()
    try:
        async with connection.transaction() as session:
            await session.execute(
                "INSERT INTO swe_agentobs_runs "
                "(run_id,service_unit_key,source_key,tenant_key,agent_key,"
                "chat_key,root_question_key,capture_enabled,started_at,ended_at,"
                "status,quality,terminal_fact_source,metadata_text) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,1,%s,%s,'succeeded',"
                "'observed','business_settlement','{}')",
                (
                    run_id,
                    b"swe",
                    source_id.encode(),
                    b"capacity-user",
                    b"capacity-agent",
                    b"capacity-chat",
                    b"capacity-question",
                    started_at,
                    started_at + timedelta(seconds=10),
                ),
            )
            await session.execute(
                insert,
                (run_id, started_at, started_at, _CAPACITY_LIMIT + 1),
            )
    finally:
        await connection.close()


async def _server_snapshot(connection) -> dict:
    result = {}
    async with connection.cursor() as cursor:
        try:
            await cursor.execute(
                "SELECT COALESCE(SUM(CURRENT_NUMBER_OF_BYTES_USED),0),"
                "COALESCE(SUM(HIGH_NUMBER_OF_BYTES_USED),0) "
                "FROM performance_schema.memory_summary_global_by_event_name",
            )
            current, high_water = await cursor.fetchone()
            result["global_memory_current_bytes"] = int(current)
            result["global_memory_high_water_bytes"] = int(high_water)
        except Exception as exc:
            result["global_memory_status"] = type(exc).__name__
        try:
            await cursor.execute(
                "SELECT ENABLED FROM performance_schema.setup_consumers "
                "WHERE NAME='events_statements_cpu'",
            )
            row = await cursor.fetchone()
            result["statement_cpu_consumer"] = row[0] if row else "unavailable"
        except Exception as exc:
            result["statement_cpu_consumer"] = type(exc).__name__
        try:
            await cursor.execute(
                "SELECT COUNT_STAR,SUM_TIMER_WAIT,AVG_TIMER_WAIT,"
                "SUM_ROWS_EXAMINED,SUM_CREATED_TMP_DISK_TABLES "
                "FROM performance_schema.events_statements_summary_by_digest "
                "WHERE DIGEST_TEXT LIKE '%bounded_performance_candidates%'",
            )
            row = await cursor.fetchone()
            result["candidate_statement_digest"] = (
                [int(value or 0) for value in row] if row else None
            )
        except Exception as exc:
            result["candidate_statement_digest_status"] = type(exc).__name__
    return result


async def _explain_candidate_query(
    database: str,
    source_id: str,
    start_at: datetime,
    end_at: datetime,
) -> list[dict]:
    connection = await _admin_connection(database)
    query = (
        "EXPLAIN SELECT /*+ MAX_EXECUTION_TIME(5000) */ "
        "COUNT(*) AS candidate_count FROM (SELECT s.span_id "
        "FROM swe_agentobs_spans s JOIN swe_agentobs_runs r "
        "ON r.run_id=s.run_id WHERE r.service_unit_key=%s "
        "AND r.source_key IN (%s) AND s.ended_at IS NOT NULL "
        "AND s.started_at >= %s AND s.started_at < %s "
        "AND s.span_type=%s AND s.operation=%s LIMIT %s) "
        "AS bounded_performance_candidates"
    )
    try:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                query,
                (
                    b"swe",
                    source_id.encode(),
                    start_at,
                    end_at,
                    "LLM",
                    "chat",
                    _CAPACITY_LIMIT + 1,
                ),
            )
            return [dict(row) for row in await cursor.fetchall()]
    finally:
        connection.close()


def _emit_report(
    *,
    count: int,
    timings: list[float],
    client_cpu_seconds: float,
    before: dict,
    after: dict,
    explain: list[dict],
) -> None:
    ordered = sorted(timings)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    print(
        json.dumps(
            {
                "synthetic_span_count": _CAPACITY_LIMIT + 1,
                "bounded_candidate_count": count,
                "query_ms": [round(value, 2) for value in timings],
                "p50_ms": round(statistics.median(timings), 2),
                "p95_nearest_rank_ms": round(ordered[p95_index], 2),
                "python_client_cpu_seconds": round(client_cpu_seconds, 4),
                "python_client_peak_rss_platform_units": resource.getrusage(
                    resource.RUSAGE_SELF,
                ).ru_maxrss,
                "server_before": before,
                "server_after": after,
                "explain": explain,
                "mysql_host_cpu_available": False,
            },
            sort_keys=True,
        ),
    )


async def run() -> None:
    if not os.environ.get("SWE_AGENTOBS_TEST_DB_NAME", "").endswith("_test"):
        raise RuntimeError("configure an explicitly disposable *_test target")
    database = f"swe_codex_capacity_{uuid4().hex[:12]}_test"
    source_id = f"capacity-{uuid4().hex}"
    run_id = str(uuid4())
    start_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(
        hours=1,
    )
    start_db = start_at.replace(tzinfo=None)
    created = False
    try:
        await _assert_schema_absent(database)
        created = True
        await _install_schema(database)
        await _insert_synthetic_spans(
            database,
            source_id,
            run_id,
            start_db,
        )
        from swe.database.connection import DatabaseConnection as SweConnection

        connection = SweConnection(_database_config(database))
        await connection.connect()
        store = ObservabilityStore(connection)
        readiness = await store.readiness()
        if not readiness.get("ready"):
            raise RuntimeError("capacity benchmark schema failed readiness")
        admin = await _admin_connection(database)
        try:
            before = await _server_snapshot(admin)
            timings = []
            cpu_started = time.process_time()
            count = 0
            for _ in range(_REPETITIONS):
                started = time.perf_counter()
                count = await store.count_performance_candidates(
                    service_unit_id="swe",
                    source_ids=[source_id],
                    start_at=start_at - timedelta(seconds=1),
                    end_at=start_at + timedelta(seconds=1),
                    span_type="LLM",
                    operation="chat",
                    max_candidates=_CAPACITY_LIMIT,
                )
                timings.append((time.perf_counter() - started) * 1000)
                if count != _CAPACITY_LIMIT + 1:
                    raise AssertionError(
                        "candidate budget count did not stop at limit + 1",
                    )
            client_cpu_seconds = time.process_time() - cpu_started
            after = await _server_snapshot(admin)
        finally:
            admin.close()
            await connection.close()
        explain = await _explain_candidate_query(
            database,
            source_id,
            start_db - timedelta(seconds=1),
            start_db + timedelta(seconds=1),
        )
        _emit_report(
            count=count,
            timings=timings,
            client_cpu_seconds=client_cpu_seconds,
            before=before,
            after=after,
            explain=explain,
        )
    finally:
        if created:
            admin = await _admin_connection()
            try:
                async with admin.cursor() as cursor:
                    await cursor.execute(
                        f"DROP DATABASE IF EXISTS `{database}`",
                    )
                    await cursor.execute(
                        "SELECT COUNT(*) FROM information_schema.schemata "
                        "WHERE schema_name=%s",
                        (database,),
                    )
                    remaining = int((await cursor.fetchone())[0])
                    if remaining:
                        raise RuntimeError("capacity benchmark schema remains")
                    print(
                        f"capacity_schema_cleanup=verified count={remaining}",
                    )
            finally:
                admin.close()


if __name__ == "__main__":
    asyncio.run(run())
