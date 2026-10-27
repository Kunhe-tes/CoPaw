# -*- coding: utf-8 -*-
"""Expert main messages capture the current received dependency version."""

from concurrent.futures import ThreadPoolExecutor
import json
import shutil
import threading
from uuid import uuid4

import pytest

from swe.app.subagents import session_dependencies as dependencies
from swe.app.subagents.agent_definitions import AgentOwnedDefinitionRepository

CHAT_ID = "00000000-0000-0000-0000-000000000301"


def _install(workspace, *, version="1", definition_id=None):
    repository = AgentOwnedDefinitionRepository(
        workspace / "agents",
        owner_scope="agent:tenant:profile",
    )
    payload = {
        "name": "reviewer",
        "description": "Review",
        "instruction": f"role {version}",
        "skills": [f"skill-{version}"],
        "mcps": [f"mcp-{version}"],
        "community": {
            "item_id": "received",
            "version": version,
            "content_fingerprint": f"fingerprint-{version}",
        },
    }
    if definition_id is None:
        package = repository.create(payload)
        definition_id = package.definition_id
    root = workspace / "agents" / f"{definition_id}.dependencies"
    if root.exists():
        shutil.rmtree(root)
    skill = root / "skills" / f"skill-{version}"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"skill {version}")
    (root / "mcp").mkdir()
    (root / "mcp/config.json").write_text(
        json.dumps(
            {
                f"mcp-{version}": {
                    "name": f"mcp-{version}",
                    "command": f"server-{version}",
                },
            },
        ),
    )
    package = repository._package_from_payload(
        definition_id,
        {**payload, "enabled": True},
    )
    repository._write(package)
    return package.definition


def _initialize(workspace, definition):
    initialize = getattr(
        dependencies,
        "initialize_community_expert_main_dependency_view",
        None,
    )
    assert callable(
        initialize,
    ), "expert main needs its own versioned dependency view"
    return initialize(
        workspace_dir=workspace,
        chat_id=CHAT_ID,
        definition=definition,
    )


def test_main_views_follow_version_without_changing_legacy_chat_view(tmp_path):
    first = _install(tmp_path)
    legacy = dependencies.initialize_community_expert_dependency_view(
        workspace_dir=tmp_path,
        chat_id=CHAT_ID,
        definition=first,
    )
    first_view = _initialize(tmp_path, first)
    second = _install(
        tmp_path,
        version="2",
        definition_id=first.agent_owned.definition_id,
    )
    second_view = _initialize(tmp_path, second)
    assert first_view != second_view
    assert (first_view / "skills/skill-1/SKILL.md").read_text() == "skill 1"
    assert (second_view / "skills/skill-2/SKILL.md").read_text() == "skill 2"
    assert list(json.loads((second_view / "mcp/config.json").read_text())) == [
        "mcp-2",
    ]
    assert (
        dependencies.initialize_community_expert_dependency_view(
            workspace_dir=tmp_path,
            chat_id=CHAT_ID,
            definition=second,
        )
        == legacy
    )
    assert (legacy / "skills/skill-1/SKILL.md").read_text() == "skill 1"


def test_concurrent_same_version_only_publishes_one_complete_view(
    tmp_path,
    monkeypatch,
):
    definition = _install(tmp_path)
    barrier = threading.Barrier(2)
    replace = dependencies.os.replace

    def publish_together(source, target):
        barrier.wait(timeout=5)
        return replace(source, target)

    monkeypatch.setattr(dependencies.os, "replace", publish_together)
    with ThreadPoolExecutor(max_workers=2) as pool:
        roots = list(
            pool.map(lambda _: _initialize(tmp_path, definition), range(2)),
        )
    assert roots[0] == roots[1]
    assert (roots[0] / "skills/skill-1/SKILL.md").read_text() == "skill 1"
    assert not list(roots[0].parent.glob(".main-*.tmp"))


def test_update_in_progress_cannot_mix_definition_and_new_dependencies(
    tmp_path,
):
    first = _install(tmp_path)
    definition_id = first.agent_owned.definition_id
    marker = tmp_path / "agents" / f".{definition_id}.toml.{uuid4().hex}.tmp"
    marker.write_text("new definition being installed")
    with pytest.raises(dependencies.ExpertDependencyViewError):
        _initialize(tmp_path, first)
    marker.unlink()
    assert _initialize(tmp_path, first).is_dir()


def test_changed_definition_during_copy_fails_without_publishing(
    tmp_path,
    monkeypatch,
):
    first = _install(tmp_path)
    copy = dependencies._copy_skill_tree_no_symlinks

    def change_after_copy(source, target):
        copy(source, target)
        path = tmp_path / "agents" / f"{first.agent_owned.definition_id}.toml"
        path.write_text(path.read_text().replace("role 1", "new role"))

    monkeypatch.setattr(
        dependencies,
        "_copy_skill_tree_no_symlinks",
        change_after_copy,
    )
    with pytest.raises(dependencies.ExpertDependencyViewError):
        _initialize(tmp_path, first)


def test_symlinked_private_skill_never_falls_back_to_profile(tmp_path):
    definition = _install(tmp_path)
    skill = (
        tmp_path
        / "agents"
        / f"{definition.agent_owned.definition_id}.dependencies/skills/skill-1"
    )
    shutil.rmtree(skill)
    profile_skill = tmp_path / "active_skills/skill-1"
    profile_skill.mkdir(parents=True)
    (profile_skill / "SKILL.md").write_text("profile resource")
    skill.symlink_to(profile_skill, target_is_directory=True)
    with pytest.raises(dependencies.ExpertDependencyViewError):
        _initialize(tmp_path, definition)


def test_main_first_does_not_prevent_original_subagent_view(tmp_path):
    definition = _install(tmp_path)
    main_view = _initialize(tmp_path, definition)
    legacy = dependencies.initialize_community_expert_dependency_view(
        workspace_dir=tmp_path,
        chat_id=CHAT_ID,
        definition=definition,
    )
    assert legacy != main_view
    assert (legacy / "skills/skill-1/SKILL.md").read_text() == "skill 1"


def test_replaced_received_content_with_same_version_gets_distinct_view(
    tmp_path,
):
    definition = _install(tmp_path)
    first = _initialize(tmp_path, definition)
    source = (
        tmp_path
        / "agents"
        / f"{definition.agent_owned.definition_id}.dependencies/skills/skill-1/SKILL.md"
    )
    source.write_text("restored local received content")
    second = _initialize(tmp_path, definition)
    assert first != second
    assert (first / "skills/skill-1/SKILL.md").read_text() == "skill 1"
    assert (
        second / "skills/skill-1/SKILL.md"
    ).read_text() == "restored local received content"


def test_symlinked_view_parent_is_rejected(tmp_path):
    definition = _install(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".expert_sessions").symlink_to(
        outside,
        target_is_directory=True,
    )
    with pytest.raises(dependencies.ExpertDependencyViewError):
        _initialize(tmp_path, definition)
    assert not list(outside.iterdir())


def test_cross_version_race_rejects_old_copy_and_keeps_new_winner(
    tmp_path,
    monkeypatch,
):
    first = _install(tmp_path)
    copied_old = threading.Event()
    allow_old_to_finish = threading.Event()
    copy = dependencies._copy_skill_tree_no_symlinks

    def pause_old(source, target):
        copy(source, target)
        if (target / "skills/skill-1").exists():
            copied_old.set()
            assert allow_old_to_finish.wait(timeout=5)

    monkeypatch.setattr(
        dependencies,
        "_copy_skill_tree_no_symlinks",
        pause_old,
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        old = pool.submit(_initialize, tmp_path, first)
        assert copied_old.wait(timeout=5)
        second = _install(
            tmp_path,
            version="2",
            definition_id=first.agent_owned.definition_id,
        )
        current = _initialize(tmp_path, second)
        allow_old_to_finish.set()
        with pytest.raises(dependencies.ExpertDependencyViewError):
            old.result(timeout=5)
    assert (current / "skills/skill-2/SKILL.md").read_text() == "skill 2"
    assert not list(current.parent.glob(".main-*.tmp"))


def test_withdrawal_or_broken_mcp_never_reuses_existing_view(tmp_path):
    definition = _install(tmp_path)
    _initialize(tmp_path, definition)
    root = (
        tmp_path
        / "agents"
        / f"{definition.agent_owned.definition_id}.dependencies"
    )
    config = root / "mcp/config.json"
    original = config.read_text()
    config.write_text("broken JSON")
    with pytest.raises(OSError):
        _initialize(tmp_path, definition)
    config.write_text(original)
    shutil.rmtree(root)
    with pytest.raises(dependencies.ExpertDependencyViewError):
        _initialize(tmp_path, definition)


def test_missing_private_skill_entrypoint_is_structural_failure(tmp_path):
    definition = _install(tmp_path)
    root = (
        tmp_path
        / "agents"
        / f"{definition.agent_owned.definition_id}.dependencies"
    )
    (root / "skills/skill-1/SKILL.md").unlink()
    with pytest.raises(dependencies.ExpertDependencyViewError):
        _initialize(tmp_path, definition)


def test_mutated_cached_skill_is_not_used_with_original_definition(tmp_path):
    definition = _install(tmp_path)
    view = _initialize(tmp_path, definition)
    (view / "skills/skill-1/SKILL.md").write_text(
        "modified cached instruction",
    )
    with pytest.raises(dependencies.ExpertDependencyViewError):
        _initialize(tmp_path, definition)
