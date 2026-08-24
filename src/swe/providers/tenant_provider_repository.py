# -*- coding: utf-8 -*-
"""Tenant-scoped provider configuration persistence."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from swe.providers.models import ModelSlotConfig


class TenantProviderRepository:
    """Read and write provider data under one secret-directory root."""

    def __init__(self, secret_dir: Path) -> None:
        self.secret_dir = secret_dir

    def root_path(self, scope: str) -> Path:
        return self.secret_dir / scope / "providers"

    def builtin_path(self, scope: str) -> Path:
        return self.root_path(scope) / "builtin"

    def custom_path(self, scope: str) -> Path:
        return self.root_path(scope) / "custom"

    def prepare_scope(self, scope: str) -> "TenantProviderRepository.Paths":
        root = self.root_path(scope)
        if not root.exists() and scope != "default":
            default_root = self.root_path("default")
            if default_root.exists():
                shutil.copytree(default_root, root)
        for path in (root, root / "builtin", root / "custom"):
            path.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(path, 0o700)
            except OSError:
                pass
        return self.Paths(
            root=root,
            builtin=root / "builtin",
            custom=root / "custom",
        )

    def provider_path(
        self,
        scope: str,
        provider_id: str,
        *,
        is_builtin: bool,
    ) -> Path:
        provider_dir = (
            self.builtin_path(scope) if is_builtin else self.custom_path(scope)
        )
        return provider_dir / f"{provider_id}.json"

    def write_provider(
        self,
        scope: str,
        payload: dict[str, Any],
        *,
        is_builtin: bool,
        skip_if_exists: bool = False,
    ) -> Path:
        self.prepare_scope(scope)
        provider_path = self.provider_path(
            scope,
            str(payload["id"]),
            is_builtin=is_builtin,
        )
        if skip_if_exists and provider_path.exists():
            return provider_path
        provider_path.write_bytes(
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        self._restrict_file_permissions(provider_path)
        return provider_path

    def read_provider(
        self,
        scope: str,
        provider_id: str,
        *,
        is_builtin: bool,
    ) -> dict[str, Any] | None:
        provider_path = self.provider_path(
            scope,
            provider_id,
            is_builtin=is_builtin,
        )
        try:
            data = json.loads(provider_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def delete_provider(
        self,
        scope: str,
        provider_id: str,
        *,
        is_builtin: bool,
    ) -> None:
        try:
            self.provider_path(
                scope,
                provider_id,
                is_builtin=is_builtin,
            ).unlink()
        except FileNotFoundError:
            pass

    def write_active_model(
        self,
        scope: str,
        active_model: ModelSlotConfig,
    ) -> Path:
        self.prepare_scope(scope)
        active_path = self.root_path(scope) / "active_model.json"
        active_path.write_bytes(
            json.dumps(
                active_model.model_dump(),
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
        )
        self._restrict_file_permissions(active_path)
        return active_path

    def read_active_model(self, scope: str) -> ModelSlotConfig | None:
        try:
            data = json.loads(
                (self.root_path(scope) / "active_model.json").read_text(
                    encoding="utf-8",
                ),
            )
            return ModelSlotConfig.model_validate(data)
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def freshness_token(self, scope: str) -> tuple[tuple[str, int, int], ...]:
        root = self.root_path(scope)
        if not root.exists():
            return ()
        try:
            return tuple(
                sorted(
                    (
                        str(path.relative_to(root)),
                        path.stat().st_mtime_ns,
                        path.stat().st_size,
                    )
                    for path in root.rglob("*.json")
                ),
            )
        except OSError:
            return ()

    @staticmethod
    def _restrict_file_permissions(path: Path) -> None:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    class Paths:
        def __init__(self, *, root: Path, builtin: Path, custom: Path) -> None:
            self.root = root
            self.builtin = builtin
            self.custom = custom
