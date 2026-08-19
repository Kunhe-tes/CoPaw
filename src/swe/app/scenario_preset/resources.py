# -*- coding: utf-8 -*-
"""Session-scoped marketplace resource helpers.

Only resource identities and safe, non-secret MCP configuration may cross the
marketplace boundary.  Credentials remain tenant-owned environment
references and are resolved by the normal runtime configuration path.
"""

from __future__ import annotations

import re
import json
import shutil
from pathlib import Path
from typing import Any

_ENV_REFERENCE = re.compile(r"^\$\{ENV:[A-Za-z_][A-Za-z0-9_]*\}$")
_MASKED_SECRET_MARKERS = {"*", "***", "****", "[REDACTED]", "<masked>"}


def sanitize_mcp_config(raw: Any) -> dict[str, Any]:
    """Return a validated MCP config without accepting marketplace secrets.

    Marketplace detail responses mask literal headers/env values.  Treat all
    non-empty values in those maps as unsafe unless they are explicit tenant
    environment references (``${ENV:NAME}``).
    """
    if not isinstance(raw, dict):
        raise ValueError("MCP config must be an object")

    transport = str(raw.get("transport") or "stdio").strip().lower()
    if transport not in {"stdio", "streamable_http", "sse"}:
        raise ValueError("unsupported MCP transport")

    headers = _sanitize_secret_map(raw.get("headers"), "header")
    env = _sanitize_secret_map(raw.get("env"), "env")
    config = {
        "transport": transport,
        "url": str(raw.get("url") or ""),
        "headers": headers,
        "command": str(raw.get("command") or ""),
        "args": [str(value) for value in raw.get("args", []) or []],
        "env": env,
        "cwd": str(raw.get("cwd") or ""),
        "lazy_load": bool(raw.get("lazy_load", False)),
    }
    if transport == "stdio" and not config["command"].strip():
        raise ValueError("stdio MCP config requires command")
    if transport != "stdio" and not config["url"].strip():
        raise ValueError("HTTP MCP config requires url")
    return config


def stage_temporary_skill_zip(
    payload: bytes,
    *,
    resource_id: str,
    session_root: Path,
) -> tuple[str, Path]:
    """Scan and place one market Skill below a single Chat's private root."""
    from ...agents.skills_manager import (  # pylint: disable=import-outside-toplevel
        _extract_zip_skills,
        _scan_skill_dir_or_raise,
    )

    safe_resource_id = _safe_resource_id(resource_id)
    root = session_root.resolve()
    target_root = (root / safe_resource_id).resolve()
    target_root.relative_to(root)
    temporary_root, found = _extract_zip_skills(payload)
    try:
        if len(found) != 1:
            raise ValueError("market Skill archive must contain exactly one Skill")
        source_dir, skill_name = found[0]
        _scan_skill_dir_or_raise(source_dir, skill_name)
        target_dir = (target_root / skill_name).resolve()
        target_dir.relative_to(target_root)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, target_dir)
        return skill_name, target_dir / "SKILL.md"
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def stage_temporary_mcp_config(
    config: dict[str, Any],
    *,
    resource_id: str,
    session_root: Path,
) -> Path:
    """Persist safe MCP config only in the Chat-private resource directory."""
    root = session_root.resolve()
    target_root = (root / _safe_resource_id(resource_id)).resolve()
    target_root.relative_to(root)
    target_root.mkdir(parents=True, exist_ok=True)
    path = target_root / "mcp.json"
    path.write_text(
        json.dumps(config, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _sanitize_secret_map(raw: Any, label: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"MCP {label} map must be an object")
    result: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key).strip()
        text = str(value or "").strip()
        if not name:
            raise ValueError(f"MCP {label} name must not be empty")
        if not text:
            result[name] = ""
            continue
        if text in _MASKED_SECRET_MARKERS or not _ENV_REFERENCE.fullmatch(text):
            raise ValueError(f"MCP {label} contains unsafe secret material")
        result[name] = text
    return result


def _safe_resource_id(resource_id: str) -> str:
    normalized = str(resource_id or "").strip()
    if not normalized or normalized in {".", ".."}:
        raise ValueError("invalid market resource ID")
    if "/" in normalized or "\\" in normalized or "\x00" in normalized:
        raise ValueError("invalid market resource ID")
    return normalized
