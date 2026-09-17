# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from swe.security.tool_guard.guardians.file_guardian import (
    FilePathToolGuardian,
)


def test_file_guardian_extracts_background_shell_command_paths(
    tmp_path: Path,
) -> None:
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("secret")
    secret_path = secret_file.as_posix()
    guardian = FilePathToolGuardian(sensitive_files=[secret_path])

    shell_findings = guardian.guard(
        "execute_shell_command",
        {"command": f"cat {secret_path}"},
    )
    background_findings = guardian.guard(
        "start_background_process",
        {"command": f"cat {secret_path}"},
    )

    assert [finding.rule_id for finding in shell_findings] == [
        "SENSITIVE_FILE_BLOCK",
    ]
    assert [finding.rule_id for finding in background_findings] == [
        "SENSITIVE_FILE_BLOCK",
    ]
