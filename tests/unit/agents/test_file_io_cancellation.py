# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
import threading

import pytest

from swe.agents.tool_failure import ToolExecutionError
from swe.agents.tools import file_io
from swe.config.context import tenant_context


def _workspace(tmp_path: Path) -> Path:
    workspace_dir = tmp_path / "tenant_a" / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    return workspace_dir


async def _wait_for_event(event: threading.Event) -> None:
    assert await asyncio.to_thread(event.wait, 1.0)


async def _wait_for_temp_cleanup(workspace_dir: Path) -> None:
    for _ in range(100):
        if not list(workspace_dir.glob(".*.tmp")):
            return
        await asyncio.sleep(0.01)
    pytest.fail(f"temporary files were not cleaned up in {workspace_dir}")


@pytest.mark.asyncio
async def test_write_file_cancellation_does_not_modify_target(
    tmp_path: Path,
    monkeypatch,
):
    workspace_dir = _workspace(tmp_path)
    target = workspace_dir / "note.txt"
    target.write_text("original", encoding="utf-8-sig")
    write_started = threading.Event()
    release_write = threading.Event()
    write_finished = threading.Event()

    async def delayed_write(**kwargs):
        write_started.set()
        assert await asyncio.to_thread(release_write.wait, 1.0)
        Path(kwargs["file_path"]).write_text(
            kwargs["content"],
            encoding=kwargs["encoding"],
        )
        write_finished.set()

    monkeypatch.setattr(
        file_io,
        "_write_content_with_diagnostics",
        delayed_write,
    )

    with monkeypatch.context() as m:
        m.setattr("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path)
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            task = asyncio.create_task(
                file_io.write_file("note.txt", "new content"),
            )
            await _wait_for_event(write_started)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            release_write.set()
            await _wait_for_event(write_finished)
            await _wait_for_temp_cleanup(workspace_dir)

    assert target.read_text(encoding="utf-8-sig") == "original"


@pytest.mark.asyncio
async def test_append_file_cancellation_does_not_modify_target(
    tmp_path: Path,
    monkeypatch,
):
    workspace_dir = _workspace(tmp_path)
    target = workspace_dir / "note.txt"
    target.write_text("original", encoding="utf-8-sig")
    write_started = threading.Event()
    release_write = threading.Event()
    write_finished = threading.Event()

    async def delayed_write(**kwargs):
        write_started.set()
        assert await asyncio.to_thread(release_write.wait, 1.0)
        Path(kwargs["file_path"]).write_text(
            kwargs["content"],
            encoding=kwargs["encoding"],
        )
        write_finished.set()

    monkeypatch.setattr(
        file_io,
        "_write_content_with_diagnostics",
        delayed_write,
    )

    with monkeypatch.context() as m:
        m.setattr("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path)
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            task = asyncio.create_task(
                file_io.append_file("note.txt", " appended"),
            )
            await _wait_for_event(write_started)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            release_write.set()
            await _wait_for_event(write_finished)
            await _wait_for_temp_cleanup(workspace_dir)

    assert target.read_text(encoding="utf-8-sig") == "original"


@pytest.mark.asyncio
async def test_write_file_rejects_direct_workspace_skill_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace_dir = _workspace(tmp_path)

    with monkeypatch.context() as m:
        m.setattr("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path)
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            with pytest.raises(ToolExecutionError) as exc_info:
                await file_io.write_file(
                    "skills/uploaded/SKILL.md",
                    "# Uploaded\n",
                )

    assert exc_info.value.error_type == "permission_denied"
    assert not (workspace_dir / "skills" / "uploaded" / "SKILL.md").exists()
