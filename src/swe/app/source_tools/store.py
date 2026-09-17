# -*- coding: utf-8 -*-
"""Durable source-tool catalogue storage, kept outside tenant workspaces."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any


class SourceToolStore:
    """Persist the source-wide catalogue in a controlled application library."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = Path(root_dir)
        self._state_path = self._root_dir / "catalogue.json"

    def load(self) -> dict[str, Any]:
        """Load the complete catalogue state, creating no implicit records."""
        if not self._state_path.exists():
            return {"sources": {}}
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("source tool catalogue is unavailable") from exc
        if not isinstance(raw, dict) or not isinstance(
            raw.get("sources", {}),
            dict,
        ):
            raise RuntimeError("source tool catalogue is invalid")
        return raw

    def save(self, state: dict[str, Any]) -> None:
        """Atomically write a complete catalogue update."""
        self._root_dir.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(
            state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        with tempfile.NamedTemporaryFile(
            dir=self._root_dir,
            delete=False,
        ) as staged:
            staged.write(encoded)
            staged_path = Path(staged.name)
        os.chmod(staged_path, 0o600)
        staged_path.replace(self._state_path)
