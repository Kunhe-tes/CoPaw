# -*- coding: utf-8 -*-
"""Representative two-stage workflow metrics, never the 10k benchmark."""

import asyncio
import io
import json
import time

from agentscope.message import Msg
from click.testing import CliRunner
import pytest

from swe.app.conversation_storage.migration.progress import MigrationProgress

from tests.integrated.conversation_storage.test_tenant_workflow_mysql import (
    _command,
    _prepare_database,
    _prepare_sources,
)


async def _measured_invoke(arguments):
    started = time.perf_counter()
    stream = io.StringIO()
    report = MigrationProgress(arguments[0], "representative", stream=stream)

    def invoke():
        with report.activate():
            try:
                return CliRunner().invoke(_command(), arguments)
            finally:
                report.emit()

    result = await asyncio.to_thread(invoke)
    assert result.exit_code in (0, 2), result.output
    progress = []
    lines = result.stderr.splitlines()
    if arguments[0] == "prepare":
        lines = stream.getvalue().splitlines()
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if "db_statement_attempts" in record:
            progress.append(record)
    assert progress, "migration progress metrics were not emitted"
    metrics = {
        key: value
        for key, value in progress[-1].items()
        if key.startswith(("db_", "bundle_", "stage_wall_"))
        or key in ("rss_peak_bytes", "temp_peak_bytes", "io_seconds")
    }
    return json.loads(result.stdout), {
        "wall_seconds": round(time.perf_counter() - started, 3),
        "exit_code": result.exit_code,
        **metrics,
    }


@pytest.mark.parametrize("failed_source", [False, True])
async def test_representative_prepare_migrate_metrics(
    conversation_test_database,
    tmp_path,
    monkeypatch,
    failed_source,
):
    db = conversation_test_database
    await _prepare_database(db, monkeypatch)
    prepared = _prepare_sources(
        tmp_path,
        "running_turn" if failed_source else "none",
    )
    (
        _source,
        _nas,
        workspaces,
        _config,
        _original,
        session_b,
        manifest,
        output,
        resources,
        services,
        boundary,
        shares,
    ) = prepared
    session_a = workspaces["alice"] / "sessions" / "alice_s.json"
    state = json.loads(session_a.read_text())
    state["agent"]["memory"]["content"] = [
        Msg("user", "representative " + str(i), "user").to_dict()
        for i in range(128)
    ]
    session_a.chmod(0o644)
    session_a.write_text(json.dumps(state))
    session_a.chmod(0o444)
    result, prepare_metrics = await _measured_invoke(
        [
            "prepare",
            "--services",
            str(services),
            "--boundary",
            str(boundary),
            "--manifest",
            str(manifest),
            "--shares-file",
            str(shares),
            "--tenant-isolation",
            "--in-place",
            *resources,
        ],
    )
    assert result["failed"] == 0
    arguments = [
        "migrate",
        "--manifest",
        str(manifest),
        "--output-dir",
        str(output),
        "--apply",
        *resources,
    ]
    result, first = await _measured_invoke(arguments)
    assert result["published"] == (2 if failed_source else 3)
    if failed_source:
        state = json.loads(session_b.read_text())
        state.pop("turn_states")
        session_b.chmod(0o644)
        session_b.write_text(json.dumps(state))
        session_b.chmod(0o444)
    result, repeated = await _measured_invoke(arguments)
    assert result["published"] == 3 and result["failed"] == 0
    count = await db.fetch_one(
        "SELECT COUNT(*) AS n FROM swe_conversation_messages",
    )
    assert count["n"] >= 128
    assert first["db_statement_attempts"] > 0
    assert first["db_transaction_begins"] > 0
    print(
        json.dumps(
            {
                "benchmark": "representative_prepare_migrate",
                "environment": "isolated_mysql_local_directories",
                "sources": 3,
                "workspaces": 3,
                "input_messages": 128,
                "workers": 3,
                "io_workers": 2,
                "memory_budget_mib": 128,
                "failed_then_repaired_source": failed_source,
                "prepare": prepare_metrics,
                "migrate": first,
                "repeat": repeated,
            },
            sort_keys=True,
        ),
    )
