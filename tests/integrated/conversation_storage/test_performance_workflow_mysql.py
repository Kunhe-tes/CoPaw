# -*- coding: utf-8 -*-
"""Representative two-stage workflow metrics, never the 10k benchmark."""

import asyncio
import io
import json
from pathlib import Path
import time

from agentscope.message import Msg
from click.testing import CliRunner
import pytest

from swe.app.conversation_storage.bundle import BundleStore
from swe.app.conversation_storage.migration.progress import MigrationProgress
from swe.cli.conversation_storage_cmd import conversation_storage_group

from tests.integrated.conversation_storage.test_tenant_workflow_mysql import (
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
                return CliRunner().invoke(
                    conversation_storage_group,
                    arguments,
                )
            finally:
                report.emit()

    result = await asyncio.to_thread(invoke)
    assert result.exit_code in (0, 1, 2), (
        result.output
        + "\nexception="
        + (repr(result.exception) if result.exception is not None else "None")
    )
    progress = []
    lines = [
        *stream.getvalue().splitlines(),
        *result.stderr.splitlines(),
        *result.output.splitlines(),
    ]
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if "db_statement_attempts" in record:
            progress.append(record)
    assert progress, "migration progress metrics were not emitted"
    measured = max(
        progress,
        key=lambda item: (
            item.get("db_statement_attempts", 0),
            item.get("bundle_opens", 0),
        ),
    )
    metrics = {
        key: value
        for key, value in measured.items()
        if key.startswith(
            ("db_", "bundle_", "stage_wall_", "binding_", "manifest_"),
        )
        or key in ("rss_peak_bytes", "temp_peak_bytes", "io_seconds")
    }
    reports = []
    for line in [*result.stdout.splitlines(), *result.output.splitlines()]:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and "status" in record:
            reports.append(record)
    return (reports[-1] if reports else {}), {
        "wall_seconds": round(time.perf_counter() - started, 3),
        "exit_code": result.exit_code,
        "exception_type": (
            type(result.exception).__name__ if result.exception else None
        ),
        "cli_output": result.output,
        "cli_stderr": result.stderr,
        **metrics,
    }


async def _assert_new_metadata_schema(db):
    tables = {
        next(iter(row.values())) for row in await db.fetch_all("SHOW TABLES")
    }
    expected_tables = {
        "swe_conversation_sessions",
        "swe_conversation_chats",
        "swe_conversation_turns",
        "swe_conversation_publications",
        "swe_conversation_retentions",
    }
    assert expected_tables <= tables
    assert "swe_conversation_messages" not in tables
    ticket_counts = await db.fetch_all(
        "SELECT entry_kind,COUNT(*) AS n "
        "FROM swe_conversation_migration_entries "
        "GROUP BY entry_kind ORDER BY entry_kind",
    )
    assert all(row["entry_kind"] != b"message" for row in ticket_counts)
    return ticket_counts


async def _target_row_counts(db):
    counts = {}
    for table in (
        "swe_conversation_sessions",
        "swe_conversation_chats",
        "swe_conversation_publications",
    ):
        result = await db.fetch_one("SELECT COUNT(*) AS n FROM " + table)
        counts[table.removeprefix("swe_conversation_")] = result["n"]
    return counts


@pytest.mark.parametrize(
    "failure_mode",
    ["none", "running_turn", "fast_verification"],
)
async def test_representative_prepare_migrate_metrics(
    conversation_test_database,
    tmp_path,
    monkeypatch,
    failure_mode,
):
    db = conversation_test_database
    await _prepare_database(db, monkeypatch)
    prepared = _prepare_sources(
        tmp_path,
        failure_mode if failure_mode != "fast_verification" else "none",
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
    if failure_mode != "none":
        import_metrics = fast_verify_metrics = full_verify_metrics = {
            "not_run": "isolated failure path is exercised through migrate",
        }
        full_result = {}
    else:
        _, import_metrics = await _measured_invoke(
            [
                "import",
                "--manifest",
                str(manifest),
                "--apply",
                *resources,
            ],
        )
        _, fast_verify_metrics = await _measured_invoke(
            ["verify", "--manifest", str(manifest), *resources],
        )
        full_result, full_verify_metrics = await _measured_invoke(
            [
                "verify",
                "--manifest",
                str(manifest),
                "--full-audit",
                *resources,
            ],
        )
        assert fast_verify_metrics["exit_code"] == 0, fast_verify_metrics
        assert full_verify_metrics["exit_code"] == 0, full_verify_metrics
        assert full_result.get("passed") is True
    fail_fast_verification = [failure_mode == "fast_verification"]
    if fail_fast_verification[0]:
        from swe.cli import conversation_storage_tenants

        verify_import = conversation_storage_tenants.verify_import

        async def fail_bob_fast_once(*args, **kwargs):
            manifest_view = args[2]
            if (
                kwargs.get("verification_level") == "fast"
                and any(
                    item["tenant_id"] == "bob"
                    for item in manifest_view.data["workspaces"]
                )
                and fail_fast_verification[0]
            ):
                fail_fast_verification[0] = False
                return {
                    "passed": False,
                    "verification_level": "fast",
                    "blockers": [
                        {
                            "position": "publications",
                            "detail": "injected source failure",
                        },
                    ],
                    "checked": [],
                }
            return await verify_import(*args, **kwargs)

        monkeypatch.setattr(
            conversation_storage_tenants,
            "verify_import",
            fail_bob_fast_once,
        )
    arguments = [
        "migrate",
        "--manifest",
        str(manifest),
        "--apply",
        *resources,
    ]
    result, first = await _measured_invoke(arguments)
    assert result["published"] == (2 if failure_mode != "none" else 3)
    if failure_mode == "running_turn":
        state = json.loads(session_b.read_text())
        state.pop("turn_states")
        session_b.chmod(0o644)
        session_b.write_text(json.dumps(state))
        session_b.chmod(0o444)
    result, repeated = await _measured_invoke(arguments)
    assert result["published"] == 3 and result["failed"] == 0
    ticket_counts = await _assert_new_metadata_schema(db)
    target_counts = await _target_row_counts(db)
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
                "target_rows": {
                    **target_counts,
                    "tickets_by_kind": {
                        (
                            row["entry_kind"].decode()
                            if isinstance(row["entry_kind"], bytes)
                            else row["entry_kind"]
                        ): row["n"]
                        for row in ticket_counts
                    },
                },
                "workers": 3,
                "io_workers": 2,
                "memory_budget_mib": 128,
                "failure_mode": failure_mode,
                "prepare": prepare_metrics,
                "import": import_metrics,
                "fast_verify": fast_verify_metrics,
                "full_verify": full_verify_metrics,
                "verification_report": full_result,
                "migrate": first,
                "repeat": repeated,
            },
            sort_keys=True,
        ),
    )


@pytest.mark.asyncio
async def test_fast_verification_does_not_claim_body_equality(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    db = conversation_test_database
    await _prepare_database(db, monkeypatch)
    prepared = _prepare_sources(tmp_path, "none")
    (
        _source,
        nas,
        _workspaces,
        _config,
        _original,
        _session,
        manifest,
        _output,
        resources,
        services,
        boundary,
        shares,
    ) = prepared
    prepared_report, _ = await _measured_invoke(
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
    assert prepared_report["failed"] == 0
    imported_report, _ = await _measured_invoke(
        ["import", "--manifest", str(manifest), "--apply", *resources],
    )
    assert imported_report["failed"] == 0

    manifest_data = json.loads(manifest.read_text())
    recovery = next(
        assignment
        for position, assignment in manifest_data["assignments"][
            "publication"
        ].items()
        if position.endswith("/recovery")
    )
    bundles = BundleStore(nas)
    index = bundles.inspect(recovery["relative_path"])
    root = index.blocks["legacy_root"]
    bundle_path = nas / recovery["relative_path"]
    with bundle_path.open("rb") as bundle:
        bundle.seek(root.offset)
        assert bundle.read(1) == b"{"
    bundle_path.chmod(0o644)
    try:
        with bundle_path.open("r+b") as bundle:
            bundle.seek(root.offset)
            bundle.write(b"[")
    finally:
        bundle_path.chmod(0o444)

    from swe.cli import conversation_storage_tenants

    verification_results = []
    verify_import = conversation_storage_tenants.verify_import

    async def capture_verification(*args, **kwargs):
        result = await verify_import(*args, **kwargs)
        verification_results.append(result)
        return result

    monkeypatch.setattr(
        conversation_storage_tenants,
        "verify_import",
        capture_verification,
    )
    fast_result, _ = await _measured_invoke(
        ["verify", "--manifest", str(manifest), *resources],
    )
    assert fast_result["verification_level"] == "fast"
    assert fast_result["failed"] == 0, verification_results

    full_result, _ = await _measured_invoke(
        [
            "verify",
            "--manifest",
            str(manifest),
            "--full-audit",
            *resources,
        ],
    )
    assert full_result["verification_level"] == "full"
    assert full_result["failed"] == 1
    failure_report = json.loads(
        Path(full_result["failure_report"]).read_text(),
    )
    assert len(failure_report) == 1
