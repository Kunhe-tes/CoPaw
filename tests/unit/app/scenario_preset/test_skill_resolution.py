# -*- coding: utf-8 -*-
"""Trusted resolution of scenario market IDs to already-enabled skills."""

from pathlib import Path

from swe.app.runner.skill_selection import resolve_scenario_skill_names


def test_resolve_scenario_skill_names_matches_enabled_skill_id(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skills" / "summarize"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nskill_id: market-summarize\ndescription: Summarize\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "skill.json").write_text(
        '{"layout_version": 2, "skills": {"summarize": {"enabled": true, "channels": ["console"]}}}',
        encoding="utf-8",
    )

    assert resolve_scenario_skill_names(
        workspace_dir=tmp_path,
        channel="console",
        resource_ids=["market-summarize"],
    ) == ["summarize"]
