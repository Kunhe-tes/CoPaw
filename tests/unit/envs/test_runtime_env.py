# -*- coding: utf-8 -*-
"""租户运行时 env helper 的单元测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from swe.config.context import encode_scope_id, tenant_context
from swe.envs.store import load_envs, save_envs


def _patch_working_dir(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr("swe.config.utils.WORKING_DIR", root)


def _tenant_env_path(root: Path, tenant_id: str, source_id: str) -> Path:
    scope_id = encode_scope_id(tenant_id, source_id)
    return root / scope_id / ".secret" / "envs.json"


def test_validate_env_key_rejects_malformed_and_protected_names() -> None:
    from swe.envs.runtime import validate_env_key

    validate_env_key("API_TOKEN")

    for key in ("", "1TOKEN", "BAD-NAME", "PATH"):
        with pytest.raises(ValueError, match=key or "empty"):
            validate_env_key(key)


def test_build_runtime_env_uses_scope_file_precedence_and_filters_protected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from swe.envs.runtime import build_runtime_env

    _patch_working_dir(monkeypatch, tmp_path)
    save_envs(
        {
            "API_TOKEN": "tenant-secret",
            "TENANT_ONLY": "present",
            "PATH": "/tenant/bin",
            "PYTHONPATH": "/tenant/python",
        },
        _tenant_env_path(tmp_path, "tenant-a", "source-a"),
    )
    monkeypatch.setenv("API_TOKEN", "process-secret")
    before = dict(os.environ)

    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        env = build_runtime_env(
            base_env={"API_TOKEN": "process-secret", "PATH": "/usr/bin"},
            call_env={
                "API_TOKEN": "call-secret",
                "CALL_ONLY": "yes",
                "PYTHONPATH": "/call/python",
            },
        )

    assert env["API_TOKEN"] == "call-secret"
    assert env["TENANT_ONLY"] == "present"
    assert env["CALL_ONLY"] == "yes"
    assert env["PATH"] == "/usr/bin"
    assert "PYTHONPATH" not in env
    assert os.environ == before


def test_build_runtime_env_removes_system_configuration_and_boundary_keys() -> (
    None
):
    from swe.envs.runtime import build_runtime_env

    env = build_runtime_env(
        base_env={
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "SWE_DB_ACCESS": "backend-secret",
            "SWE_SECRET_DIR": "/srv/swe.secret",
            "PYTHONPATH": "/backend/python",
            "SWE_TENANT_PATH_GUARD_ROOT": "/tenant/root",
        },
        call_env={
            "SWE_ZHAOHU_CLIENT_SECRET_POSEIDON": "call-secret",
            "CALL_ONLY": "yes",
        },
    )

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/home/user"
    assert env["CALL_ONLY"] == "yes"
    assert env["SWE_TENANT_PATH_GUARD_ROOT"] == "/tenant/root"
    assert "SWE_DB_ACCESS" not in env
    assert "SWE_ZHAOHU_CLIENT_SECRET_POSEIDON" not in env
    assert "SWE_SECRET_DIR" not in env
    assert "PYTHONPATH" not in env


def test_build_runtime_env_removes_non_default_backend_secrets() -> None:
    from swe.envs.runtime import build_runtime_env

    env = build_runtime_env(
        base_env={
            "PATH": "/usr/bin",
            "SWE_AUTH_PASSWORD": "auth-secret",
            "SWE_INTERNAL_TOKEN": "internal-secret",
            "TITLE_API_KEY": "title-secret",
            "ZHAOHU_CLIENT_SECRET": "zhaohu-secret",
            "ZHAOHU_INTENT_API_KEY": "intent-secret",
        },
    )

    assert env["PATH"] == "/usr/bin"
    assert "SWE_AUTH_PASSWORD" not in env
    assert "SWE_INTERNAL_TOKEN" not in env
    assert "TITLE_API_KEY" not in env
    assert "ZHAOHU_CLIENT_SECRET" not in env
    assert "ZHAOHU_INTENT_API_KEY" not in env


def test_missing_context_does_not_read_default_env_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from swe.envs.runtime import build_runtime_env

    _patch_working_dir(monkeypatch, tmp_path)
    save_envs(
        {"API_TOKEN": "default-secret"},
        tmp_path / "default" / ".secret" / "envs.json",
    )

    env = build_runtime_env(base_env={})

    assert "API_TOKEN" not in env


def test_runtime_env_lookup_is_source_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from swe.envs.runtime import load_tenant_runtime_env

    _patch_working_dir(monkeypatch, tmp_path)
    save_envs(
        {"API_TOKEN": "source-a"},
        _tenant_env_path(tmp_path, "tenant-a", "source-a"),
    )
    save_envs(
        {"API_TOKEN": "source-b"},
        _tenant_env_path(tmp_path, "tenant-a", "source-b"),
    )

    with tenant_context(tenant_id="tenant-a", source_id="source-b"):
        env = load_tenant_runtime_env()

    assert env == {"API_TOKEN": "source-b"}


def test_save_envs_uses_atomic_replace_and_preserves_existing_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envs_path = tmp_path / "tenant-a" / ".secret" / "envs.json"
    save_envs({"OLD": "value"}, envs_path)

    def fail_replace(
        src: str | bytes | os.PathLike,
        dst: str | bytes | os.PathLike,
    ) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("swe.envs.store.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        save_envs({"NEW": "value"}, envs_path)

    assert load_envs(envs_path) == {"OLD": "value"}


def test_save_envs_secret_file_permissions(tmp_path: Path) -> None:
    envs_path = tmp_path / "tenant-a" / ".secret" / "envs.json"

    save_envs({"API_TOKEN": "secret"}, envs_path)

    assert envs_path.stat().st_mode & 0o777 == 0o600
    assert envs_path.parent.stat().st_mode & 0o777 == 0o700
