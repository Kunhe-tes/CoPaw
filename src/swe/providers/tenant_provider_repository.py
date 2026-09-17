# -*- coding: utf-8 -*-
"""Tenant-scoped provider configuration persistence."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover (Windows)
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover (Unix)
    msvcrt = None

from swe.providers.models import ModelSlotConfig


class TenantProviderRepository:
    """Own provider paths, disk seeding, discovery, and atomic persistence."""

    def __init__(self, secret_dir: Path) -> None:
        self.secret_dir = secret_dir
        self._freshness_tokens: dict[
            str,
            dict[str, tuple[int, int]],
        ] = {}

    def root_path(self, scope: str) -> Path:
        from swe.config.utils import migrate_legacy_scope_dir_if_needed

        return (
            migrate_legacy_scope_dir_if_needed(self.secret_dir, scope)
            / "providers"
        )

    def builtin_path(self, scope: str) -> Path:
        return self.root_path(scope) / "builtin"

    def custom_path(self, scope: str) -> Path:
        return self.root_path(scope) / "custom"

    def prepare_scope(self, scope: str) -> "TenantProviderRepository.Paths":
        """Ensure one scoped provider tree exists without racing its template."""
        root = self.root_path(scope)
        self._ensure_scope(scope, root)
        for path in (root, root / "builtin", root / "custom"):
            path.mkdir(parents=True, exist_ok=True)
            self._restrict_directory_permissions(path)
        return self.Paths(
            root=root,
            builtin=root / "builtin",
            custom=root / "custom",
        )

    def ensure_scope(self, scope: str) -> None:
        """Public compatibility entry point for concurrency-safe seeding."""
        self.prepare_scope(scope)

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

    def active_model_path(self, scope: str) -> Path:
        return self.root_path(scope) / "active_model.json"

    def provider_paths(self, scope: str, *, is_builtin: bool) -> list[Path]:
        provider_dir = (
            self.builtin_path(scope) if is_builtin else self.custom_path(scope)
        )
        return (
            sorted(provider_dir.glob("*.json"))
            if provider_dir.exists()
            else []
        )

    def custom_provider_paths(self, scope: str) -> list[Path]:
        return self.provider_paths(scope, is_builtin=False)

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
        self._write_json_atomic(provider_path, payload)
        return provider_path

    def read_provider(
        self,
        scope: str,
        provider_id: str,
        *,
        is_builtin: bool,
    ) -> dict[str, Any] | None:
        return self._read_json(
            self.provider_path(scope, provider_id, is_builtin=is_builtin),
        )

    def delete_provider(
        self,
        scope: str,
        provider_id: str,
        *,
        is_builtin: bool,
    ) -> None:
        provider_path = self.provider_path(
            scope,
            provider_id,
            is_builtin=is_builtin,
        )
        try:
            provider_path.unlink()
        except FileNotFoundError:
            pass

    def discard_provider_freshness_token(
        self,
        scope: str,
        provider_id: str,
        *,
        is_builtin: bool,
    ) -> None:
        """Forget one deleted provider from a collected scope snapshot."""
        provider_path = self.provider_path(
            scope,
            provider_id,
            is_builtin=is_builtin,
        )
        self._freshness_tokens.get(scope, {}).pop(str(provider_path), None)

    def write_active_model(
        self,
        scope: str,
        active_model: ModelSlotConfig,
    ) -> Path:
        self.prepare_scope(scope)
        active_path = self.active_model_path(scope)
        self._write_json_atomic(active_path, active_model.model_dump())
        return active_path

    def read_active_model(self, scope: str) -> ModelSlotConfig | None:
        data = self._read_json(self.active_model_path(scope))
        if data is None:
            return None
        try:
            return ModelSlotConfig.model_validate(data)
        except ValueError:
            return None

    def freshness_token(self, scope: str) -> tuple[tuple[str, int, int], ...]:
        root = self.root_path(scope)
        if not root.exists():
            return ()
        try:
            return tuple(
                sorted(
                    (str(path.relative_to(root)), *self.file_token(path))
                    for path in root.rglob("*.json")
                ),
            )
        except OSError:
            return ()

    def freshness_snapshot(
        self,
        scope: str,
        builtin_provider_ids: list[str] | tuple[str, ...],
    ) -> dict[str, tuple[int, int]]:
        return self.collect_freshness_tokens(scope, builtin_provider_ids)

    def collect_freshness_tokens(
        self,
        scope: str,
        builtin_provider_ids: list[str] | tuple[str, ...],
    ) -> dict[str, tuple[int, int]]:
        """Collect and retain the provider-file tokens for one scope."""
        paths = [
            self.provider_path(scope, provider_id, is_builtin=True)
            for provider_id in builtin_provider_ids
        ]
        paths.extend(self.custom_provider_paths(scope))
        paths.append(self.active_model_path(scope))
        snapshot: dict[str, tuple[int, int]] = {}
        for path in paths:
            try:
                if path.exists():
                    snapshot[str(path)] = self.file_token(path)
            except OSError:
                continue
        self._freshness_tokens[scope] = snapshot
        return snapshot

    @staticmethod
    def file_token(path: Path) -> tuple[int, int]:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    @staticmethod
    def file_has_changed(
        path: Path,
        snapshot: dict[str, tuple[int, int]],
    ) -> bool:
        try:
            if path.exists():
                return snapshot.get(
                    str(path),
                ) != TenantProviderRepository.file_token(
                    path,
                )
            return str(path) in snapshot
        except OSError:
            return False

    def _ensure_scope(self, scope: str, root: Path) -> None:
        root.parent.mkdir(parents=True, exist_ok=True)
        lock_path = root.parent / ".provider_init.lock"
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            self._acquire_lock(lock_file, scope)
            try:
                if root.exists():
                    return
                temporary_root = root.parent / (
                    f".{root.name}.{uuid.uuid4().hex}.tmp"
                )
                try:
                    self._seed_scope(scope, temporary_root)
                    for path in (
                        temporary_root,
                        temporary_root / "builtin",
                        temporary_root / "custom",
                    ):
                        path.mkdir(parents=True, exist_ok=True)
                        self._restrict_directory_permissions(path)
                    os.replace(temporary_root, root)
                except BaseException:
                    shutil.rmtree(temporary_root, ignore_errors=True)
                    raise
            finally:
                self._release_lock(lock_file)

    def _seed_scope(self, scope: str, root: Path) -> None:
        template = self._template_path(scope)
        if template is not None:
            shutil.copytree(template, root)
        else:
            root.mkdir(parents=True, exist_ok=True)

    def _template_path(self, scope: str) -> Path | None:
        from swe.config.context import get_current_source_id

        source_id = get_current_source_id()
        if source_id:
            source_template_scope = f"default_{source_id}"
            source_template = self.root_path(source_template_scope)
            default_template = self.root_path("default")
            if not source_template.exists() and default_template.exists():
                self._publish_source_template(
                    source_template_scope,
                    default_template,
                    source_template,
                )
            if source_template.exists() and any(source_template.iterdir()):
                return source_template
        default_template = self.root_path("default")
        if (
            scope != "default"
            and default_template.exists()
            and any(default_template.iterdir())
        ):
            return default_template
        return None

    def _publish_source_template(
        self,
        source_template_scope: str,
        default_template: Path,
        source_template: Path,
    ) -> None:
        source_template.parent.mkdir(parents=True, exist_ok=True)
        lock_path = source_template.parent / ".provider_source_template.lock"
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            self._acquire_lock(lock_file, source_template_scope)
            try:
                if source_template.exists():
                    return
                temporary_template = source_template.parent / (
                    f".{source_template.name}.{uuid.uuid4().hex}.tmp"
                )
                try:
                    shutil.copytree(default_template, temporary_template)
                    os.replace(temporary_template, source_template)
                except BaseException:
                    shutil.rmtree(temporary_template, ignore_errors=True)
                    raise
            finally:
                self._release_lock(lock_file)

    def _acquire_lock(self, lock_file: Any, scope: str) -> None:
        deadline = time.monotonic() + 30.0
        while True:
            try:
                if fcntl is not None:
                    fcntl.flock(
                        lock_file.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                elif msvcrt is not None:  # pragma: no cover (Windows)
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"Timeout waiting for provider initialization lock for tenant {scope}",
                    ) from exc
                time.sleep(0.05)

    @staticmethod
    def _release_lock(lock_file: Any) -> None:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        elif msvcrt is not None:  # pragma: no cover (Windows)
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode(
            "utf-8",
        )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(encoded)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            self._restrict_file_permissions(temporary_path)
            os.replace(temporary_path, path)
            self._restrict_file_permissions(path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _restrict_file_permissions(path: Path) -> None:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    @staticmethod
    def _restrict_directory_permissions(path: Path) -> None:
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass

    class Paths:
        def __init__(self, *, root: Path, builtin: Path, custom: Path) -> None:
            self.root = root
            self.builtin = builtin
            self.custom = custom
