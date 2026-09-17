# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest

from swe.agents.tool_failure import ToolExecutionError
from swe.agents.tools import file_io


def _install_fake_runtime_worker(
    monkeypatch,
    state: dict[str, object],
) -> None:
    state["in_worker"] = False
    state["worker_calls"] = []

    async def fake_run_runtime_state_work(func, /, *args, **kwargs):
        state["worker_calls"].append(func.__name__)
        assert state["in_worker"] is False
        state["in_worker"] = True
        try:
            return func(*args, **kwargs)
        finally:
            state["in_worker"] = False

    monkeypatch.setattr(
        file_io,
        "run_runtime_state_work",
        fake_run_runtime_state_work,
        raising=False,
    )


@pytest.mark.asyncio
async def test_read_file_processes_text_inside_runtime_worker(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "note.md"
    target.write_text("alpha\nbeta\ngamma", encoding="utf-8")
    state: dict[str, object] = {}
    _install_fake_runtime_worker(monkeypatch, state)
    monkeypatch.setattr(file_io, "_resolve_file_path", lambda _: str(target))

    def fake_read_file_safe(path: str) -> str:
        assert path == str(target)
        assert state["in_worker"] is True
        state["read_in_worker"] = True
        return "alpha\nbeta\ngamma"

    def fake_truncate_text_output(text: str, **kwargs) -> str:
        assert state["in_worker"] is True
        state["truncate_in_worker"] = True
        assert text == "beta\ngamma"
        assert kwargs["start_line"] == 2
        assert kwargs["total_lines"] == 3
        assert kwargs["file_path"] == str(target)
        return text

    monkeypatch.setattr(file_io, "read_file_safe", fake_read_file_safe)
    monkeypatch.setattr(
        file_io,
        "truncate_text_output",
        fake_truncate_text_output,
    )

    result = await file_io.read_file("logical/path.md", start_line=2)

    assert result.content[0]["text"] == "beta\ngamma"
    assert state["read_in_worker"] is True
    assert state["truncate_in_worker"] is True
    assert state["worker_calls"] == ["_read_file_selection_sync"]


@pytest.mark.asyncio
async def test_edit_file_reads_and_replaces_inside_runtime_worker(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "note.md"
    target.write_text("alpha old omega", encoding="utf-8")
    state: dict[str, object] = {}
    _install_fake_runtime_worker(monkeypatch, state)
    monkeypatch.setattr(file_io, "_resolve_file_path", lambda _: str(target))
    monkeypatch.setattr(
        file_io,
        "_resolve_writable_file_path",
        lambda _: str(target),
    )

    class ReplacementProbe:
        def __contains__(self, needle: str) -> bool:
            assert state["in_worker"] is True
            state["contains_in_worker"] = True
            return needle == "old"

        def replace(self, old_text: str, new_text: str) -> str:
            assert state["in_worker"] is True
            state["replace_in_worker"] = True
            assert old_text == "old"
            assert new_text == "new"
            return "alpha new omega"

    def fake_read_file_safe(path: str) -> ReplacementProbe:
        assert path == str(target)
        assert state["in_worker"] is True
        state["read_in_worker"] = True
        return ReplacementProbe()

    monkeypatch.setattr(file_io, "read_file_safe", fake_read_file_safe)

    result = await file_io.edit_file("logical/path.md", "old", "new")

    assert target.read_text(encoding="utf-8") == "alpha new omega"
    assert "Successfully replaced text in logical/path.md." in (
        result.content[0]["text"]
    )
    assert state["read_in_worker"] is True
    assert state["contains_in_worker"] is True
    assert state["replace_in_worker"] is True
    assert state["worker_calls"] == ["_replace_file_text_sync"]


@pytest.mark.asyncio
async def test_read_file_invalid_line_arguments_do_not_use_runtime_worker(
    monkeypatch,
):
    state: dict[str, object] = {}

    async def fail_if_called(*_args, **_kwargs):
        state["worker_called"] = True
        raise AssertionError("runtime worker should not be called")

    monkeypatch.setattr(
        file_io,
        "run_runtime_state_work",
        fail_if_called,
        raising=False,
    )

    with pytest.raises(ToolExecutionError) as exc_info:
        await file_io.read_file("logical/path.md", start_line="first")

    assert exc_info.value.error_type == "invalid_arguments"
    assert (
        exc_info.value.detail
        == "Error: start_line must be an integer, got 'first'."
    )
    assert "worker_called" not in state


@pytest.mark.asyncio
async def test_read_file_start_line_beyond_eof_returns_guidance(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "note.md"
    target.write_text("alpha\nbeta", encoding="utf-8")
    state: dict[str, object] = {}
    _install_fake_runtime_worker(monkeypatch, state)
    monkeypatch.setattr(file_io, "_resolve_file_path", lambda _: str(target))

    result = await file_io.read_file("logical/path.md", start_line=200)

    text = result.content[0]["text"]
    assert "Requested start_line 200 exceeds file length (2 lines)." in text
    assert "No content was returned." in text
    assert "start_line=2" in text
    assert state["worker_calls"] == ["_read_file_selection_sync"]


@pytest.mark.asyncio
async def test_edit_file_old_text_not_found_maps_worker_error_to_not_found(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "note.md"
    target.write_text("alpha omega", encoding="utf-8")
    state: dict[str, object] = {}
    _install_fake_runtime_worker(monkeypatch, state)
    monkeypatch.setattr(file_io, "_resolve_file_path", lambda _: str(target))

    def fake_read_file_safe(path: str) -> str:
        assert path == str(target)
        assert state["in_worker"] is True
        return "alpha omega"

    monkeypatch.setattr(file_io, "read_file_safe", fake_read_file_safe)

    with pytest.raises(ToolExecutionError) as exc_info:
        await file_io.edit_file("logical/path.md", "missing", "new")

    assert exc_info.value.error_type == "not_found"
    assert (
        exc_info.value.detail
        == "Error: The text to replace was not found in logical/path.md."
    )
    assert state["worker_calls"] == ["_replace_file_text_sync"]
