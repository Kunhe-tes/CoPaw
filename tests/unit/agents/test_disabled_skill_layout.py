# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from swe.agents import skills_manager
from swe.agents.skills_manager import (
    _default_workspace_manifest,
    get_workspace_disabled_skills_dir,
    get_workspace_skill_manifest_path,
    get_workspace_skills_dir,
    reconcile_workspace_manifest,
    resolve_effective_skills,
    resolve_workspace_managed_skill_dir,
)
from swe.utils.fs_text import SanitizedFsText


def _write_skill(path: Path, marker: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill\n---\n" + f"\n{marker}\n",
        encoding="utf-8",
    )


def _write_manifest(
    workspace: Path,
    skills: dict[str, dict[str, object]],
) -> None:
    manifest_path = get_workspace_skill_manifest_path(workspace)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "layout_version": 2,
                "version": 0,
                "skills": skills,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _entry(enabled: bool) -> dict[str, object]:
    return {
        "enabled": enabled,
        "channels": ["all"],
        "source": "customized",
        "config": {},
        "metadata": {},
    }


def _skill_content(name: str, marker: str) -> str:
    return (
        f"---\nname: {name}\ndescription: {name} skill\n---\n" f"\n{marker}\n"
    )


def _skill_zip(name: str, marker: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            f"{name}/SKILL.md",
            _skill_content(name, marker),
        )
    return buffer.getvalue()


def test_workspace_skill_layout_paths(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"

    assert get_workspace_skills_dir(workspace_dir) == workspace_dir / "skills"
    assert get_workspace_disabled_skills_dir(workspace_dir) == (
        workspace_dir / ".disabled_skills"
    )
    assert get_workspace_skill_manifest_path(workspace_dir) == (
        workspace_dir / "skill.json"
    )
    assert not (workspace_dir / ".skill_state").exists()


def test_default_workspace_manifest_declares_layout_v2() -> None:
    manifest = _default_workspace_manifest()

    assert manifest["layout_version"] == 2
    assert manifest["schema_version"] == "workspace-skill-manifest.v1"
    assert manifest["version"] == 0


def test_managed_skill_dir_follows_manifest_enablement(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"

    assert (
        resolve_workspace_managed_skill_dir(
            workspace_dir,
            "docx",
            enabled=True,
        )
        == workspace_dir / "skills" / "docx"
    )
    assert (
        resolve_workspace_managed_skill_dir(
            workspace_dir,
            "docx",
            enabled=False,
        )
        == workspace_dir / ".disabled_skills" / "docx"
    )


def test_reconcile_moves_registered_disabled_skill_out_of_runtime_root(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    active = workspace / "skills" / "demo"
    disabled = workspace / ".disabled_skills" / "demo"
    _write_skill(active, "active-copy")
    _write_manifest(workspace, {"demo": _entry(enabled=False)})

    state = reconcile_workspace_manifest(workspace)

    assert not active.exists()
    assert disabled.exists()
    assert resolve_effective_skills(workspace, "console") == []
    assert state["skills"]["demo"]["enabled"] is False


def test_reconcile_moves_registered_enabled_skill_into_runtime_root(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    active = workspace / "skills" / "demo"
    disabled = workspace / ".disabled_skills" / "demo"
    _write_skill(disabled, "disabled-copy")
    _write_manifest(workspace, {"demo": _entry(enabled=True)})

    reconcile_workspace_manifest(workspace)

    assert active.exists()
    assert not disabled.exists()
    assert resolve_effective_skills(workspace, "console") == ["demo"]


def test_reconcile_prefers_runtime_copy_when_both_registered_copies_exist(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    active = workspace / "skills" / "demo"
    disabled = workspace / ".disabled_skills" / "demo"
    _write_skill(active, "runtime-wins")
    _write_skill(disabled, "discard-me")
    _write_manifest(workspace, {"demo": _entry(enabled=False)})

    reconcile_workspace_manifest(workspace)

    assert not active.exists()
    assert "runtime-wins" in (disabled / "SKILL.md").read_text(
        encoding="utf-8",
    )
    assert "discard-me" not in (disabled / "SKILL.md").read_text(
        encoding="utf-8",
    )


def test_reconcile_ignores_unmanaged_runtime_content(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    manual = workspace / "skills" / "new-skill"
    _write_skill(manual, "manual-copy")
    _write_manifest(workspace, {})

    state = reconcile_workspace_manifest(workspace)

    assert state["skills"] == {}
    assert manual.exists()


def test_reconcile_removes_registered_entry_when_both_copies_are_missing(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    _write_manifest(workspace, {"demo": _entry(enabled=True)})

    state = reconcile_workspace_manifest(workspace)

    assert state["skills"] == {}


def test_effective_skill_resolution_fails_closed_when_move_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    active = workspace / "skills" / "demo"
    disabled = workspace / ".disabled_skills" / "demo"
    _write_skill(disabled, "disabled-copy")
    _write_manifest(workspace, {"demo": _entry(enabled=True)})

    def fail_move(_source: Path, _target: Path) -> None:
        raise OSError("cannot move registered skill")

    monkeypatch.setattr(
        "swe.agents.skills_manager._move_skill_dir",
        fail_move,
    )

    with pytest.raises(OSError, match="cannot move registered skill"):
        resolve_effective_skills(workspace, "console")
    assert not active.exists()


def test_reconcile_rolls_back_sanitized_rename_when_manifest_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    original_dir = workspace / "skills" / "bad-skill"
    sanitized_dir = workspace / "skills" / "safe-skill"
    _write_skill(original_dir, "registered-copy")
    _write_manifest(workspace, {"bad-skill": _entry(enabled=True)})
    manifest_path = get_workspace_skill_manifest_path(workspace)

    original_sanitize = skills_manager.sanitize_fs_text

    def sanitize_bad_skill(text: str) -> SanitizedFsText:
        if text == "bad-skill":
            return SanitizedFsText(
                value="safe-skill",
                changed=True,
                strategy="replace",
            )
        return original_sanitize(text)

    def fail_manifest_write(_path: Path, _payload: dict) -> None:
        raise OSError("manifest write failed")

    monkeypatch.setattr(
        skills_manager,
        "sanitize_fs_text",
        sanitize_bad_skill,
    )
    monkeypatch.setattr(
        skills_manager,
        "_write_json_atomic",
        fail_manifest_write,
    )

    with pytest.raises(OSError, match="manifest write failed"):
        reconcile_workspace_manifest(workspace)

    assert original_dir.exists()
    assert not sanitized_dir.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "bad-skill" in manifest["skills"]
    assert "safe-skill" not in manifest["skills"]


def test_reconcile_preserves_publication_and_rollback_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    original_dir = workspace / "skills" / "bad-skill"
    sanitized_dir = workspace / "skills" / "safe-skill"
    _write_skill(original_dir, "registered-copy")
    _write_manifest(workspace, {"bad-skill": _entry(enabled=True)})

    original_sanitize = skills_manager.sanitize_fs_text
    original_move = skills_manager._move_skill_dir
    publication_error = OSError("manifest write failed")
    rollback_error = OSError("rollback failed")

    def sanitize_bad_skill(text: str) -> SanitizedFsText:
        if text == "bad-skill":
            return SanitizedFsText(
                value="safe-skill",
                changed=True,
                strategy="replace",
            )
        return original_sanitize(text)

    def fail_manifest_write(_path: Path, _payload: dict) -> None:
        raise publication_error

    def fail_rollback(source: Path, target: Path) -> None:
        if source == sanitized_dir and target == original_dir:
            raise rollback_error
        original_move(source, target)

    monkeypatch.setattr(
        skills_manager,
        "sanitize_fs_text",
        sanitize_bad_skill,
    )
    monkeypatch.setattr(
        skills_manager,
        "_write_json_atomic",
        fail_manifest_write,
    )
    monkeypatch.setattr(
        skills_manager,
        "_move_skill_dir",
        fail_rollback,
    )

    with pytest.raises(RuntimeError) as exc_info:
        reconcile_workspace_manifest(workspace)

    error = exc_info.value
    assert isinstance(
        error,
        skills_manager.WorkspaceManifestReconciliationError,
    )
    assert error.reconciliation_error is publication_error
    assert error.rollback_errors == (rollback_error,)
    assert error.__cause__ is publication_error


def test_reconcile_rejects_malformed_workspace_manifest_without_mutation(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    active = workspace / "skills" / "demo"
    disabled = workspace / ".disabled_skills" / "demo"
    _write_skill(active, "active-copy")
    _write_skill(disabled, "disabled-copy")
    manifest_path = get_workspace_skill_manifest_path(workspace)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    malformed = "{not valid json"
    manifest_path.write_text(malformed, encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        reconcile_workspace_manifest(workspace)

    assert manifest_path.read_text(encoding="utf-8") == malformed
    assert active.exists()
    assert disabled.exists()


def test_disable_moves_package_before_committing_disabled_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    service = skills_manager.SkillService(workspace)
    assert (
        service.create_skill(
            "demo",
            _skill_content("demo", "active-copy"),
            enable=True,
        )
        == "demo"
    )
    active = workspace / "skills" / "demo"
    disabled = workspace / ".disabled_skills" / "demo"
    _write_skill(disabled, "stale-hidden-copy")
    manifest_path = get_workspace_skill_manifest_path(workspace)
    original_mutate = skills_manager._mutate_json

    def assert_move_precedes_manifest(
        path: Path,
        default: dict,
        mutator,
    ):
        assert path == manifest_path
        current = json.loads(path.read_text(encoding="utf-8"))
        assert current["skills"]["demo"]["enabled"] is True
        assert not active.exists()
        assert disabled.exists()
        assert "active-copy" in (disabled / "SKILL.md").read_text(
            encoding="utf-8",
        )
        return original_mutate(path, default, mutator)

    monkeypatch.setattr(
        skills_manager,
        "_mutate_json",
        assert_move_precedes_manifest,
    )

    result = service.disable_skill("demo")

    assert result["success"] is True
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["skills"]["demo"]["enabled"] is False


def test_enable_scans_then_commits_state_then_moves_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    active = workspace / "skills" / "demo"
    disabled = workspace / ".disabled_skills" / "demo"
    _write_skill(disabled, "disabled-copy")
    _write_manifest(workspace, {"demo": _entry(enabled=False)})
    manifest_path = get_workspace_skill_manifest_path(workspace)
    service = skills_manager.SkillService(workspace)
    observed: list[str] = []
    original_mutate = skills_manager._mutate_json
    original_move = skills_manager._move_skill_dir

    def record_scan(skill_dir: Path, skill_name: str) -> None:
        assert skill_dir == disabled
        assert skill_name == "demo"
        assert not active.exists()
        assert (
            json.loads(manifest_path.read_text(encoding="utf-8"))["skills"][
                "demo"
            ]["enabled"]
            is False
        )
        observed.append("scan")

    def record_manifest(
        path: Path,
        default: dict,
        mutator,
    ):
        assert observed == ["scan"]
        assert disabled.exists()
        result = original_mutate(path, default, mutator)
        observed.append("manifest")
        return result

    def record_move(source: Path, target: Path) -> None:
        assert observed == ["scan", "manifest"]
        assert source == disabled
        assert target == active
        assert (
            json.loads(manifest_path.read_text(encoding="utf-8"))["skills"][
                "demo"
            ]["enabled"]
            is True
        )
        original_move(source, target)
        observed.append("move")

    monkeypatch.setattr(
        skills_manager,
        "_scan_skill_dir_or_raise",
        record_scan,
    )
    monkeypatch.setattr(skills_manager, "_mutate_json", record_manifest)
    monkeypatch.setattr(skills_manager, "_move_skill_dir", record_move)

    result = service.enable_skill("demo")

    assert result["success"] is True
    assert observed == ["scan", "manifest", "move"]
    assert active.exists()
    assert not disabled.exists()


def test_enable_does_not_report_success_when_move_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    active = workspace / "skills" / "demo"
    disabled = workspace / ".disabled_skills" / "demo"
    _write_skill(disabled, "disabled-copy")
    _write_manifest(workspace, {"demo": _entry(enabled=False)})

    def fail_move(_source: Path, _target: Path) -> None:
        raise OSError("cannot move enabled package")

    monkeypatch.setattr(skills_manager, "_move_skill_dir", fail_move)

    result = skills_manager.SkillService(workspace).enable_skill("demo")

    assert result["success"] is False
    assert result["reason"] == "move_failed"
    assert (
        json.loads(
            get_workspace_skill_manifest_path(workspace).read_text(
                encoding="utf-8",
            ),
        )["skills"]["demo"]["enabled"]
        is True
    )
    assert disabled.exists()
    assert not active.exists()


def test_create_and_list_disabled_skill_use_hidden_root(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    service = skills_manager.SkillService(workspace)

    created = service.create_skill(
        "demo",
        _skill_content("demo", "disabled-copy"),
        enable=False,
    )

    assert created == "demo"
    assert not (workspace / "skills" / "demo").exists()
    assert (workspace / ".disabled_skills" / "demo").exists()
    assert [skill.name for skill in service.list_all_skills()] == ["demo"]


def test_create_overwrite_preserves_disabled_state_and_config(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    service = skills_manager.SkillService(workspace)
    service.create_skill(
        "demo",
        _skill_content("demo", "original"),
        config={"token": "keep"},
        enable=False,
    )
    reconcile_workspace_manifest(workspace)
    service.set_skill_channels("demo", ["discord"])

    created = service.create_skill(
        "demo",
        _skill_content("demo", "updated"),
        overwrite=True,
        config=None,
        enable=True,
    )

    assert created == "demo"
    hidden = workspace / ".disabled_skills" / "demo" / "SKILL.md"
    assert "updated" in hidden.read_text(encoding="utf-8")
    assert not (workspace / "skills" / "demo").exists()
    entry = json.loads(
        get_workspace_skill_manifest_path(workspace).read_text(
            encoding="utf-8",
        ),
    )["skills"]["demo"]
    assert entry["enabled"] is False
    assert entry["channels"] == ["discord"]
    assert entry["config"] == {"token": "keep"}


def test_edit_and_load_disabled_skill_use_hidden_root(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = skills_manager.SkillService(workspace)
    service.create_skill(
        "demo",
        _skill_content("demo", "original"),
        enable=False,
    )
    reconcile_workspace_manifest(workspace)

    result = service.save_skill(
        skill_name="demo",
        content=_skill_content("demo", "updated"),
        references={"notes.md": "hidden reference"},
    )

    assert result["success"] is True
    assert not (workspace / "skills" / "demo").exists()
    hidden = workspace / ".disabled_skills" / "demo"
    assert "updated" in (hidden / "SKILL.md").read_text(encoding="utf-8")
    assert (
        service.load_skill_file(
            "demo",
            "references/notes.md",
            "customized",
        )
        == "hidden reference"
    )


def test_rename_disabled_skill_stays_hidden_and_preserves_state(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    service = skills_manager.SkillService(workspace)
    service.create_skill(
        "demo",
        _skill_content("demo", "original"),
        config={"token": "keep"},
        enable=False,
    )
    reconcile_workspace_manifest(workspace)
    service.set_skill_channels("demo", ["discord"])

    result = service.save_skill(
        skill_name="demo",
        target_name="renamed",
        content=_skill_content("renamed", "updated"),
    )

    assert result == {"success": True, "mode": "rename", "name": "renamed"}
    assert not (workspace / "skills" / "renamed").exists()
    assert not (workspace / ".disabled_skills" / "demo").exists()
    assert (workspace / ".disabled_skills" / "renamed").exists()
    entry = json.loads(
        get_workspace_skill_manifest_path(workspace).read_text(
            encoding="utf-8",
        ),
    )["skills"]["renamed"]
    assert entry["enabled"] is False
    assert entry["channels"] == ["discord"]
    assert entry["config"] == {"token": "keep"}


def test_rename_conflict_checks_hidden_root(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = skills_manager.SkillService(workspace)
    service.create_skill(
        "demo",
        _skill_content("demo", "original"),
        enable=False,
    )
    reconcile_workspace_manifest(workspace)
    _write_skill(workspace / ".disabled_skills" / "taken", "occupied")

    result = service.save_skill(
        skill_name="demo",
        target_name="taken",
        content=_skill_content("taken", "updated"),
    )

    assert result["success"] is False
    assert result["reason"] == "conflict"
    assert (workspace / ".disabled_skills" / "demo").exists()


def test_delete_disabled_skill_removes_hidden_package_and_registration(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    service = skills_manager.SkillService(workspace)
    service.create_skill(
        "demo",
        _skill_content("demo", "disabled-copy"),
        enable=False,
    )
    reconcile_workspace_manifest(workspace)

    deleted = service.delete_skill("demo")

    assert deleted is True
    assert not (workspace / ".disabled_skills" / "demo").exists()
    manifest = json.loads(
        get_workspace_skill_manifest_path(workspace).read_text(
            encoding="utf-8",
        ),
    )
    assert "demo" not in manifest["skills"]


def test_replace_existing_disabled_skill_uses_hidden_root_and_state(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    service = skills_manager.SkillService(workspace)
    service.create_skill(
        "demo",
        _skill_content("demo", "original"),
        config={"token": "keep"},
        enable=False,
    )
    reconcile_workspace_manifest(workspace)
    service.set_skill_channels("demo", ["discord"])
    source_dir = tmp_path / "replacement"
    _write_skill(source_dir, "replacement")

    result = service.replace_workspace_skill_from_dir(
        skill_name="demo",
        source_dir=source_dir,
        config={"replacement": "ignore"},
    )

    assert result == {"success": True, "name": "demo"}
    assert not (workspace / "skills" / "demo").exists()
    hidden = workspace / ".disabled_skills" / "demo" / "SKILL.md"
    assert "replacement" in hidden.read_text(encoding="utf-8")
    entry = json.loads(
        get_workspace_skill_manifest_path(workspace).read_text(
            encoding="utf-8",
        ),
    )["skills"]["demo"]
    assert entry["enabled"] is False
    assert entry["channels"] == ["discord"]
    assert entry["config"] == {"token": "keep"}


@pytest.mark.parametrize("enabled_root", [True, False])
def test_replace_workspace_skill_rejects_unmanaged_same_name_in_either_root(
    tmp_path: Path,
    enabled_root: bool,
) -> None:
    workspace = tmp_path / "workspace"
    unmanaged_dir = resolve_workspace_managed_skill_dir(
        workspace,
        "demo",
        enabled=enabled_root,
    )
    _write_skill(unmanaged_dir, "unmanaged original")
    original_bytes = (unmanaged_dir / "SKILL.md").read_bytes()
    source_dir = tmp_path / "replacement"
    _write_skill(source_dir, "replacement")
    manifest_path = get_workspace_skill_manifest_path(workspace)
    assert not manifest_path.exists()

    result = skills_manager.SkillService(
        workspace,
    ).replace_workspace_skill_from_dir(
        skill_name="demo",
        source_dir=source_dir,
    )

    assert result["success"] is False
    assert result["reason"] == "conflict"
    assert (unmanaged_dir / "SKILL.md").read_bytes() == original_bytes
    opposite_dir = resolve_workspace_managed_skill_dir(
        workspace,
        "demo",
        enabled=not enabled_root,
    )
    assert not opposite_dir.exists()
    assert not manifest_path.exists()


def test_import_new_disabled_skill_registers_hidden_package_directly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"

    def forbid_discovery(_workspace: Path) -> dict:
        raise AssertionError("import must register without reconciliation")

    monkeypatch.setattr(
        skills_manager,
        "reconcile_workspace_manifest",
        forbid_discovery,
    )

    result = skills_manager.SkillService(workspace).import_from_zip(
        _skill_zip("demo", "imported"),
        enable=False,
    )

    assert result["imported"] == ["demo"]
    assert not (workspace / "skills" / "demo").exists()
    assert (workspace / ".disabled_skills" / "demo").exists()
    entry = json.loads(
        get_workspace_skill_manifest_path(workspace).read_text(
            encoding="utf-8",
        ),
    )["skills"]["demo"]
    assert entry["enabled"] is False


def test_import_overwrite_preserves_existing_disabled_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    service = skills_manager.SkillService(workspace)
    service.create_skill(
        "demo",
        _skill_content("demo", "original"),
        config={"token": "keep"},
        enable=False,
    )
    reconcile_workspace_manifest(workspace)
    service.set_skill_channels("demo", ["discord"])

    def forbid_discovery(_workspace: Path) -> dict:
        raise AssertionError("import must refresh without reconciliation")

    monkeypatch.setattr(
        skills_manager,
        "reconcile_workspace_manifest",
        forbid_discovery,
    )

    result = service.import_from_zip(
        _skill_zip("demo", "updated"),
        overwrite=True,
        enable=True,
    )

    assert result["imported"] == ["demo"]
    assert not (workspace / "skills" / "demo").exists()
    hidden = workspace / ".disabled_skills" / "demo" / "SKILL.md"
    assert "updated" in hidden.read_text(encoding="utf-8")
    entry = json.loads(
        get_workspace_skill_manifest_path(workspace).read_text(
            encoding="utf-8",
        ),
    )["skills"]["demo"]
    assert entry["enabled"] is False
    assert entry["channels"] == ["discord"]
    assert entry["config"] == {"token": "keep"}


def test_pool_download_overwrite_preserves_existing_disabled_state(
    tmp_path: Path,
) -> None:
    working_dir = tmp_path / "tenant"
    workspace = working_dir / "workspaces" / "default"
    pool = skills_manager.SkillPoolService(working_dir=working_dir)
    pool.create_skill(
        "demo",
        _skill_content("demo", "pool replacement"),
        config={"pool": "ignore"},
    )
    workspace_service = skills_manager.SkillService(workspace)
    workspace_service.create_skill(
        "demo",
        _skill_content("demo", "workspace original"),
        config={"workspace": "keep"},
        enable=False,
    )
    workspace_service.set_skill_channels("demo", ["discord"])

    result = pool.download_to_workspace(
        "demo",
        workspace,
        overwrite=True,
    )

    assert result["success"] is True
    assert not (workspace / "skills" / "demo").exists()
    hidden = workspace / ".disabled_skills" / "demo" / "SKILL.md"
    assert "pool replacement" in hidden.read_text(encoding="utf-8")
    entry = json.loads(
        get_workspace_skill_manifest_path(workspace).read_text(
            encoding="utf-8",
        ),
    )["skills"]["demo"]
    assert entry["enabled"] is False
    assert entry["channels"] == ["discord"]
    assert entry["config"] == {"workspace": "keep"}


def test_new_pool_download_defaults_enabled_and_uses_pool_config(
    tmp_path: Path,
) -> None:
    working_dir = tmp_path / "tenant"
    workspace = working_dir / "workspaces" / "default"
    pool = skills_manager.SkillPoolService(working_dir=working_dir)
    pool.create_skill(
        "demo",
        _skill_content("demo", "pool content"),
        config={"pool": "use"},
    )

    result = pool.download_to_workspace("demo", workspace)

    assert result["success"] is True
    assert (workspace / "skills" / "demo" / "SKILL.md").exists()
    assert not (workspace / ".disabled_skills" / "demo").exists()
    entry = json.loads(
        get_workspace_skill_manifest_path(workspace).read_text(
            encoding="utf-8",
        ),
    )["skills"]["demo"]
    assert entry["enabled"] is True
    assert entry["channels"] == ["all"]
    assert entry["config"] == {"pool": "use"}


@pytest.mark.parametrize("enabled_root", [True, False])
@pytest.mark.parametrize(
    "operation",
    ["download_to_workspace", "preflight_download_to_workspace"],
)
def test_pool_download_rejects_unmanaged_same_name_in_either_root(
    tmp_path: Path,
    enabled_root: bool,
    operation: str,
) -> None:
    working_dir = tmp_path / "tenant"
    workspace = working_dir / "workspaces" / "default"
    pool = skills_manager.SkillPoolService(working_dir=working_dir)
    pool.create_skill(
        "demo",
        _skill_content("demo", "pool content"),
    )
    unmanaged_dir = resolve_workspace_managed_skill_dir(
        workspace,
        "demo",
        enabled=enabled_root,
    )
    _write_skill(unmanaged_dir, "unmanaged content")
    original_bytes = (unmanaged_dir / "SKILL.md").read_bytes()
    manifest_path = get_workspace_skill_manifest_path(workspace)
    assert not manifest_path.exists()

    result = getattr(pool, operation)(
        "demo",
        workspace,
        overwrite=True,
    )

    assert result["success"] is False
    assert result["reason"] == "conflict"
    assert (unmanaged_dir / "SKILL.md").read_bytes() == original_bytes
    assert not manifest_path.exists()
