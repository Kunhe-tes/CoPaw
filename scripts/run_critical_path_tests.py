#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run critical runtime path tests phase-by-phase and fail fast."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PHASES = [
    (
        "scheduled-run-boundary",
        "tests/integrated/critical_paths/test_scheduled_run_boundary.py",
    ),
    (
        "mcp-runtime-path",
        "tests/integrated/critical_paths/test_mcp_runtime_path.py",
    ),
    (
        "model-invocation-path",
        "tests/integrated/critical_paths/test_model_invocation_path.py",
    ),
    (
        "scheduled-agent-mcp-react-path",
        (
            "tests/integrated/critical_paths/"
            "test_scheduled_agent_mcp_react_path.py"
        ),
    ),
]


def _python_executable(repo_root: Path) -> str:
    venv_python = repo_root / "venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    python = _python_executable(repo_root)

    for name, test_path in PHASES:
        print(f"== critical path phase: {name} ==", flush=True)
        completed = subprocess.run(
            [
                python,
                "-m",
                "pytest",
                test_path,
                "-x",
                "-v",
            ],
            cwd=repo_root,
            check=False,
        )
        if completed.returncode != 0:
            print(
                f"critical path phase failed: {name}",
                file=sys.stderr,
                flush=True,
            )
            return completed.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
