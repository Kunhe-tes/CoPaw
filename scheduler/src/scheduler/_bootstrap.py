# -*- coding: utf-8 -*-
"""Bootstrap repo-local package imports for Scheduler."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_packages() -> None:
    """Expose the repo-local Scheduler package when run from this checkout."""
    scheduler_src = Path(__file__).resolve().parents[1]
    scheduler_src_text = str(scheduler_src)
    if scheduler_src.exists() and scheduler_src_text not in sys.path:
        sys.path.insert(0, scheduler_src_text)


ensure_repo_packages()
