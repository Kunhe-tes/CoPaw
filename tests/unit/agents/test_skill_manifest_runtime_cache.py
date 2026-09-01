# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path


def _write_workspace(workspace: Path, *, description: str = "cached") -> None:
    skill_dir = workspace / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: demo\ndescription: {description}\n---\nbody\n",
        encoding="utf-8",
    )
    (workspace / "skill.json").write_text(
        json.dumps(
            {
                "layout_version": 2,
                "skills": {"demo": {"enabled": True, "channels": ["all"]}},
            },
        ),
        encoding="utf-8",
    )


def test_resolve_effective_skills_reuses_unchanged_workspace_snapshot(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.agents import skills_manager

    _write_workspace(tmp_path)
    original = skills_manager.reconcile_workspace_manifest
    calls = 0

    def counted(workspace: Path):
        nonlocal calls
        calls += 1
        return original(workspace)

    monkeypatch.setattr(
        skills_manager,
        "reconcile_workspace_manifest",
        counted,
    )

    assert skills_manager.resolve_effective_skills(tmp_path, "console") == [
        "demo",
    ]
    assert skills_manager.resolve_effective_skills(tmp_path, "console") == [
        "demo",
    ]
    assert calls == 1


def test_snapshot_reuses_manifest_metadata_and_detects_skill_content_change(
    tmp_path: Path,
) -> None:
    from swe.agents import skills_manager
    from swe.agents.skill_runtime_snapshot import get_workspace_skill_snapshot

    _write_workspace(tmp_path, description="before")
    first = get_workspace_skill_snapshot(tmp_path)
    assert first.skills["demo"].metadata["description"] == "before"
    assert first.skills["demo"].content_signature

    (tmp_path / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: after\n---\nbody\n",
        encoding="utf-8",
    )
    second = get_workspace_skill_snapshot(tmp_path)
    assert second is not first
    assert (
        second.skills["demo"].content_signature
        != first.skills["demo"].content_signature
    )
    assert skills_manager.resolve_effective_skills(
        tmp_path,
        "console",
        _snapshot=second,
    ) == ["demo"]
