# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest

from swe.agents.tool_failure import ToolExecutionError
from swe.config.context import encode_scope_id, tenant_context


@pytest.fixture
def tenant_workspace(tmp_path: Path) -> Generator[dict[str, Path], None, None]:
    base_dir = tmp_path
    workspaces = {
        "source_a": (
            base_dir
            / encode_scope_id("tenant_a", "source_a")
            / "workspaces"
            / "agent_a"
        ),
        "source_b": (
            base_dir
            / encode_scope_id("tenant_a", "source_b")
            / "workspaces"
            / "agent_a"
        ),
    }
    for workspace in workspaces.values():
        workspace.mkdir(parents=True)

    with patch("swe.constant.WORKING_DIR", base_dir):
        with patch("swe.security.tenant_path_boundary.WORKING_DIR", base_dir):
            with patch("swe.config.utils.WORKING_DIR", base_dir):
                yield workspaces


@pytest.fixture(autouse=True)
def stop_background_processes() -> Generator[None, None, None]:
    yield
    try:
        from swe.agents.tools.background_process import (
            managed_background_process_manager,
        )
    except ImportError:
        return
    managed_background_process_manager.stop_all()


def _response_text(response) -> str:
    return response.content[0]["text"]


def _extract_process_id(text: str) -> str:
    match = re.search(r"process_id:\s*(bgp_[a-zA-Z0-9_]+)", text)
    assert match, text
    return match.group(1)


async def _wait_for_output(
    process_id: str,
    expected: str,
    *,
    status: str | None = None,
) -> str:
    from swe.agents.tools.background_process import get_process_output

    last_text = ""
    for _ in range(30):
        output = await get_process_output(process_id)
        last_text = _response_text(output)
        if expected in last_text and (
            status is None or f"status: {status}" in last_text
        ):
            return last_text
        await asyncio.sleep(0.1)
    return last_text


@pytest.mark.asyncio
async def test_start_short_command_lists_and_reads_output(
    tenant_workspace: dict[str, Path],
) -> None:
    from swe.agents.tools.background_process import (
        get_process_output,
        list_background_processes,
        start_background_process,
    )

    with tenant_context(
        tenant_id="tenant_a",
        user_id="user_a",
        source_id="source_a",
        workspace_dir=tenant_workspace["source_a"],
    ):
        started = await start_background_process(
            'python -c "print(\'bg hello\')"',
            name="short command",
        )
        process_id = _extract_process_id(_response_text(started))

        output_text = await _wait_for_output(process_id, "bg hello")
        listed = await list_background_processes()
        final_output = await get_process_output(process_id)

    assert "Background process started" in _response_text(started)
    assert process_id in _response_text(listed)
    assert "short command" in _response_text(listed)
    assert "bg hello" in output_text
    assert "status:" in _response_text(final_output)


@pytest.mark.asyncio
async def test_stop_running_process_preserves_captured_output(
    tenant_workspace: dict[str, Path],
) -> None:
    from swe.agents.tools.background_process import (
        get_process_output,
        start_background_process,
        stop_background_process,
    )

    with tenant_context(
        tenant_id="tenant_a",
        user_id="user_a",
        source_id="source_a",
        workspace_dir=tenant_workspace["source_a"],
    ):
        started = await start_background_process(
            "python -c \"import time; print('ready', flush=True); "
            'time.sleep(30)"',
            name="sleeping command",
        )
        process_id = _extract_process_id(_response_text(started))
        assert "ready" in await _wait_for_output(process_id, "ready")

        stopped = await stop_background_process(process_id)
        output = await get_process_output(process_id)

    assert "stopped" in _response_text(stopped)
    assert "ready" in _response_text(output)
    assert "status: stopped" in _response_text(output)


@pytest.mark.asyncio
async def test_source_owner_cannot_list_read_or_stop_other_source_process(
    tenant_workspace: dict[str, Path],
) -> None:
    from swe.agents.tools.background_process import (
        get_process_output,
        list_background_processes,
        start_background_process,
        stop_background_process,
    )

    with tenant_context(
        tenant_id="tenant_a",
        user_id="user_a",
        source_id="source_a",
        workspace_dir=tenant_workspace["source_a"],
    ):
        started = await start_background_process(
            "python -c \"import time; time.sleep(30)\"",
            name="source a",
        )
        process_id = _extract_process_id(_response_text(started))

    with tenant_context(
        tenant_id="tenant_a",
        user_id="user_a",
        source_id="source_b",
        workspace_dir=tenant_workspace["source_b"],
    ):
        listed = await list_background_processes()
        output = await get_process_output(process_id)
        stopped = await stop_background_process(process_id)

    with tenant_context(
        tenant_id="tenant_a",
        user_id="user_a",
        source_id="source_a",
        workspace_dir=tenant_workspace["source_a"],
    ):
        cleanup = await stop_background_process(process_id)

    assert process_id not in _response_text(listed)
    missing_process = f"Process not found in current scope: {process_id}"
    assert missing_process in _response_text(
        output,
    )
    assert missing_process in _response_text(
        stopped,
    )
    assert "stopped" in _response_text(cleanup)


@pytest.mark.asyncio
async def test_python_runtime_guard_blocks_dynamic_path_escape(
    tenant_workspace: dict[str, Path],
) -> None:
    from swe.agents.tools.background_process import start_background_process

    secret_file = tenant_workspace["source_b"] / "secret.txt"
    secret_file.write_text("source b secret")
    source_b_scope = encode_scope_id("tenant_a", "source_b")
    code = (
        "import os; "
        "path = os.path.join('..', '..', '..', "
        f"'{source_b_scope}', 'workspaces', 'agent_a', 'secret.txt'); "
        "print(open(path).read())"
    )

    with tenant_context(
        tenant_id="tenant_a",
        user_id="user_a",
        source_id="source_a",
        workspace_dir=tenant_workspace["source_a"],
    ):
        started = await start_background_process(
            f'python -c "{code}"',
            name="dynamic escape",
        )
        process_id = _extract_process_id(_response_text(started))
        output_text = await _wait_for_output(
            process_id,
            "outside the allowed workspace",
            status="failed",
        )

    assert "status: failed" in output_text
    assert "outside the allowed workspace" in output_text
    assert "source b secret" not in output_text


@pytest.mark.asyncio
async def test_get_process_output_clamps_to_bounded_tail(
    tenant_workspace: dict[str, Path],
) -> None:
    from swe.agents.tools.background_process import (
        get_process_output,
        start_background_process,
    )

    with tenant_context(
        tenant_id="tenant_a",
        user_id="user_a",
        source_id="source_a",
        workspace_dir=tenant_workspace["source_a"],
    ):
        started = await start_background_process(
            "python -c \"print('prefix-' + 'x' * 200 + '-tail')\"",
            name="large output",
        )
        process_id = _extract_process_id(_response_text(started))
        await _wait_for_output(process_id, "-tail")
        output = await get_process_output(process_id, max_bytes=32)

    text = _response_text(output)
    assert "truncated: true" in text
    assert "-tail" in text
    assert "prefix-" not in text


@pytest.mark.asyncio
async def test_per_owner_running_process_limit_is_enforced(
    tenant_workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from swe.agents.tools import background_process
    from swe.agents.tools.background_process import (
        start_background_process,
        stop_background_process,
    )

    monkeypatch.setattr(
        background_process,
        "MAX_RUNNING_PROCESSES_PER_OWNER",
        1,
    )

    with tenant_context(
        tenant_id="tenant_a",
        user_id="user_a",
        source_id="source_a",
        workspace_dir=tenant_workspace["source_a"],
    ):
        started = await start_background_process(
            "python -c \"import time; time.sleep(30)\"",
            name="first",
        )
        process_id = _extract_process_id(_response_text(started))
        with pytest.raises(ToolExecutionError) as exc_info:
            await start_background_process(
                "python -c \"import time; time.sleep(30)\"",
                name="second",
            )
        await stop_background_process(process_id)

    assert exc_info.value.error_type == "resource_limit_exceeded"
    assert "per owner" in exc_info.value.detail


@pytest.mark.asyncio
async def test_concurrent_start_reserves_per_owner_capacity(
    tenant_workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from swe.agents.tools import background_process
    from swe.agents.tools.background_process import (
        start_background_process,
        stop_background_process,
    )

    prepare_calls = 0
    original_prepare = background_process.prepare_shell_command

    def slow_prepare_shell_command(command: str, cwd: Path | str | None):
        nonlocal prepare_calls
        prepare_calls += 1
        time.sleep(0.3)
        return original_prepare(command, cwd)

    monkeypatch.setattr(
        background_process,
        "MAX_RUNNING_PROCESSES_PER_OWNER",
        1,
    )
    monkeypatch.setattr(
        background_process,
        "prepare_shell_command",
        slow_prepare_shell_command,
    )

    with tenant_context(
        tenant_id="tenant_a",
        user_id="user_a",
        source_id="source_a",
        workspace_dir=tenant_workspace["source_a"],
    ):
        results = await asyncio.gather(
            start_background_process(
                "python -c \"import time; time.sleep(30)\"",
                name="first",
            ),
            start_background_process(
                "python -c \"import time; time.sleep(30)\"",
                name="second",
            ),
            return_exceptions=True,
        )

        successes = [
            result for result in results if not isinstance(result, Exception)
        ]
        failures = [
            result for result in results if isinstance(result, Exception)
        ]
        for success in successes:
            await stop_background_process(
                _extract_process_id(_response_text(success)),
            )

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], ToolExecutionError)
    assert failures[0].error_type == "resource_limit_exceeded"
    assert prepare_calls == 1


@pytest.mark.asyncio
async def test_stop_all_clears_process_registry(
    tenant_workspace: dict[str, Path],
) -> None:
    from swe.agents.tools.background_process import (
        list_background_processes,
        managed_background_process_manager,
        start_background_process,
    )

    with tenant_context(
        tenant_id="tenant_a",
        user_id="user_a",
        source_id="source_a",
        workspace_dir=tenant_workspace["source_a"],
    ):
        started = await start_background_process(
            "python -c \"import time; time.sleep(30)\"",
            name="cleanup",
        )
        process_id = _extract_process_id(_response_text(started))
        managed_background_process_manager.stop_all()
        listed = await list_background_processes()

    assert process_id not in _response_text(listed)
    assert "No background processes" in _response_text(listed)
