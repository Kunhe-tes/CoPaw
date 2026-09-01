# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import threading
import time
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


def test_workspace_skill_coordinator_serializes_local_mutations(
    tmp_path: Path,
) -> None:
    from swe.agents.skill_runtime_snapshot import workspace_skill_coordinator

    entered: list[str] = []
    first_inside = threading.Event()
    release_first = threading.Event()

    def first() -> None:
        with workspace_skill_coordinator(tmp_path):
            entered.append("first")
            first_inside.set()
            release_first.wait(timeout=2)
            entered.append("first-done")

    def second() -> None:
        first_inside.wait(timeout=2)
        with workspace_skill_coordinator(tmp_path):
            entered.append("second")

    first_thread = threading.Thread(target=first)
    second_thread = threading.Thread(target=second)
    first_thread.start()
    second_thread.start()
    assert first_inside.wait(timeout=2)
    time.sleep(0.02)
    assert entered == ["first"]
    release_first.set()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)
    assert entered == ["first", "first-done", "second"]


def test_snapshot_build_failure_keeps_previous_cached_snapshot(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.agents import skills_manager
    from swe.agents import skill_runtime_snapshot as snapshots

    _write_workspace(tmp_path)
    first = snapshots.get_workspace_skill_snapshot(tmp_path)
    manifest_path = tmp_path / "skill.json"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    def fail_read(*_args, **_kwargs):
        raise RuntimeError("reconcile unavailable")

    monkeypatch.setattr(skills_manager, "read_skill_manifest", fail_read)
    try:
        snapshots.get_workspace_skill_snapshot(tmp_path)
    except RuntimeError as exc:
        assert str(exc) == "reconcile unavailable"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("snapshot build unexpectedly succeeded")

    assert snapshots._CACHE[tmp_path.resolve()] is first


def test_snapshot_validation_refreshes_stat_token_without_rehashing_forever(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.agents import skills_manager
    from swe.agents import skill_runtime_snapshot as snapshots

    _write_workspace(tmp_path)
    first = snapshots.get_workspace_skill_snapshot(tmp_path)
    skill_md = tmp_path / "skills" / "demo" / "SKILL.md"
    stat = skill_md.stat()
    os.utime(
        skill_md,
        ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000),
    )

    validated = snapshots._filter_changed_skills(first)
    assert (
        validated.skills["demo"].freshness_token
        != first.skills["demo"].freshness_token
    )

    monkeypatch.setattr(
        skills_manager,
        "_build_signature",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unchanged content should not be rehashed"),
        ),
    )
    assert snapshots._filter_changed_skills(validated) is validated
