# -*- coding: utf-8 -*-
"""Tests for workspace file distribution routes."""

from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from swe.app.routers import files
from swe.config.context import encode_scope_id


def _client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[TestClient, Path]:
    source_workspace = (
        tmp_path
        / encode_scope_id("source-user", "source-a")
        / "workspaces"
        / "agent-a"
    )
    source_workspace.mkdir(parents=True)
    monkeypatch.setattr(files, "WORKING_DIR", tmp_path, raising=False)
    monkeypatch.setattr(
        files,
        "resolve_file_manager_workspace_dir",
        AsyncMock(return_value=source_workspace),
        raising=False,
    )
    app = FastAPI()
    app.include_router(files.router)
    return TestClient(app), source_workspace


def _target(
    tmp_path: Path,
    tenant_id: str,
    *,
    source_id: str = "source-a",
    agent_id: str = "agent-a",
) -> tuple[dict[str, str], Path]:
    scope_id = encode_scope_id(tenant_id, source_id)
    workspace = tmp_path / scope_id / "workspaces" / agent_id
    workspace.mkdir(parents=True)
    return {"tenant_id": tenant_id, "scope_id": scope_id}, workspace


def test_distribute_copies_to_each_target_and_replaces_existing_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, source_workspace = _client(monkeypatch, tmp_path)
    source_file = source_workspace / "exports" / "report.txt"
    source_file.parent.mkdir()
    source_file.write_text("fresh report", encoding="utf-8")
    target_a, workspace_a = _target(tmp_path, "target-a")
    target_b, workspace_b = _target(tmp_path, "target-b")
    existing = workspace_a / "inbox" / "daily.txt"
    existing.parent.mkdir()
    existing.write_text("stale report", encoding="utf-8")

    response = client.post(
        "/files/distribute",
        json={
            "source_path": "exports/report.txt",
            "targets": [target_a, target_b],
            "target_path": "inbox/daily.txt",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "source_path": "exports/report.txt",
        "target_path": "inbox/daily.txt",
        "agent_id": "agent-a",
        "results": [
            {**target_a, "success": True, "error": ""},
            {**target_b, "success": True, "error": ""},
        ],
    }
    assert existing.read_text(encoding="utf-8") == "fresh report"
    assert (workspace_b / "inbox" / "daily.txt").read_text(
        encoding="utf-8",
    ) == "fresh report"


def test_distribute_keeps_processing_after_missing_target_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, source_workspace = _client(monkeypatch, tmp_path)
    (source_workspace / "source.txt").write_text("content", encoding="utf-8")
    missing_scope = encode_scope_id("missing-user", "source-a")
    valid_target, valid_workspace = _target(tmp_path, "valid-user")

    response = client.post(
        "/files/distribute",
        json={
            "source_path": "source.txt",
            "targets": [
                {"tenant_id": "missing-user", "scope_id": missing_scope},
                valid_target,
            ],
            "target_path": "received/source.txt",
        },
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["success"] is False
    assert results[0]["error"] == "Target agent workspace does not exist"
    assert results[1]["success"] is True
    assert (valid_workspace / "received" / "source.txt").is_file()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_path", "../secret.txt"),
        ("target_path", "nested/../../secret.txt"),
        ("source_path", "/etc/passwd"),
        ("target_path", "C:/outside.txt"),
        ("target_path", "C:outside.txt"),
        ("target_path", r"..\outside.txt"),
    ],
)
def test_distribute_rejects_non_relative_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    client, source_workspace = _client(monkeypatch, tmp_path)
    (source_workspace / "source.txt").write_text("content", encoding="utf-8")
    target, _ = _target(tmp_path, "target-a")
    body = {
        "source_path": "source.txt",
        "targets": [target],
        "target_path": "received.txt",
    }
    body[field] = value

    response = client.post("/files/distribute", json=body)

    assert response.status_code == 422


def test_distribute_rejects_empty_duplicate_or_mismatched_targets_before_copy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, source_workspace = _client(monkeypatch, tmp_path)
    (source_workspace / "source.txt").write_text("content", encoding="utf-8")
    target, target_workspace = _target(tmp_path, "target-a")
    mismatched_scope = encode_scope_id("other-user", "source-a")

    empty = client.post(
        "/files/distribute",
        json={
            "source_path": "source.txt",
            "targets": [],
            "target_path": "received.txt",
        },
    )
    duplicate = client.post(
        "/files/distribute",
        json={
            "source_path": "source.txt",
            "targets": [target, target],
            "target_path": "received.txt",
        },
    )
    mismatch = client.post(
        "/files/distribute",
        json={
            "source_path": "source.txt",
            "targets": [
                {"tenant_id": "target-a", "scope_id": mismatched_scope},
            ],
            "target_path": "received.txt",
        },
    )

    assert empty.status_code == 422
    assert duplicate.status_code == 422
    assert mismatch.status_code == 422
    assert not (target_workspace / "received.txt").exists()


@pytest.mark.parametrize("source_kind", ["missing", "directory", "symlink"])
def test_distribute_rejects_invalid_source_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    source_kind: str,
) -> None:
    client, source_workspace = _client(monkeypatch, tmp_path)
    source_path = source_workspace / "source.txt"
    if source_kind == "directory":
        source_path.mkdir()
    elif source_kind == "symlink":
        outside = tmp_path / "outside-source.txt"
        outside.write_text("secret", encoding="utf-8")
        try:
            source_path.symlink_to(outside)
        except OSError as exc:
            pytest.skip(f"symbolic links unavailable: {exc}")
    target, _ = _target(tmp_path, "target-a")

    response = client.post(
        "/files/distribute",
        json={
            "source_path": "source.txt",
            "targets": [target],
            "target_path": "received.txt",
        },
    )

    assert response.status_code == (404 if source_kind == "missing" else 422)


def test_distribute_reports_target_symlink_escape_and_continues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, source_workspace = _client(monkeypatch, tmp_path)
    (source_workspace / "source.txt").write_text("content", encoding="utf-8")
    escaped_target, escaped_workspace = _target(tmp_path, "escaped-user")
    valid_target, valid_workspace = _target(tmp_path, "valid-user")
    outside = tmp_path / "outside-target"
    outside.mkdir()
    try:
        (escaped_workspace / "received").symlink_to(
            outside,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symbolic links unavailable: {exc}")

    response = client.post(
        "/files/distribute",
        json={
            "source_path": "source.txt",
            "targets": [escaped_target, valid_target],
            "target_path": "received/source.txt",
        },
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["success"] is False
    assert response.json()["results"][0]["error"] == (
        "Target path escapes the agent workspace"
    )
    assert response.json()["results"][1]["success"] is True
    assert not (outside / "source.txt").exists()
    assert (valid_workspace / "received" / "source.txt").is_file()


def test_distribute_replaces_hard_link_without_mutating_linked_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, source_workspace = _client(monkeypatch, tmp_path)
    (source_workspace / "source.txt").write_text("new", encoding="utf-8")
    target, target_workspace = _target(tmp_path, "target-a")
    outside = tmp_path / "outside-hard-link.txt"
    outside.write_text("original", encoding="utf-8")
    linked_target = target_workspace / "received.txt"
    try:
        linked_target.hardlink_to(outside)
    except OSError as exc:
        pytest.skip(f"hard links unavailable: {exc}")

    response = client.post(
        "/files/distribute",
        json={
            "source_path": "source.txt",
            "targets": [target],
            "target_path": "received.txt",
        },
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["success"] is True
    assert outside.read_text(encoding="utf-8") == "original"
    assert linked_target.read_text(encoding="utf-8") == "new"


def test_files_router_keeps_preview_route_registered() -> None:
    route_paths = {route.path for route in files.router.routes}

    assert "/files/preview/{filepath:path}" in route_paths
    assert "/files/distribute" in route_paths
