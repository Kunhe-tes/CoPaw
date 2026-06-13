# -*- coding: utf-8 -*-
"""Unit tests for tenant-aware CLI init command.

Tests that `swe init --tenant-id <id>` writes config to the correct
tenant directory structure, and that backward compatibility is preserved.
"""

import sys
from types import ModuleType
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import pytest
from click.testing import CliRunner
from swe.cli.init_cmd import init_cmd


def _patch_provider_manager(monkeypatch):
    """Mock ProviderManager to avoid side effects."""

    class MockProviderManager:
        _instance = None

        def __init__(self, *args, **kwargs):
            pass

        @classmethod
        def get_instance(cls):
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

        def get_active_provider(self):
            return None

        def get_active_model(self):
            return None

    monkeypatch.setattr(
        "swe.cli.init_cmd.ProviderManager",
        MockProviderManager,
    )


def test_init_cmd_writes_to_tenant_directory(tmp_path, monkeypatch):
    """Test that --tenant-id writes config to tenant-specific directory."""
    # Patch WORKING_DIR to use tmp_path
    monkeypatch.setattr("swe.cli.init_cmd.WORKING_DIR", tmp_path)
    monkeypatch.setattr("swe.constant.WORKING_DIR", tmp_path)

    _patch_provider_manager(monkeypatch)

    runner = CliRunner()

    result = runner.invoke(
        init_cmd,
        ["--defaults", "--accept-security", "--tenant-id", "tenant-acme"],
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "tenant-acme" / "config.json").exists()
    assert (tmp_path / "tenant-acme" / "HEARTBEAT.md").exists()
    assert (tmp_path / "tenant-acme" / "workspaces" / "default").is_dir()


def test_init_cmd_defaults_tenant_id_to_default(tmp_path, monkeypatch):
    """Test that init without --tenant-id defaults to 'default' tenant."""
    # Patch WORKING_DIR to use tmp_path
    monkeypatch.setattr("swe.cli.init_cmd.WORKING_DIR", tmp_path)
    monkeypatch.setattr("swe.constant.WORKING_DIR", tmp_path)

    _patch_provider_manager(monkeypatch)

    runner = CliRunner()

    result = runner.invoke(init_cmd, ["--defaults", "--accept-security"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "default" / "config.json").exists()
    assert not (tmp_path / ".telemetry_collected").exists()
    # Ensure old flat structure is NOT created
    assert not (tmp_path / "config.json").exists()


def test_init_cmd_does_not_import_telemetry(tmp_path, monkeypatch):
    """Init should not import telemetry or attempt usage collection."""
    monkeypatch.setattr("swe.cli.init_cmd.WORKING_DIR", tmp_path)
    monkeypatch.setattr("swe.constant.WORKING_DIR", tmp_path)
    _patch_provider_manager(monkeypatch)

    telemetry_module = ModuleType("swe.utils.telemetry")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("telemetry should not be used")

    telemetry_module.collect_and_upload_telemetry = fail_if_called
    telemetry_module.has_telemetry_been_collected = fail_if_called
    telemetry_module.is_telemetry_opted_out = fail_if_called
    telemetry_module.mark_telemetry_collected = fail_if_called
    monkeypatch.setitem(sys.modules, "swe.utils.telemetry", telemetry_module)

    result = CliRunner().invoke(
        init_cmd,
        ["--defaults", "--accept-security"],
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "default" / "config.json").exists()
