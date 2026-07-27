# -*- coding: utf-8 -*-
import asyncio
import os
import signal
import sys
from contextlib import asynccontextmanager, nullcontext
from types import SimpleNamespace

import pytest


def test_normalize_tool_output_keeps_utf8_safe_head_and_tail():
    from swe.app.runner.tool_output_frames import normalize_tool_output

    text = "首段\n" + ("中间数据\n" * 200) + "尾段\n"

    normalized = normalize_tool_output(
        text,
        max_bytes=512,
        max_lines=20,
    )

    assert normalized.startswith("首段\n")
    assert normalized.endswith("尾段\n")
    assert "[工具输出已截断：原始" in normalized
    assert "省略" in normalized
    assert len(normalized.encode("utf-8")) <= 512
    assert normalized.count("\n") <= 20


def test_normalize_tool_output_leaves_within_budget_text_unchanged():
    from swe.app.runner.tool_output_frames import normalize_tool_output

    assert (
        normalize_tool_output(
            "stdout\nstderr\n",
            max_bytes=512,
            max_lines=20,
        )
        == "stdout\nstderr\n"
    )


@pytest.mark.asyncio
async def test_shell_terminal_result_uses_live_output_budget(
    monkeypatch,
    tmp_path,
):
    from swe.agents.tools import shell
    from swe.app.runner.tool_output_frames import normalize_tool_output

    raw_output = "head\n" + ("middle\n" * 20_000) + "tail\n"

    async def fake_subprocess(*_args, **_kwargs):
        return 0, raw_output, ""

    @asynccontextmanager
    async def no_execution_slot(_policy):
        yield

    monkeypatch.setattr(
        shell,
        "prepare_shell_command",
        lambda *_args, **_kwargs: SimpleNamespace(
            command="echo ignored",
            working_dir=tmp_path,
            env=os.environ.copy(),
            python_runtime_guard=nullcontext(),
        ),
    )
    monkeypatch.setattr(
        shell,
        "resolve_current_process_limit_policy",
        lambda _tool_name: SimpleNamespace(build_preexec_fn=lambda: None),
    )
    monkeypatch.setattr(
        shell,
        "_tenant_shell_execution_slot",
        no_execution_slot,
    )
    monkeypatch.setattr(shell, "_execute_platform_subprocess", fake_subprocess)
    monkeypatch.setattr(
        shell,
        "_format_process_limit_diagnostic",
        lambda text, _policy: text,
    )

    result = await shell.execute_shell_command("echo ignored")

    assert result.content[0]["text"] == normalize_tool_output(raw_output)


@pytest.mark.asyncio
async def test_live_frame_budget_includes_omission_marker():
    from swe.app.runner.tool_output_frames import (
        LIVE_TOOL_OUTPUT_MAX_BYTES,
        bind_tool_output_emitter,
        emit_tool_output_text,
        tool_output_invocation,
    )

    frames = []

    async def collect(frame):
        frames.append(frame)

    with (
        bind_tool_output_emitter(collect),
        tool_output_invocation(
            tool_call_id="call-1",
            tool_name="execute_shell_command",
        ),
    ):
        await emit_tool_output_text(
            "stdout",
            "x" * (LIVE_TOOL_OUTPUT_MAX_BYTES + 1),
        )

    assert sum(len(frame["text"].encode("utf-8")) for frame in frames) <= (
        LIVE_TOOL_OUTPUT_MAX_BYTES
    )
    assert frames[-1]["truncated"] is True
    assert "[早期实时输出已省略]" in frames[-1]["text"]


@pytest.mark.asyncio
async def test_unix_shell_emits_live_stdout_and_stderr_frames(tmp_path):
    if sys.platform == "win32":
        pytest.skip("Unix subprocess live output is not used on Windows")

    from swe.agents.tools import shell
    from swe.app.runner.tool_output_frames import (
        bind_tool_output_emitter,
        tool_output_invocation,
    )

    frames = []

    async def collect(frame):
        frames.append(frame)

    with (
        bind_tool_output_emitter(collect),
        tool_output_invocation(
            tool_call_id="call-1",
            tool_name="execute_shell_command",
        ),
    ):
        returncode, stdout, stderr = await shell._execute_unix_subprocess(
            "printf 'out-line\\n'; printf 'err-line\\n' >&2",
            tmp_path,
            5,
            os.environ.copy(),
        )

    assert returncode == 0
    assert stdout == "out-line"
    assert stderr == "err-line"

    assert {frame["source"] for frame in frames} == {"stdout", "stderr"}
    assert {frame["text"] for frame in frames} == {"out-line\n", "err-line\n"}
    assert all(frame["object"] == "tool_output_frame" for frame in frames)
    assert all(frame["tool_call_id"] == "call-1" for frame in frames)
    assert all(
        frame["tool_name"] == "execute_shell_command" for frame in frames
    )
    assert [frame["sequence"] for frame in frames] == [1, 2]


@pytest.mark.asyncio
async def test_unix_shell_success_cleans_background_pipe_holders(tmp_path):
    if sys.platform == "win32":
        pytest.skip("Unix subprocess live output is not used on Windows")

    from swe.agents.tools import shell

    returncode, stdout, stderr = await asyncio.wait_for(
        shell._execute_unix_subprocess(
            "sleep 2 & echo done",
            tmp_path,
            1,
            os.environ.copy(),
        ),
        timeout=1,
    )

    assert returncode == 0
    assert stdout == "done"
    assert stderr == ""


@pytest.mark.asyncio
async def test_unix_shell_success_kills_sigterm_ignoring_pipe_holders(
    tmp_path,
):
    if sys.platform == "win32":
        pytest.skip("Unix subprocess live output is not used on Windows")

    from swe.agents.tools import shell

    pid_file = tmp_path / "background.pid"
    background_pid: int | None = None
    try:
        returncode, stdout, stderr = await asyncio.wait_for(
            shell._execute_unix_subprocess(
                (
                    "trap '' TERM; "
                    "while :; do sleep 1; done & "
                    f"echo $! > {pid_file}; "
                    "echo done"
                ),
                tmp_path,
                0.1,
                os.environ.copy(),
            ),
            timeout=4,
        )

        background_pid = int(pid_file.read_text().strip())

        assert returncode == 0
        assert stdout == "done"
        assert stderr == ""
        with pytest.raises(ProcessLookupError):
            os.kill(background_pid, 0)
    finally:
        if background_pid is not None:
            try:
                os.killpg(os.getpgid(background_pid), signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.asyncio
async def test_unix_shell_success_cleans_background_process_group(tmp_path):
    if sys.platform == "win32":
        pytest.skip("Unix subprocess live output is not used on Windows")

    from swe.agents.tools import shell

    pid_file = tmp_path / "background.pid"
    background_pid: int | None = None
    try:
        returncode, stdout, stderr = await asyncio.wait_for(
            shell._execute_unix_subprocess(
                (
                    "sleep 30 >/dev/null 2>&1 & "
                    f"echo $! > {pid_file}; "
                    "echo done"
                ),
                tmp_path,
                5,
                os.environ.copy(),
            ),
            timeout=4,
        )

        background_pid = int(pid_file.read_text().strip())

        assert returncode == 0
        assert stdout == "done"
        assert stderr == ""
        with pytest.raises(ProcessLookupError):
            os.kill(background_pid, 0)
    finally:
        if background_pid is not None:
            try:
                os.killpg(os.getpgid(background_pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
