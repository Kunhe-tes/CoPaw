# -*- coding: utf-8 -*-
"""Tests for the ``swe app`` CLI command."""

from swe.cli.app_cmd import app_cmd


def test_app_cmd_hides_health_access_logs_by_default():
    """Health probes should be excluded from uvicorn access logs by default."""
    hide_access_paths_option = next(
        param for param in app_cmd.params if param.name == "hide_access_paths"
    )

    assert "/api/health/health" in hide_access_paths_option.default
