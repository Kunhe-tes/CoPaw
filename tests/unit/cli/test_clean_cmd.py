# -*- coding: utf-8 -*-
from __future__ import annotations

from click.testing import CliRunner

from swe.cli.clean_cmd import clean_cmd


def test_clean_cmd_removes_legacy_telemetry_marker(tmp_path, monkeypatch):
    monkeypatch.setattr("swe.cli.clean_cmd.WORKING_DIR", tmp_path)
    marker = tmp_path / ".telemetry_collected"
    marker.write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(clean_cmd, ["--yes"])

    assert result.exit_code == 0, result.output
    assert not marker.exists()
