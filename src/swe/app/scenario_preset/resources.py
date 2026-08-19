# -*- coding: utf-8 -*-
"""Session-scoped marketplace resource helpers.

Only resource identities and safe, non-secret MCP configuration may cross the
marketplace boundary.  Credentials remain tenant-owned environment
references and are resolved by the normal runtime configuration path.
"""

from __future__ import annotations

import re
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
