# -*- coding: utf-8 -*-
"""Reading and writing environment variables.

Persistence strategy (two layers):

1. **envs.json** – canonical store, survives process restarts.
2. **os.environ** – injected into the current Python process so that
   ``os.getenv()`` and child subprocesses (``subprocess.run``, etc.)
   can read them immediately.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_BOOTSTRAP_WORKING_DIR = (
    Path(os.environ.get("SWE_WORKING_DIR", "~/.swe")).expanduser().resolve()
)
_BOOTSTRAP_SECRET_DIR = (
    Path(
        os.environ.get(
            "SWE_SECRET_DIR",
            f"{_BOOTSTRAP_WORKING_DIR}.secret",
        ),
    )
    .expanduser()
    .resolve()
)

_ENVS_JSON = _BOOTSTRAP_SECRET_DIR / "envs.json"
_LEGACY_ENVS_JSON_CANDIDATES = (
    Path(__file__).resolve().parent / "envs.json",
    _BOOTSTRAP_WORKING_DIR / "envs.json",
)


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        # Some systems/filesystems may not support chmod semantics.
        pass


def _prepare_secret_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _chmod_best_effort(path.parent, 0o700)


def _migrate_legacy_envs_json(path: Path) -> None:
    """Copy old envs.json into secret dir once (best effort)."""
    if path.is_file():
        return
    if path.exists() and not path.is_file():
        logger.error(
            "envs.json path exists but is not a regular file: %s",
            path,
        )
        return

    for legacy in _LEGACY_ENVS_JSON_CANDIDATES:
        if not legacy.is_file() or _same_path(legacy, path):
            continue
        try:
            _prepare_secret_parent(path)
            shutil.copy2(legacy, path)
            _chmod_best_effort(path, 0o600)
            return
        except OSError as exc:
            logger.warning(
                "Failed to migrate legacy envs.json from %s: %s",
                legacy,
                exc,
            )
            continue


# Security-sensitive envs should come from process/system environment,
# not persisted envs.json.
_PROTECTED_BOOTSTRAP_KEYS = frozenset(
    {
        "SWE_WORKING_DIR",
        "SWE_SECRET_DIR",
    },
)


def get_envs_json_path() -> Path:
    """Return envs.json path under SECRET_DIR."""
    return _ENVS_JSON


# ------------------------------------------------------------------
# os.environ helpers
# ------------------------------------------------------------------


def _apply_to_environ(
    envs: dict[str, str],
    *,
    overwrite: bool = True,
) -> None:
    """Set key/value pairs into ``os.environ``.

    Args:
        envs: Key-value mapping to inject.
        overwrite: When False, existing process env values take precedence.
    """
    for key, value in envs.items():
        if not overwrite and key in os.environ:
            continue
        os.environ[key] = value


def _remove_from_environ(key: str) -> None:
    """Remove *key* from ``os.environ`` if present."""
    os.environ.pop(key, None)


def _sync_environ(
    old: dict[str, str],
    new: dict[str, str],
) -> None:
    """Synchronise ``os.environ``: set *new*, remove stale *old*."""
    for key, old_value in old.items():
        if key not in new and os.environ.get(key) == old_value:
            _remove_from_environ(key)
    _apply_to_environ(new, overwrite=True)


# ------------------------------------------------------------------
# JSON persistence
# ------------------------------------------------------------------


def load_envs(
    path: Optional[Path] = None,
) -> dict[str, str]:
    """Load env vars from envs.json."""
    if path is None:
        path = get_envs_json_path()
        _migrate_legacy_envs_json(path)
    if path.exists() and not path.is_file():
        logger.error(
            "envs.json path exists but is not a regular file: %s",
            path,
        )
        return {}
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return {k: str(v) for k, v in data.items()}
    except (json.JSONDecodeError, ValueError):
        pass
    except OSError as exc:
        logger.warning(
            "Failed to read envs.json from %s due to OS error: %s",
            path,
            exc,
        )
    return {}


def save_envs(
    envs: dict[str, str],
    path: Optional[Path] = None,
) -> None:
    """Write env vars to envs.json and sync to ``os.environ``."""
    sync_process_env = path is None
    if path is None:
        path = get_envs_json_path()
        _migrate_legacy_envs_json(path)
    old = load_envs(path)
    if path.exists() and not path.is_file():
        raise IsADirectoryError(
            f"envs.json path exists but is not a regular file: {path}",
        )
    _prepare_secret_parent(path)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            tmp_path = Path(fh.name)
            json.dump(envs, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        _chmod_best_effort(tmp_path, 0o600)
        os.replace(tmp_path, path)
        _chmod_best_effort(path, 0o600)
    except Exception:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise

    if sync_process_env:
        _sync_environ(old, envs)


def set_env_var(
    key: str,
    value: str,
    path: Optional[Path] = None,
) -> dict[str, str]:
    """Set a single env var. Returns updated dict."""
    envs = load_envs(path)
    envs[key] = value
    save_envs(envs, path)
    return envs


def delete_env_var(
    key: str,
    path: Optional[Path] = None,
) -> dict[str, str]:
    """Delete a single env var. Returns updated dict."""
    envs = load_envs(path)
    envs.pop(key, None)
    save_envs(envs, path)
    return envs


def load_envs_into_environ() -> dict[str, str]:
    """Load envs.json and apply bootstrap-safe entries to ``os.environ``.

    Call this once at application startup so that environment
    variables persisted from a previous session are available
    immediately. Protected keys are excluded from injection, and
    existing process/system env vars are preserved.

    Returns:
        Full persisted mapping from envs.json, including protected keys
        that are intentionally not injected into ``os.environ``.
    """
    envs = load_envs()
    bootstrap_envs = {
        key: value
        for key, value in envs.items()
        if key not in _PROTECTED_BOOTSTRAP_KEYS
    }
    from swe.env_defaults import get_applied_env_defaults

    applied_defaults = get_applied_env_defaults()
    for key, value in bootstrap_envs.items():
        if key not in os.environ or os.environ.get(
            key,
        ) == applied_defaults.get(
            key,
        ):
            os.environ[key] = value
    return envs
