# -*- coding: utf-8 -*-
"""Explicit provisioning for source-scoped tenant templates."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import shutil
import tempfile
from time import perf_counter
from typing import Literal
from uuid import uuid4

from ...config.context import is_valid_identity_value
from ...constant import SECRET_DIR
from .bootstrap_lock import (
    AsyncFlock,
    BootstrapLockFailure,
    BootstrapLockTimeout,
)
from .bootstrap_state import (
    BootstrapReadiness,
    SourceTemplateUnavailable,
    inspect_bootstrap_readiness,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceTemplateProvisionResult:
    """Result of an idempotent source-template ensure operation."""

    source_id: str
    template_name: str
    status: Literal["created", "repaired", "ready"]


def inspect_source_template_readiness(
    base_working_dir: Path,
    source_id: str,
) -> BootstrapReadiness:
    """Return strict readiness for source template files and providers."""
    template_name = f"default_{source_id}"
    template_dir = Path(base_working_dir) / template_name
    readiness = inspect_bootstrap_readiness(template_dir)
    providers_dir = SECRET_DIR / template_name / "providers"
    if readiness.ready and providers_dir.is_dir():
        return readiness
    missing_paths = readiness.missing_paths
    if not providers_dir.is_dir():
        missing_paths = (*missing_paths, providers_dir)
    return BootstrapReadiness(
        ready=False,
        missing_paths=missing_paths,
        invalid_json_paths=readiness.invalid_json_paths,
        reason=(
            readiness.reason if not readiness.ready else "missing_providers"
        ),
    )


class SourceTemplateProvisioner:
    """Create or repair source templates outside normal tenant traffic."""

    def __init__(self, base_working_dir: Path) -> None:
        self._base_working_dir = Path(base_working_dir).expanduser().resolve()

    async def ensure(self, source_id: str) -> SourceTemplateProvisionResult:
        """Return a ready source template without overwriting a ready one."""
        if not is_valid_identity_value(source_id):
            raise SourceTemplateUnavailable(
                "invalid source template identifier",
            )

        source_id = str(source_id)
        template_name = f"default_{source_id}"
        started_at = perf_counter()
        logger.info(
            "source_template_provisioning_started source_id=%s",
            source_id,
        )
        lock_path = (
            self._base_working_dir
            / ".source-template-locks"
            / f"{source_id}.lock"
        )
        try:
            async with AsyncFlock(lock_path):
                current = inspect_source_template_readiness(
                    self._base_working_dir,
                    source_id,
                )
                if current.ready:
                    logger.info(
                        "source_template_provisioning_ready source_id=%s duration_ms=%d",
                        source_id,
                        int((perf_counter() - started_at) * 1000),
                    )
                    return SourceTemplateProvisionResult(
                        source_id=source_id,
                        template_name=template_name,
                        status="ready",
                    )

                default_readiness = inspect_bootstrap_readiness(
                    self._base_working_dir / "default",
                )
                default_providers = SECRET_DIR / "default" / "providers"
                if (
                    not default_readiness.ready
                    or not default_providers.is_dir()
                ):
                    raise SourceTemplateUnavailable(
                        "global default source template is unavailable",
                    )

                existed = (self._base_working_dir / template_name).exists()
                await asyncio.to_thread(self._publish, template_name)
                final = inspect_source_template_readiness(
                    self._base_working_dir,
                    source_id,
                )
                if not final.ready:
                    raise SourceTemplateUnavailable(
                        "source template failed strict readiness validation",
                    )
                status: Literal["created", "repaired"] = (
                    "repaired" if existed else "created"
                )
                event_name = (
                    "source_template_provisioning_repaired"
                    if status == "repaired"
                    else "source_template_provisioning_ready"
                )
                logger.info(
                    "%s source_id=%s outcome=%s duration_ms=%d",
                    event_name,
                    source_id,
                    status,
                    int((perf_counter() - started_at) * 1000),
                )
                return SourceTemplateProvisionResult(
                    source_id=source_id,
                    template_name=template_name,
                    status=status,
                )
        except (BootstrapLockTimeout, BootstrapLockFailure) as exc:
            logger.error(
                "source_template_provisioning_failed source_id=%s error=%s",
                source_id,
                type(exc).__name__,
            )
            raise SourceTemplateUnavailable(
                "source template lock unavailable",
            ) from exc
        except Exception as exc:
            logger.error(
                "source_template_provisioning_failed source_id=%s error=%s",
                source_id,
                type(exc).__name__,
            )
            if isinstance(exc, SourceTemplateUnavailable):
                raise
            raise SourceTemplateUnavailable(
                "source template provisioning failed",
            ) from exc

    def _publish(self, template_name: str) -> None:
        target_dir = self._base_working_dir / template_name
        target_secret_dir = SECRET_DIR / template_name
        staged_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{template_name}.",
                suffix=".tmp",
                dir=self._base_working_dir,
            ),
        )
        secret_parent = SECRET_DIR
        secret_parent.mkdir(parents=True, exist_ok=True)
        staged_secret_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{template_name}.",
                suffix=".tmp",
                dir=secret_parent,
            ),
        )
        template_backup: Path | None = None
        secret_backup: Path | None = None
        published_template = False
        published_secret = False
        try:
            shutil.copytree(
                self._base_working_dir / "default",
                staged_dir,
                dirs_exist_ok=True,
            )
            shutil.copytree(
                SECRET_DIR / "default",
                staged_secret_dir,
                dirs_exist_ok=True,
            )
            self._rewrite_workspace_paths(staged_dir, target_dir)
            staged_readiness = inspect_bootstrap_readiness(
                staged_dir,
                expected_tenant_dir=target_dir,
            )
            if not staged_readiness.ready:
                raise SourceTemplateUnavailable(
                    "staged source template is invalid",
                )

            if target_dir.exists():
                template_backup = target_dir.with_name(
                    f"{target_dir.name}.{uuid4().hex}.bak",
                )
                target_dir.replace(template_backup)
            if target_secret_dir.exists():
                secret_backup = target_secret_dir.with_name(
                    f"{target_secret_dir.name}.{uuid4().hex}.bak",
                )
                target_secret_dir.replace(secret_backup)

            staged_dir.replace(target_dir)
            published_template = True
            staged_secret_dir.replace(target_secret_dir)
            published_secret = True
            if template_backup is not None:
                shutil.rmtree(template_backup)
            if secret_backup is not None:
                shutil.rmtree(secret_backup)
        except Exception:
            if published_secret and target_secret_dir.exists():
                shutil.rmtree(target_secret_dir)
            if published_template and target_dir.exists():
                shutil.rmtree(target_dir)
            if secret_backup is not None and secret_backup.exists():
                secret_backup.replace(target_secret_dir)
            if template_backup is not None and template_backup.exists():
                template_backup.replace(target_dir)
            raise
        finally:
            if staged_dir.exists():
                shutil.rmtree(staged_dir)
            if staged_secret_dir.exists():
                shutil.rmtree(staged_secret_dir)

    @staticmethod
    def _rewrite_workspace_paths(staged_dir: Path, target_dir: Path) -> None:
        source_prefix = str(staged_dir.parent / "default" / "workspaces")
        copied_prefix = str(target_dir / "workspaces")
        for path in (
            staged_dir / "config.json",
            staged_dir / "workspaces" / "default" / "agent.json",
        ):
            payload = json.loads(path.read_text(encoding="utf-8"))
            SourceTemplateProvisioner._replace_workspace_paths(
                payload,
                source_prefix,
                copied_prefix,
            )
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    @staticmethod
    def _replace_workspace_paths(
        value: object,
        source_prefix: str,
        target_prefix: str,
    ) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == "workspace_dir" and isinstance(nested, str):
                    if nested.startswith(source_prefix):
                        value[key] = nested.replace(
                            source_prefix,
                            target_prefix,
                            1,
                        )
                else:
                    SourceTemplateProvisioner._replace_workspace_paths(
                        nested,
                        source_prefix,
                        target_prefix,
                    )
        elif isinstance(value, list):
            for nested in value:
                SourceTemplateProvisioner._replace_workspace_paths(
                    nested,
                    source_prefix,
                    target_prefix,
                )
