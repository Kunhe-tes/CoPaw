# -*- coding: utf-8 -*-
"""Two-stage CLI preserves explicit isolation and durable frozen evidence."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import click
import pytest
from click.testing import CliRunner


def command():
    from swe.cli.conversation_storage_discovery_cmd import (
        register_discovery_commands,
    )

    @click.group()
    def group():
        pass

    register_discovery_commands(group)
    return group


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    from swe.database import config

    monkeypatch.setattr(
        config,
        "get_database_config",
        lambda: SimpleNamespace(database="business"),
    )
    source = tmp_path / "source"
    root = source / "default_SRC"
    workspace = root / "workspaces" / "agent"
    workspace.mkdir(parents=True)
    nas = tmp_path / "nas"
    runtime = nas / "default_SRC/workspaces/agent"
    runtime.mkdir(parents=True)
    (root / "config.json").write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": {
                        "agent": {
                            "id": "agent",
                            "workspace_dir": str(runtime),
                        },
                    },
                },
            },
        ),
    )
    (workspace / "agent.json").write_text('{"id":"agent"}')
    (workspace / "chats.json").write_text('{"version":1,"chats":[]}')
    for path in source.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    source.chmod(0o555)
    services = tmp_path / "services.json"
    services.write_text(
        json.dumps(
            {
                "services": [
                    {
                        "service_unit_id": "SERVICE",
                        "source_root": str(source),
                        "config_root": str(source),
                        "original_root": str(nas),
                        "nas_root": str(nas),
                    },
                ],
            },
        ),
    )
    shares = tmp_path / "shares.json"
    shares.write_text("[]")
    boundary = tmp_path / "boundary.json"
    boundary.write_text(
        json.dumps(
            {
                "snapshot_id": "stopped-1",
                "captured_at": "2026-11-15T00:00:00Z",
                "old_image_digest": "old@sha256:" + "a" * 64,
                "evidence_refs": ["stop", "readonly"],
            },
        ),
    )
    return {
        "services": services,
        "shares": shares,
        "boundary": boundary,
        "manifest": tmp_path / "manifest.json",
        "workspace": workspace,
    }


def prepare_args(inputs):
    return [
        "prepare",
        "--tenant-isolation",
        "--services",
        str(inputs["services"]),
        "--boundary",
        str(inputs["boundary"]),
        "--shares-file",
        str(inputs["shares"]),
        "--manifest",
        str(inputs["manifest"]),
    ]


def test_write_runtime_copies_manifest_beside_service_references(tmp_path):
    from types import SimpleNamespace

    from swe.cli.conversation_storage_tenants import _write_runtime

    source = tmp_path / "manifest.json"
    source.write_text('{"migration_id":"job"}')
    output = tmp_path / "runtime"
    manifest = SimpleNamespace(
        path=source,
        migration_id="job",
        data={"services": [{"service_unit_id": "svc", "nas_root": "/nas"}]},
    )

    _write_runtime(output, manifest)

    assert (output / "manifest.json").read_text() == source.read_text()
    assert len(list(output.glob("*.runtime.json"))) == 1


def test_write_runtime_accepts_manifest_in_output_directory(tmp_path):
    from swe.cli.conversation_storage_tenants import _write_runtime

    source = tmp_path / "manifest.json"
    source.write_text('{"migration_id":"job"}')
    manifest = SimpleNamespace(
        path=source,
        migration_id="job",
        data={"services": [{"service_unit_id": "svc", "nas_root": "/nas"}]},
    )
    _write_runtime(tmp_path, manifest)
    assert source.read_text() == '{"migration_id":"job"}'
    assert len(list(tmp_path.glob("*.runtime.json"))) == 1


@pytest.mark.parametrize("invalid_chats", [False, True])
def test_prepare_reuses_freeze_and_readonly_preflight(
    inputs,
    monkeypatch,
    invalid_chats,
):
    from swe.cli import conversation_storage_v3_cmd as v3

    if invalid_chats:
        registry = inputs["workspace"] / "chats.json"
        registry.chmod(0o644)
        registry.write_text("invalid")
        registry.chmod(0o444)
    preflight = Mock(
        return_value={
            "status": "success",
            "failed": 0,
            "completed": 0,
            "failure_report": None,
            "passed": True,
        },
    )
    monkeypatch.setattr(v3, "run_v3_command", preflight)
    result = CliRunner().invoke(command(), prepare_args(inputs))
    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    assert output["operation"] == "prepare"
    frozen = json.loads(inputs["manifest"].read_text())
    assert frozen["tenant_isolation"] is True
    assert frozen["source_isolation"] is True
    assert "freshness_protocol" not in frozen
    assert frozen["source_binding_storage"] == "manifest-v1"
    assert "chats_mtime_ns" not in frozen["workspaces"][0]
    assert "input_digest" not in frozen["tenants"][0]
    assert frozen["tenants"][0]["source_id"] == "SRC"
    assert frozen["offline"]["application_schema"] == "business"
    assert frozen["assignments"] == frozen["batches"] == {}
    assert frozen["tenants"][0]["state"] == "discovered"
    assert Path(output["discovery"]).stat().st_mode & 0o777 == 0o600
    assert preflight.call_args.args == ("preflight", inputs["manifest"])
    assert preflight.call_args.kwargs["apply"] is False


def test_prepare_requires_isolation_and_refuses_schema_mismatch(inputs):
    args = prepare_args(inputs)
    args.remove("--tenant-isolation")
    result = CliRunner().invoke(command(), args)
    assert result.exit_code == 1
    assert "explicit --tenant-isolation" in result.output
    result = CliRunner().invoke(
        command(),
        prepare_args(inputs)
        + [
            "--application-schema",
            "other",
        ],
    )
    assert result.exit_code == 1
    assert "schema differs" in result.output
    assert not inputs["manifest"].exists()


def test_prepare_preserves_existing_output(inputs):
    inputs["manifest"].write_text("existing evidence")
    result = CliRunner().invoke(command(), prepare_args(inputs))
    assert result.exit_code == 1
    assert inputs["manifest"].read_text() == "existing evidence"


@pytest.mark.parametrize(
    "error",
    [OSError("shared disk down"), RuntimeError("bug")],
)
def test_prepare_never_converts_global_preflight_error_to_partial(
    inputs,
    monkeypatch,
    error,
):
    from swe.cli import conversation_storage_v3_cmd as v3

    monkeypatch.setattr(v3, "run_v3_command", Mock(side_effect=error))
    result = CliRunner().invoke(command(), prepare_args(inputs))
    assert result.exit_code == 1
    assert "partial_success" not in result.output


@pytest.mark.parametrize("apply", [True, False])
def test_migrate_forwards_resources_without_splitting_workflow(
    inputs,
    monkeypatch,
    apply,
):
    from swe.cli import conversation_storage_v3_cmd as v3

    inputs["manifest"].write_text("{}")
    execute = Mock()
    monkeypatch.setattr(v3, "run_v3_and_echo", execute)
    args = [
        "migrate",
        "--manifest",
        str(inputs["manifest"]),
        "--output-dir",
        str(inputs["manifest"].parent / "runtime"),
        "--workers",
        "3",
        "--io-workers",
        "2",
        "--memory-budget-mib",
        "256",
    ] + (["--apply"] if apply else [])
    result = CliRunner().invoke(command(), args)
    assert result.exit_code == 0, result.output
    assert execute.call_args.args == ("migrate", str(inputs["manifest"]))
    assert execute.call_args.kwargs["apply"] is apply
    assert execute.call_args.kwargs["workers"] == 3
    assert execute.call_args.kwargs["io_workers"] == 2
    assert execute.call_args.kwargs["memory_budget_mib"] == 256


def test_migrate_retains_partial_exit_code(inputs, monkeypatch):
    from swe.cli import conversation_storage_v3_cmd as v3

    inputs["manifest"].write_text("{}")
    monkeypatch.setattr(
        v3,
        "run_v3_and_echo",
        Mock(
            side_effect=click.exceptions.Exit(2),
        ),
    )
    result = CliRunner().invoke(
        command(),
        [
            "migrate",
            "--manifest",
            str(inputs["manifest"]),
            "--output-dir",
            str(inputs["manifest"].parent / "runtime"),
            "--apply",
        ],
    )
    assert result.exit_code == 2


def test_prepare_in_place_mode_is_durable(inputs, monkeypatch):
    from swe.cli import conversation_storage_v3_cmd as v3

    declared = json.loads(inputs["services"].read_text())
    service = declared["services"][0]
    service.update(
        original_root=service["source_root"],
        snapshot_root=service["source_root"],
    )
    inputs["services"].write_text(json.dumps(declared))
    config = inputs["workspace"].parents[1] / "config.json"
    config.chmod(0o644)
    config.write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": {
                        "agent": {
                            "id": "agent",
                            "workspace_dir": str(inputs["workspace"]),
                        },
                    },
                },
            },
        ),
    )
    config.chmod(0o444)
    monkeypatch.setattr(
        v3,
        "run_v3_command",
        Mock(
            return_value={"status": "success", "passed": True},
        ),
    )
    result = CliRunner().invoke(
        command(),
        prepare_args(inputs)
        + [
            "--in-place",
        ],
    )
    assert result.exit_code == 0, result.output
    frozen = json.loads(inputs["manifest"].read_text())
    assert frozen["in_place"] is True
    assert "freshness_protocol" not in frozen
    assert "in_place_evidence" not in frozen["workspaces"][0]


def test_prepare_freeze_refusal_never_starts_preflight(inputs, monkeypatch):
    from swe.cli import conversation_storage_discovery_cmd as discovery
    from swe.cli import conversation_storage_v3_cmd as v3

    freeze = Mock(side_effect=ValueError("source changed during freeze"))
    monkeypatch.setattr(discovery, "freeze_discovery", freeze)
    preflight = Mock()
    monkeypatch.setattr(v3, "run_v3_command", preflight)
    result = CliRunner().invoke(command(), prepare_args(inputs))
    assert result.exit_code == 1
    assert "source changed during freeze" in result.output
    preflight.assert_not_called()
    assert not inputs["manifest"].exists()


def test_prepare_excludes_historical_shares_without_database_access(
    inputs,
    monkeypatch,
):
    from swe.cli import conversation_storage_discovery_cmd as discovery_cmd
    from swe.cli import conversation_storage_v3_cmd as v3

    discover = discovery_cmd.discover_services
    observed = []

    def record_discovery(*args, **kwargs):
        report = discover(*args, **kwargs)
        observed.append(report)
        return report

    monkeypatch.setattr(discovery_cmd, "discover_services", record_discovery)
    monkeypatch.setattr(
        v3,
        "run_v3_command",
        Mock(
            return_value={"status": "success", "passed": True},
        ),
    )
    args = prepare_args(inputs)
    index = args.index("--shares-file")
    del args[index : index + 2]
    result = CliRunner().invoke(command(), args)
    assert result.exit_code == 0, result.output
    assert observed[0]["shares"] == []
    assert observed[0]["source_shares"] == []
    assert observed[0]["excluded_scopes"] == ["historical_shares"]
    assert len(observed) == 1


def test_prepare_does_not_compare_chats_mtime(inputs, monkeypatch):
    from swe.cli import conversation_storage_discovery_cmd as discovery
    from swe.cli import conversation_storage_v3_cmd as v3

    freeze = discovery.freeze_discovery

    def changed_before_freeze(*args, **kwargs):
        registry = inputs["workspace"] / "chats.json"
        registry.chmod(0o644)
        registry.write_text(
            json.dumps({"version": 1, "chats": [], "changed": True}),
        )
        registry.chmod(0o444)
        return freeze(*args, **kwargs)

    monkeypatch.setattr(discovery, "freeze_discovery", changed_before_freeze)
    monkeypatch.setattr(
        v3,
        "run_v3_command",
        Mock(return_value={"status": "success", "passed": True}),
    )
    result = CliRunner().invoke(command(), prepare_args(inputs))
    assert result.exit_code == 0, result.output
    v3.run_v3_command.assert_called_once()
    assert inputs["manifest"].exists()


def test_prepare_does_not_read_conversation_inputs(inputs, monkeypatch):
    from swe.cli import conversation_storage_v3_cmd as v3

    read_bytes = Path.read_bytes

    def guarded_read(path):
        if (
            path.is_relative_to(inputs["workspace"])
            and path.name != "agent.json"
        ):
            raise AssertionError("prepare read conversation input")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    monkeypatch.setattr(
        v3,
        "run_v3_command",
        Mock(return_value={"status": "success", "passed": True}),
    )
    result = CliRunner().invoke(command(), prepare_args(inputs))
    assert result.exit_code == 0, result.output


def test_prepare_rejects_empty_tenant_job(inputs, monkeypatch):
    from swe.cli import conversation_storage_discovery_cmd as discovery
    from swe.cli import conversation_storage_v3_cmd as v3

    monkeypatch.setattr(
        discovery,
        "discover_services",
        Mock(return_value={"tenants": []}),
    )
    freeze = Mock()
    preflight = Mock()
    monkeypatch.setattr(discovery, "freeze_discovery", freeze)
    monkeypatch.setattr(v3, "run_v3_command", preflight)
    result = CliRunner().invoke(command(), prepare_args(inputs))
    assert result.exit_code == 1
    assert "at least one discovered tenant" in result.output
    freeze.assert_not_called()
    preflight.assert_not_called()
    assert not inputs["manifest"].exists()


@pytest.mark.asyncio
async def test_register_rejects_empty_tenant_job_before_database_access():
    from swe.cli.conversation_storage_tenants import _register_tenants

    db, states = Mock(), Mock()
    manifest = SimpleNamespace(data={"tenants": []})
    with pytest.raises(ValueError, match="at least one discovered tenant"):
        await _register_tenants(db, manifest, states, Mock())
    assert not db.mock_calls
    assert not states.mock_calls
