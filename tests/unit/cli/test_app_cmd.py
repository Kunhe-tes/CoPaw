# -*- coding: utf-8 -*-
"""Tests for the ``swe app`` CLI command."""

from unittest.mock import Mock

from click.testing import CliRunner

from swe.cli import app_cmd as app_cmd_module
from swe.cli.app_cmd import app_cmd


def test_app_cmd_hides_health_access_logs_by_default():
    """Health probes should be excluded from uvicorn access logs by default."""
    hide_access_paths_option = next(
        param for param in app_cmd.params if param.name == "hide_access_paths"
    )

    assert "/api/health/health" in hide_access_paths_option.default


def test_select_uvicorn_loop_uses_uvloop_when_available(monkeypatch):
    """Non-Windows service startup should prefer uvloop when installed."""
    monkeypatch.setattr(app_cmd_module.sys, "platform", "linux")
    monkeypatch.setattr(
        app_cmd_module.importlib.util,
        "find_spec",
        lambda name: object() if name == "uvloop" else None,
    )

    assert app_cmd_module._select_uvicorn_loop() == "uvloop"


def test_select_uvicorn_loop_falls_back_without_uvloop(monkeypatch):
    """Missing uvloop should not prevent the service from starting."""
    monkeypatch.setattr(app_cmd_module.sys, "platform", "linux")
    monkeypatch.setattr(
        app_cmd_module.importlib.util,
        "find_spec",
        lambda _: None,
    )

    assert app_cmd_module._select_uvicorn_loop() == "auto"


def test_select_uvicorn_loop_uses_auto_on_windows(monkeypatch):
    """uvloop is not supported on Windows."""
    monkeypatch.setattr(app_cmd_module.sys, "platform", "win32")
    monkeypatch.setattr(
        app_cmd_module.importlib.util,
        "find_spec",
        lambda name: object() if name == "uvloop" else None,
    )

    assert app_cmd_module._select_uvicorn_loop() == "auto"


def test_app_cmd_passes_selected_loop_to_uvicorn(monkeypatch):
    """The CLI should pass the selected event loop mode to uvicorn."""
    uvicorn_run = Mock()
    monkeypatch.setattr(app_cmd_module.uvicorn, "run", uvicorn_run)
    monkeypatch.setattr(app_cmd_module, "write_last_api", Mock())
    monkeypatch.setattr(app_cmd_module, "setup_logger", Mock())
    monkeypatch.setattr(
        app_cmd_module,
        "_select_uvicorn_loop",
        lambda: "uvloop",
    )

    result = CliRunner().invoke(
        app_cmd,
        ["--host", "127.0.0.1", "--port", "9123"],
    )

    assert result.exit_code == 0
    uvicorn_run.assert_called_once()
    assert uvicorn_run.call_args.kwargs["loop"] == "uvloop"
