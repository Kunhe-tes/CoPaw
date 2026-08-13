# -*- coding: utf-8 -*-
"""Recovery lifecycle tests for explicitly invalid bootstrap JSON files."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "src"))

import swe.app.workspace.tenant_initializer as initializer_module
from swe.app.workspace.bootstrap_state import (
    BootstrapReadiness,
    BootstrapRecoveryFailure,
)
from swe.app.workspace.tenant_initializer import TenantInitializer


def test_recovery_removes_its_backup_after_final_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "tenant-a" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{broken", encoding="utf-8")
    invalid = BootstrapReadiness(
        ready=False,
        missing_paths=(),
        invalid_json_paths=(config_path,),
        reason="invalid_json",
    )
    ready = BootstrapReadiness(True, (), (), "ready")
    monkeypatch.setattr(
        initializer_module,
        "inspect_bootstrap_readiness",
        lambda _tenant_dir: invalid if config_path.exists() else ready,
    )
    monkeypatch.setattr(
        TenantInitializer,
        "ensure_seeded_bootstrap",
        lambda self, **_kwargs: {"minimal": True},
    )

    result = TenantInitializer(tmp_path, "tenant-a").recover_seeded_bootstrap()

    assert result["recovered_paths"] == [str(config_path)]
    assert list(config_path.parent.glob("config.json.*.bak")) == []


def test_recovery_retains_backup_when_final_readiness_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "tenant-a" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{broken", encoding="utf-8")
    invalid = BootstrapReadiness(
        ready=False,
        missing_paths=(),
        invalid_json_paths=(config_path,),
        reason="invalid_json",
    )
    monkeypatch.setattr(
        initializer_module,
        "inspect_bootstrap_readiness",
        lambda _tenant_dir: invalid,
    )
    monkeypatch.setattr(
        TenantInitializer,
        "ensure_seeded_bootstrap",
        lambda self, **_kwargs: {"minimal": True},
    )

    with pytest.raises(BootstrapRecoveryFailure):
        TenantInitializer(tmp_path, "tenant-a").recover_seeded_bootstrap()

    assert list(config_path.parent.glob("config.json.*.bak"))
