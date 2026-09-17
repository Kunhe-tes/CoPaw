# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from swe.agents.workspace_skill_layout_migration import (
    SkillLayoutMigrationError,
    SkillLayoutMigrationReport,
    WorkspaceMigrationResult,
)
from swe.cli.skills_cmd import skills_group


def _report(
    *items: tuple[Path, str],
) -> SkillLayoutMigrationReport:
    return SkillLayoutMigrationReport(
        success=True,
        workspaces=tuple(
            WorkspaceMigrationResult(workspace, status)
            for workspace, status in items
        ),
    )


def test_migrate_layout_requires_exactly_one_mode(tmp_path: Path) -> None:
    runner = CliRunner()

    missing = runner.invoke(
        skills_group,
        ["migrate-layout", "--working-dir", str(tmp_path)],
    )
    both = runner.invoke(
        skills_group,
        [
            "migrate-layout",
            "--check",
            "--apply",
            "--working-dir",
            str(tmp_path),
        ],
    )

    assert missing.exit_code != 0
    assert both.exit_code != 0
    message = "choose exactly one of --check or --apply"
    assert message in missing.output
    assert message in both.output


def test_migrate_layout_check_dispatches_read_only_engine(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    report = _report((workspace, "ready"))

    with (
        patch(
            "swe.cli.skills_cmd.check_workspace_skill_layout_migration",
            return_value=report,
        ) as check,
        patch(
            "swe.cli.skills_cmd.apply_workspace_skill_layout_migration",
        ) as apply,
    ):
        result = CliRunner().invoke(
            skills_group,
            ["migrate-layout", "--check", "--working-dir", str(tmp_path)],
        )

    assert result.exit_code == 0
    check.assert_called_once_with(tmp_path)
    apply.assert_not_called()
    assert f"{workspace}: ready" in result.output


def test_migrate_layout_apply_dispatches_write_engine(tmp_path: Path) -> None:
    workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    report = _report((workspace, "migrated"))

    with (
        patch(
            "swe.cli.skills_cmd.check_workspace_skill_layout_migration",
        ) as check,
        patch(
            "swe.cli.skills_cmd.apply_workspace_skill_layout_migration",
            return_value=report,
        ) as apply,
    ):
        result = CliRunner().invoke(
            skills_group,
            ["migrate-layout", "--apply", "--working-dir", str(tmp_path)],
        )

    assert result.exit_code == 0
    check.assert_not_called()
    apply.assert_called_once_with(tmp_path)
    assert f"{workspace}: migrated" in result.output


def test_migrate_layout_reports_engine_error(tmp_path: Path) -> None:
    with patch(
        "swe.cli.skills_cmd.check_workspace_skill_layout_migration",
        side_effect=SkillLayoutMigrationError("mixed layout"),
    ):
        result = CliRunner().invoke(
            skills_group,
            ["migrate-layout", "--check", "--working-dir", str(tmp_path)],
        )

    assert result.exit_code != 0
    assert "mixed layout" in result.output


def test_migrate_layout_prints_every_workspace_status(tmp_path: Path) -> None:
    migrated = tmp_path / "tenant-a" / "workspaces" / "default"
    unrelated = tmp_path / "tenant-b" / "workspaces" / "empty"
    report = _report(
        (migrated, "already_migrated"),
        (unrelated, "not_applicable"),
    )

    with patch(
        "swe.cli.skills_cmd.check_workspace_skill_layout_migration",
        return_value=report,
    ):
        result = CliRunner().invoke(
            skills_group,
            ["migrate-layout", "--check", "--working-dir", str(tmp_path)],
        )

    assert result.exit_code == 0
    assert result.output.splitlines() == [
        f"{migrated}: already_migrated",
        f"{unrelated}: not_applicable",
    ]


def test_migrate_layout_empty_report_has_no_item_output(
    tmp_path: Path,
) -> None:
    with patch(
        "swe.cli.skills_cmd.check_workspace_skill_layout_migration",
        return_value=_report(),
    ):
        result = CliRunner().invoke(
            skills_group,
            ["migrate-layout", "--check", "--working-dir", str(tmp_path)],
        )

    assert result.exit_code == 0
    assert result.output == ""


def test_migrate_layout_rejects_file_working_dir(tmp_path: Path) -> None:
    working_file = tmp_path / "not-a-directory"
    working_file.write_text("file", encoding="utf-8")

    with patch(
        "swe.cli.skills_cmd.check_workspace_skill_layout_migration",
    ) as check:
        result = CliRunner().invoke(
            skills_group,
            [
                "migrate-layout",
                "--check",
                "--working-dir",
                str(working_file),
            ],
        )

    assert result.exit_code != 0
    check.assert_not_called()
    assert "directory" in result.output.lower()
