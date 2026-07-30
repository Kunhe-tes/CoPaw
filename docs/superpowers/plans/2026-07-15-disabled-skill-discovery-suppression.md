# Disabled Skill Discovery Suppression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move registered disabled Workspace skills out of `skills/` into `.disabled_skills/`, move Workspace management state into `.skill_state/manifest.json`, and provide a one-time deployment CLI for migrating the old layout.

**Architecture:** Keep Workspace skill layout policy centralized in `skills_manager.py`: the manifest is authoritative, active and disabled roots materialize enablement, and reconciliation handles only registered entries. Put the one-time, all-or-nothing migration engine in a separate module imported by the Click CLI so runtime startup never carries legacy-layout compatibility.

**Tech Stack:** Python 3.10+, Click, pathlib/shutil/tempfile, existing cross-process JSON file locking, Pydantic models, pytest

---

## Risk and file map

GitNexus reports HIGH upstream impact for `get_workspace_skill_manifest_path` (18 direct callers, 3 affected process groups), `reconcile_workspace_manifest` (13 direct callers, initialization and Agent creation), and `TenantInitializer.seed_default_workspace_skills_from_default` (5 direct callers, initialization and configuration distribution). Every task below keeps public helper names stable, changes behavior behind those helpers, and runs focused regression suites before broad tests.

Before the first edit in each task, satisfy the repository impact gate for every existing symbol changed in that task. Previously measured targets may reuse the results above; additionally run upstream impact for `SkillInvocationDetector.set_enabled_skills`, `SkillService.replace_workspace_skill_from_dir`, `TenantInitializer._prepare_source_workspace_state`, `TenantInitializer._has_default_workspace_skills`, `_build_workspace_skill_specs`, `_snapshot_workspace_skill`, `_restore_workspace_skill`, `_initialize_agent_workspace`, and `skills_group` immediately before their respective edits. Report and stop for user review if any new result is HIGH or CRITICAL.

Every Task 1–6 commit step has the same mandatory change-detection gate: execute its `git add` command, then run GitNexus `detect_changes({scope: "staged"})`, review the listed symbols and flows, and only then execute the shown `git commit --only`. The known staged `tests/unit/app/test_runtime_diagnostic.py` change belongs to the user and may appear in staged detection, but no task commit may include or modify it. Report and stop for user review if task changes have HIGH or CRITICAL risk.

**Create:**

- `src/swe/agents/workspace_skill_layout_migration.py` — read-only preflight, Workspace discovery, apply, rollback, and migration reports.
- `tests/unit/agents/test_disabled_skill_layout.py` — path, reconciliation, runtime, and lifecycle behavior.
- `tests/unit/agents/test_workspace_skill_layout_migration.py` — migration engine behavior.
- `tests/unit/cli/test_cli_skills_migration.py` — Click command contract.

**Modify:**

- `src/swe/agents/skills_manager.py` — layout helpers, v2 manifest, registered-only reconciliation, state-aware SkillService, Pool download behavior.
- `src/swe/agents/skill_invocation_detector.py` — read runtime skill metadata from the v2 manifest path.
- `src/swe/app/workspace/tenant_initializer.py` — seed active and disabled registered packages while preserving state.
- `src/swe/app/routers/agents.py` — register Pool skills explicitly when creating an Agent Workspace.
- `src/swe/app/routers/skills.py` — resolve management views and rollback snapshots from manifest state.
- `src/swe/cli/skills_cmd.py` — deployment-only `migrate-layout` command.
- `tests/unit/agents/test_utf8_skill_cleanup.py` — registered-only UTF-8 directory rename expectations.
- `tests/unit/agents/test_skill_invocation_detector.py` — v2 manifest metadata cache regression.
- `tests/unit/app/test_runner_session_skill_freshness.py` — write runtime fixtures through the v2 manifest helper.
- `tests/unit/workspace/test_tenant_skill_seeding.py` — disabled package seeding.
- `tests/unit/routers/test_skills_tenant_scope.py` — disabled management view, Pool rollback, and registered fixture updates.

Do not modify ordinary file search, glob, shell, or File Guardian code. Do not stage or commit the pre-existing `tests/unit/app/test_runtime_diagnostic.py` change.

### Task 1: Introduce Workspace layout primitives

**Files:**

- Create: `tests/unit/agents/test_disabled_skill_layout.py`
- Modify: `src/swe/agents/skills_manager.py:166-214,628-634`
- Modify: `src/swe/agents/skill_invocation_detector.py:259-325`
- Modify: `tests/unit/agents/test_skill_invocation_detector.py`
- Modify: `tests/unit/app/test_runner_session_skill_freshness.py`

- [ ] **Step 1: Write failing path and manifest tests**

```python
# tests/unit/agents/test_disabled_skill_layout.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from swe.agents.skills_manager import (
    _default_workspace_manifest,
    get_workspace_disabled_skills_dir,
    get_workspace_skill_manifest_path,
    get_workspace_skill_state_dir,
    get_workspace_skills_dir,
    resolve_workspace_managed_skill_dir,
)


def test_workspace_skill_layout_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    assert get_workspace_skills_dir(workspace) == workspace / "skills"
    assert get_workspace_disabled_skills_dir(workspace) == (
        workspace / ".disabled_skills"
    )
    assert get_workspace_skill_state_dir(workspace) == workspace / ".skill_state"
    assert get_workspace_skill_manifest_path(workspace) == (
        workspace / ".skill_state" / "manifest.json"
    )


def test_default_workspace_manifest_declares_layout_v2() -> None:
    manifest = _default_workspace_manifest()

    assert manifest["layout_version"] == 2
    assert manifest["schema_version"] == "workspace-skill-manifest.v1"
    assert manifest["version"] == 0


def test_managed_skill_dir_follows_manifest_enablement(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    assert resolve_workspace_managed_skill_dir(
        workspace,
        "docx",
        enabled=True,
    ) == workspace / "skills" / "docx"
    assert resolve_workspace_managed_skill_dir(
        workspace,
        "docx",
        enabled=False,
    ) == workspace / ".disabled_skills" / "docx"
```

After importing `json` and `get_workspace_skill_manifest_path` in `test_skill_invocation_detector.py`, add:

```python
def test_set_enabled_skills_reads_metadata_from_v2_manifest(tmp_path) -> None:
    manifest_path = get_workspace_skill_manifest_path(tmp_path)
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "layout_version": 2,
                "skills": {
                    "demo": {
                        "enabled": True,
                        "metadata": {
                            "description": "v2 description",
                            "skill_id": "skill-1",
                            "cn_name": "演示技能",
                        },
                    },
                },
            },
        ),
        encoding="utf-8",
    )
    detector = SkillInvocationDetector(workspace_dir=tmp_path)

    detector.set_enabled_skills(["demo"])

    assert detector._skill_descriptions["demo"] == "v2 description"
    assert detector._skill_ids["demo"] == "skill-1"
    assert detector._skill_cn_names["demo"] == "演示技能"
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_skill_invocation_detector.py \
  tests/unit/app/test_runner_session_skill_freshness.py -q
```

Expected: collection fails because the new layout helpers do not exist, or the manifest-path assertion reports the old `workspace/skill.json` path.

- [ ] **Step 3: Add the minimal path policy**

```python
# src/swe/agents/skills_manager.py
WORKSPACE_SKILL_LAYOUT_VERSION = 2


def get_workspace_disabled_skills_dir(workspace_dir: Path) -> Path:
    """Return the registered disabled-skill package directory."""
    return Path(workspace_dir) / ".disabled_skills"


def get_workspace_skill_state_dir(workspace_dir: Path) -> Path:
    """Return the backend-managed Workspace skill state directory."""
    return Path(workspace_dir) / ".skill_state"


def get_workspace_skill_manifest_path(workspace_dir: Path) -> Path:
    """Return the v2 Workspace skill manifest path."""
    return get_workspace_skill_state_dir(workspace_dir) / "manifest.json"


def get_legacy_workspace_skill_manifest_path(workspace_dir: Path) -> Path:
    """Return the pre-v2 manifest path used only by the migration CLI."""
    return Path(workspace_dir) / "skill.json"


def resolve_workspace_managed_skill_dir(
    workspace_dir: Path,
    skill_name: str,
    *,
    enabled: bool,
) -> Path:
    root = (
        get_workspace_skills_dir(workspace_dir)
        if enabled
        else get_workspace_disabled_skills_dir(workspace_dir)
    )
    return root / skill_name


def _default_workspace_manifest() -> dict[str, Any]:
    return {
        "schema_version": "workspace-skill-manifest.v1",
        "layout_version": WORKSPACE_SKILL_LAYOUT_VERSION,
        "version": 0,
        "skills": {},
    }
```

Keep `get_workspace_skills_dir()` and its legacy `skill/` to `skills/` rename behavior unchanged. Pool paths and Pool manifest schema remain unchanged.

In `SkillInvocationDetector.set_enabled_skills()`, replace `self._workspace_dir / "skill.json"` with `get_workspace_skill_manifest_path(self._workspace_dir)` and update its docstring to name `.skill_state/manifest.json`. In `_write_skill_manifest()` inside `test_runner_session_skill_freshness.py`, import the same helper, create `manifest_path.parent`, and write the fixture to that returned path.

- [ ] **Step 4: Run focused and manifest-path regression tests**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_skill_invocation_detector.py \
  tests/unit/agents/test_tenant_skill_pool_scope.py \
  tests/unit/workspace/test_cli_agent_id.py \
  tests/unit/app/test_runner_session_skill_freshness.py -q
```

Expected: new tests pass; Pool tests continue to use `skill_pool/skill.json`.

- [ ] **Step 5: Commit only Task 1 files**

```bash
git add src/swe/agents/skills_manager.py \
  src/swe/agents/skill_invocation_detector.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_skill_invocation_detector.py \
  tests/unit/app/test_runner_session_skill_freshness.py
git commit --only -m "refactor(skills): add workspace skill layout primitives" \
  src/swe/agents/skills_manager.py \
  src/swe/agents/skill_invocation_detector.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_skill_invocation_detector.py \
  tests/unit/app/test_runner_session_skill_freshness.py
```

### Task 2: Reconcile registered packages into the authoritative location

**Files:**

- Modify: `src/swe/agents/skills_manager.py:356-410,1232-1322,1375-1440`
- Modify: `tests/unit/agents/test_disabled_skill_layout.py`
- Modify: `tests/unit/agents/test_utf8_skill_cleanup.py`

- [ ] **Step 1: Add failing reconciliation behavior tests**

```python
# append to tests/unit/agents/test_disabled_skill_layout.py
import json

import pytest

from swe.agents.skills_manager import (
    reconcile_workspace_manifest,
    resolve_effective_skills,
)


def _write_skill(path: Path, marker: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {path.name}\ndescription: {marker}\n---\n{marker}\n",
        encoding="utf-8",
    )


def _write_manifest(workspace: Path, skills: dict[str, dict]) -> None:
    path = get_workspace_skill_manifest_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "layout_version": 2,
                "version": 0,
                "skills": skills,
            },
        ),
        encoding="utf-8",
    )


def _entry(enabled: bool) -> dict:
    return {
        "enabled": enabled,
        "channels": ["all"],
        "source": "customized",
        "config": {},
        "metadata": {},
    }


def test_reconcile_moves_registered_disabled_skill_out_of_runtime_root(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    _write_skill(workspace / "skills" / "demo", "active-copy")
    _write_manifest(workspace, {"demo": _entry(False)})

    manifest = reconcile_workspace_manifest(workspace)

    assert manifest["skills"]["demo"]["enabled"] is False
    assert not (workspace / "skills" / "demo").exists()
    assert (workspace / ".disabled_skills" / "demo" / "SKILL.md").exists()
    assert resolve_effective_skills(workspace, "console") == []


def test_reconcile_moves_registered_enabled_skill_into_runtime_root(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    _write_skill(workspace / ".disabled_skills" / "demo", "hidden-copy")
    _write_manifest(workspace, {"demo": _entry(True)})

    reconcile_workspace_manifest(workspace)

    assert (workspace / "skills" / "demo" / "SKILL.md").exists()
    assert not (workspace / ".disabled_skills" / "demo").exists()
    assert resolve_effective_skills(workspace, "console") == ["demo"]


def test_reconcile_prefers_runtime_copy_when_both_registered_copies_exist(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    _write_skill(workspace / "skills" / "demo", "runtime-wins")
    _write_skill(workspace / ".disabled_skills" / "demo", "discard-me")
    _write_manifest(workspace, {"demo": _entry(False)})

    reconcile_workspace_manifest(workspace)

    content = (
        workspace / ".disabled_skills" / "demo" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "runtime-wins" in content
    assert not (workspace / "skills" / "demo").exists()


def test_reconcile_ignores_unmanaged_runtime_content(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_skill(workspace / "skills" / "manual", "manual")
    _write_manifest(workspace, {})

    manifest = reconcile_workspace_manifest(workspace)

    assert manifest["skills"] == {}
    assert (workspace / "skills" / "manual" / "SKILL.md").exists()


def test_reconcile_removes_registered_entry_when_both_copies_are_missing(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    _write_manifest(workspace, {"missing": _entry(False)})

    manifest = reconcile_workspace_manifest(workspace)

    assert "missing" not in manifest["skills"]


def test_effective_skill_resolution_fails_closed_when_move_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    _write_skill(workspace / ".disabled_skills" / "demo", "hidden-copy")
    _write_manifest(workspace, {"demo": _entry(True)})

    def fail_move(source: Path, target: Path) -> None:
        raise OSError(f"cannot move {source} to {target}")

    monkeypatch.setattr(
        "swe.agents.skills_manager._move_skill_dir",
        fail_move,
    )

    with pytest.raises(OSError, match="cannot move"):
        resolve_effective_skills(workspace, "console")

    assert not (workspace / "skills" / "demo").exists()
```

Update the existing registered-directory rename fixture so it writes this v2 manifest before reconciliation:

```python
manifest_path = get_workspace_skill_manifest_path(workspace_dir)
manifest_path.parent.mkdir(parents=True)
manifest_path.write_text(
    json.dumps(
        {
            "layout_version": 2,
            "schema_version": "workspace-skill-manifest.v1",
            "version": 0,
            "skills": {
                "bad-skill": {
                    "enabled": True,
                    "channels": ["all"],
                    "source": "customized",
                    "config": {},
                    "metadata": {},
                },
                "safe-skill": {
                    "enabled": True,
                    "channels": ["all"],
                    "source": "customized",
                    "config": {},
                    "metadata": {},
                },
            },
        },
    ),
    encoding="utf-8",
)
```

Add the unmanaged counterpart explicitly:

```python
def test_reconcile_leaves_unmanaged_unsafe_directory_unchanged(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace_dir = tmp_path / "workspace"
    unsafe_dir = get_workspace_skills_dir(workspace_dir) / "bad-skill"
    _write_skill(unsafe_dir)
    original = skills_manager.sanitize_fs_text

    def fake_sanitize(text: str) -> SanitizedFsText:
        if text == "bad-skill":
            return SanitizedFsText(
                value="safe-skill",
                changed=True,
                strategy="replace",
            )
        return original(text)

    monkeypatch.setattr(skills_manager, "sanitize_fs_text", fake_sanitize)

    manifest = reconcile_workspace_manifest(workspace_dir)

    assert manifest["skills"] == {}
    assert unsafe_dir.exists()
    assert not (get_workspace_skills_dir(workspace_dir) / "safe-skill").exists()
```

In `test_load_skill_file_accepts_sanitized_path`, write a v2 manifest entry for `safe-skill` before calling reconciliation, using `enabled=True`, `channels=["all"]`, `source="customized"`, empty config, and empty metadata. The test is about sanitizing a managed reference path; it must not accidentally rely on unmanaged directory discovery.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_utf8_skill_cleanup.py -q
```

Expected: disabled-directory assertions fail because reconciliation currently scans only `skills/` and treats all discovered directories as managed.

- [ ] **Step 3: Implement registered-only reconciliation**

Replace Workspace reconciliation discovery with this sequence while leaving Pool reconciliation unchanged:

```python
def _move_skill_dir(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source.replace(target)


def _reconcile_registered_skill_location(
    workspace_dir: Path,
    skill_name: str,
    entry: dict[str, Any],
) -> Path | None:
    active_dir = get_workspace_skills_dir(workspace_dir) / skill_name
    disabled_dir = get_workspace_disabled_skills_dir(workspace_dir) / skill_name

    if active_dir.exists() and disabled_dir.exists():
        shutil.rmtree(disabled_dir)

    enabled = bool(entry.get("enabled", False))
    desired_dir = resolve_workspace_managed_skill_dir(
        workspace_dir,
        skill_name,
        enabled=enabled,
    )
    current_dir = active_dir if active_dir.exists() else disabled_dir
    if not current_dir.exists():
        return None
    if current_dir != desired_dir:
        _move_skill_dir(current_dir, desired_dir)
    return desired_dir
```

Within the manifest file lock, iterate only over `payload["skills"]`. For each registered entry, sanitize its key and whichever managed directory currently exists, resolve its desired location, remove the entry when neither copy exists, and refresh metadata from the resolved directory. Never add an entry based only on directory discovery.

Change `resolve_effective_skills()` to append a skill only when the reconciled manifest says enabled and `resolve_workspace_managed_skill_dir(..., enabled=True)` exists. Keep reconciliation exceptions visible so an unresolved move fails closed instead of returning a partially valid runtime view.

- [ ] **Step 4: Run focused and runtime registration tests**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_utf8_skill_cleanup.py \
  tests/unit/agents/test_skill_runtime_profile.py \
  tests/unit/agents/hook_runtime/test_skill_hook_loader.py \
  tests/unit/app/test_runner_session_skill_freshness.py -q
```

Expected: all pass; unmanaged content remains on disk but never appears in the effective skill list.

- [ ] **Step 5: Commit only Task 2 files**

```bash
git add src/swe/agents/skills_manager.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_utf8_skill_cleanup.py
git commit --only -m "feat(skills): reconcile registered skill locations" \
  src/swe/agents/skills_manager.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_utf8_skill_cleanup.py
```

### Task 3: Make SkillService lifecycle operations state-aware

**Files:**

- Modify: `src/swe/agents/skills_manager.py:1691-2289`
- Modify: `src/swe/app/routers/skills.py:302-345,678-705`
- Modify: `tests/unit/agents/test_disabled_skill_layout.py`
- Modify: `tests/unit/routers/test_skills_tenant_scope.py`

- [ ] **Step 1: Add failing lifecycle tests**

```python
# append to tests/unit/agents/test_disabled_skill_layout.py
from swe.agents.skills_manager import SkillService


def test_disable_moves_package_before_committing_disabled_state(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    service = SkillService(workspace)
    assert service.create_skill("demo", "---\nname: demo\n---\n", enable=True)

    result = service.disable_skill("demo")

    assert result["success"] is True
    manifest = service._read_manifest()
    assert manifest["skills"]["demo"]["enabled"] is False
    assert not (workspace / "skills" / "demo").exists()
    assert (workspace / ".disabled_skills" / "demo" / "SKILL.md").exists()


def test_enable_commits_state_then_moves_disabled_package(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = SkillService(workspace)
    assert service.create_skill("demo", "---\nname: demo\n---\n", enable=False)

    result = service.enable_skill("demo")

    assert result["success"] is True
    assert service._read_manifest()["skills"]["demo"]["enabled"] is True
    assert (workspace / "skills" / "demo" / "SKILL.md").exists()
    assert not (workspace / ".disabled_skills" / "demo").exists()


def test_edit_and_load_disabled_skill_use_disabled_store(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = SkillService(workspace)
    service.create_skill(
        "demo",
        "---\nname: demo\n---\n",
        references={"notes.md": "before"},
        enable=False,
    )

    result = service.save_skill(
        skill_name="demo",
        content="---\nname: demo\n---\nafter\n",
        references={"notes.md": "after"},
    )

    assert result["success"] is True
    assert not (workspace / "skills" / "demo").exists()
    assert service.load_skill_file("demo", "references/notes.md", "workspace") == (
        "after"
    )


def test_delete_removes_disabled_package_and_manifest_entry(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = SkillService(workspace)
    service.create_skill("demo", "---\nname: demo\n---\n", enable=False)

    assert service.delete_skill("demo") is True
    assert not (workspace / ".disabled_skills" / "demo").exists()
    assert "demo" not in service._read_manifest()["skills"]


def test_management_specs_include_registered_disabled_package(
    tmp_path: Path,
) -> None:
    from swe.app.routers.skills import _build_workspace_skill_specs

    workspace = tmp_path / "workspace"
    service = SkillService(workspace)
    service.create_skill(
        "demo",
        "---\nname: demo\ndescription: hidden\n---\n",
        enable=False,
    )

    specs = _build_workspace_skill_specs(workspace)

    assert [spec.name for spec in specs] == ["demo"]
    assert specs[0].enabled is False
    assert not (workspace / "skills" / "demo").exists()
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/routers/test_skills_tenant_scope.py -q
```

Expected: create/edit/load/delete assertions fail because SkillService currently hardcodes `get_workspace_skills_dir()`.

- [ ] **Step 3: Resolve every managed path from the manifest entry**

Implement a private SkillService helper and use it in `list_all_skills`, `create_skill`, `save_skill`, rename conflict checks, `delete_skill`, and `load_skill_file`:

```python
def _skill_dir_for_entry(
    self,
    skill_name: str,
    entry: dict[str, Any],
) -> Path:
    return resolve_workspace_managed_skill_dir(
        self.workspace_dir,
        skill_name,
        enabled=bool(entry.get("enabled", False)),
    )
```

For new creates/imports, write directly to the root selected by the requested `enable` value. `import_from_zip()` must atomically add or refresh each imported manifest entry from its resolved directory; it must not depend on reconciliation discovering the copied directory. For overwrite imports, preserve an existing entry's `enabled`, `channels`, and `config`; apply the request's `enable` value only to a genuinely new entry. For edits and renames, preserve the existing entry's enablement and keep both old and new names in the same selected root. Conflict detection must check both `skills/<target>` and `.disabled_skills/<target>`.

Update `_build_workspace_skill_specs()` in `routers/skills.py` to replace its single active `skill_root` with `resolve_workspace_managed_skill_dir(workspace_dir, skill_name, enabled=bool(entry.get("enabled", False)))` for each registered entry. This keeps disabled packages visible in management responses without exposing them to runtime registration.

Replace `_set_workspace_skill_state()` in `test_skills_tenant_scope.py` with explicit managed creation so its disabled fixtures move to the hidden root:

```python
def _set_workspace_skill_state(
    workspace_dir: Path,
    skill_name: str,
    *,
    enabled: bool,
    description: str,
) -> None:
    _write_workspace_scaffold(workspace_dir)
    content = (
        f"---\nname: {skill_name}\ndescription: {description}\n---\n"
    )
    created = SkillService(workspace_dir).create_skill(
        skill_name,
        content,
        enable=enabled,
    )
    assert created == skill_name
```

For the remaining router fixtures that intentionally model registered Workspace packages, replace “write directory then reconcile” setup with `SkillService.create_skill(...)`. Leave Pool fixtures on `reconcile_pool_manifest()` and leave any fixture explicitly testing unmanaged content unregistered.

Implement transition ordering exactly:

```python
# disable
if disabled_dir.exists():
    shutil.rmtree(disabled_dir)
_move_skill_dir(active_dir, disabled_dir)
updated = _mutate_json(manifest_path, _default_workspace_manifest(), _disable)

# enable
_scan_skill_dir_or_raise(disabled_dir, skill_name)
updated = _mutate_json(manifest_path, _default_workspace_manifest(), _enable)
if updated:
    _move_skill_dir(disabled_dir, active_dir)
```

When a post-move manifest write fails during disable, let the next reconciliation restore the still-enabled package to `skills/`. When an enable move fails after the manifest write, return failure and leave reconciliation to complete the enabled state later. Never report success before both operations complete.

- [ ] **Step 4: Run lifecycle, router, scanner, and reload regressions**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/routers/test_skills_tenant_scope.py \
  tests/unit/security/test_skill_scanner_executor.py \
  tests/unit/app/test_skills_stream_trace_scope.py -q
```

Expected: all pass; existing router response contracts and scan-before-enable behavior remain intact.

- [ ] **Step 5: Commit only Task 3 files**

```bash
git add src/swe/agents/skills_manager.py \
  src/swe/app/routers/skills.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/routers/test_skills_tenant_scope.py
git commit --only -m "feat(skills): move packages on enablement changes" \
  src/swe/agents/skills_manager.py \
  src/swe/app/routers/skills.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/routers/test_skills_tenant_scope.py
```

### Task 4: Preserve disabled state across Pool updates and Workspace seeding

**Files:**

- Modify: `src/swe/agents/skills_manager.py:1823-1861,2820-2935`
- Modify: `src/swe/app/workspace/tenant_initializer.py:372-410,1030-1210`
- Modify: `src/swe/app/routers/agents.py:725-810`
- Modify: `src/swe/app/routers/skills.py:302-345`
- Modify: `tests/unit/agents/test_disabled_skill_layout.py`
- Modify: `tests/unit/routers/test_agents_tenant_scope.py`
- Modify: `tests/unit/routers/test_skills_tenant_scope.py`
- Modify: `tests/unit/workspace/test_tenant_skill_seeding.py`

- [ ] **Step 1: Add failing replacement and seeding tests**

```python
# append to tests/unit/agents/test_disabled_skill_layout.py
def test_workspace_replacement_preserves_existing_disabled_state(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "source"
    _write_skill(source, "new-content")
    service = SkillService(workspace)
    service.create_skill("demo", "---\nname: demo\n---\nold\n", enable=False)

    result = service.replace_workspace_skill_from_dir(
        skill_name="demo",
        source_dir=source,
    )

    assert result["success"] is True
    assert service._read_manifest()["skills"]["demo"]["enabled"] is False
    assert "new-content" in (
        workspace / ".disabled_skills" / "demo" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert not (workspace / "skills" / "demo").exists()


def test_router_snapshot_restores_disabled_package_in_hidden_root(
    tmp_path: Path,
) -> None:
    from swe.app.routers.skills import (
        _restore_workspace_skill,
        _snapshot_workspace_skill,
    )

    workspace = tmp_path / "workspace"
    service = SkillService(workspace)
    service.create_skill(
        "demo",
        "---\nname: demo\n---\nbefore\n",
        enable=False,
    )
    snapshot = _snapshot_workspace_skill(workspace, "demo")
    service.save_skill(
        skill_name="demo",
        content="---\nname: demo\n---\nafter\n",
    )

    _restore_workspace_skill(snapshot)

    content = (
        workspace / ".disabled_skills" / "demo" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "before" in content
    assert "after" not in content
    assert not (workspace / "skills" / "demo").exists()
```

```python
# append to TestDefaultWorkspaceSkillSeeding in
# tests/unit/workspace/test_tenant_skill_seeding.py
def test_seed_workspace_skills_preserves_disabled_package(
    self,
    tmp_path: Path,
) -> None:
    default_initializer = TenantInitializer(tmp_path, "default")
    default_initializer.ensure_directory_structure()
    default_workspace = default_initializer.tenant_dir / "workspaces" / "default"
    service = SkillService(default_workspace)
    service.create_skill("hidden-demo", "---\nname: hidden-demo\n---\n", enable=False)

    tenant_initializer = TenantInitializer(tmp_path, "new-tenant")
    tenant_initializer.ensure_directory_structure()
    result = tenant_initializer.seed_default_workspace_skills_from_default()

    assert result["seeded"] is True
    assert "hidden-demo" in result["skills"]
    new_workspace = tenant_initializer.tenant_dir / "workspaces" / "default"
    manifest = read_skill_manifest(new_workspace, reconcile=False)
    assert manifest["skills"]["hidden-demo"]["enabled"] is False
    assert (
        get_workspace_disabled_skills_dir(new_workspace)
        / "hidden-demo"
        / "SKILL.md"
    ).exists()
    assert not (new_workspace / "skills" / "hidden-demo").exists()
```

Add `SkillService`, `get_workspace_disabled_skills_dir`, and `read_skill_manifest` to the existing `swe.agents.skills_manager` import list in that test module.

Add this Agent initialization regression to `test_agents_tenant_scope.py`:

```python
def test_initialize_agent_workspace_registers_requested_pool_skills(
    tmp_path: Path,
) -> None:
    tenant_dir = tmp_path / "tenant"
    workspace = tenant_dir / "workspaces" / "new-agent"
    SkillPoolService(working_dir=tenant_dir).create_skill(
        "guidance",
        "---\nname: guidance\ndescription: Guidance\n---\n",
    )

    agents_router._initialize_agent_workspace(
        workspace,
        SimpleNamespace(language="zh"),
        skill_names=["guidance"],
        working_dir=tenant_dir,
    )

    manifest = read_skill_manifest(workspace, reconcile=False)
    assert manifest["skills"]["guidance"]["enabled"] is True
    assert (workspace / "skills" / "guidance" / "SKILL.md").exists()
```

Import `SkillPoolService` and `read_skill_manifest` from the real `swe.agents.skills_manager` module used by that test harness.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/routers/test_agents_tenant_scope.py \
  tests/unit/workspace/test_tenant_skill_seeding.py -q
```

Expected: replacement re-enables or writes to `skills/`, seeding omits the disabled package, rollback misses hidden content, and Agent initialization copies an unmanaged directory without registering it.

- [ ] **Step 3: Preserve state in replacement and Pool download paths**

In `SkillService.replace_workspace_skill_from_dir()` and `SkillPoolService.download_to_workspace()`:

```python
workspace_manifest = read_skill_manifest(workspace_dir, reconcile=False)
existing = workspace_manifest.get("skills", {}).get(final_name)
enabled = bool(existing.get("enabled", True)) if existing else True
target_dir = resolve_workspace_managed_skill_dir(
    workspace_dir,
    final_name,
    enabled=enabled,
)
channels = (existing.get("channels") or ["all"]) if existing else ["all"]
config_value = (
    (existing.get("config") or {})
    if existing is not None
    else pool_config
)
```

Write updated metadata from `target_dir`, preserve `enabled`, `channels`, and existing config for replacements, and default only genuinely new downloads to enabled.

- [ ] **Step 4: Seed both managed roots from the source manifest**

Change `_prepare_source_workspace_state()` to call `reconcile_workspace_manifest(default_workspace)` first, then read and return a copy of every entry from the reconciled `manifest["skills"]`; do not return early merely because `skills/` is empty.

In `seed_default_workspace_skills_from_default()`:

1. Iterate only the entries returned from the source manifest.
2. For every entry, resolve both source and target with `resolve_workspace_managed_skill_dir(..., enabled=bool(entry.get("enabled", False)))` and copy that one package directory.
3. Build the target from `_default_workspace_manifest()`, assign copied entry dictionaries to `target_manifest["skills"]`, and set `target_manifest["version"] = 1`.
4. Atomically write the target manifest before calling `reconcile_workspace_manifest(target_workspace)`, because v2 reconciliation never registers unmanaged directories from disk.
5. Return the sorted copied manifest names. Preserve `enabled`, `channels`, `config`, `source`, and existing timestamps exactly from each source entry; reconciliation may refresh location-derived metadata but must not change those durable user-state fields.

Remove the now-redundant `_merge_workspace_manifest_state()` call from this seeding flow. Leave the helper itself in place because deleting an existing method is outside this task's scope.

Do not copy unmanaged directories from either root. Update `_has_default_workspace_skills()` to treat a non-empty v2 manifest as initialized without scanning `.disabled_skills/` for unknown content.

- [ ] **Step 5: Register Agent-creation copies and make Pool rollback state-aware**

In `_initialize_agent_workspace()`, replace direct `shutil.copytree(..., workspace / "skills" / name)` plus reconciliation with one `SkillPoolService(working_dir=working_dir).download_to_workspace(name, workspace_dir, overwrite=False)` call per requested name. Raise `RuntimeError` when a requested Pool package returns `success=False`; successful downloads create enabled manifest entries before runtime registration.

In `_snapshot_workspace_skill()`, resolve the backup source from the copied manifest entry's `enabled` flag. In `_restore_workspace_skill()`, remove both possible managed locations, restore the backup to the root selected by the saved entry's `enabled` flag, restore the manifest entry, then reconcile. When the saved entry is absent, remove both locations and keep the entry absent. This preserves disabled content and state when a later target in a multi-Workspace Pool transaction fails.

- [ ] **Step 6: Run Pool, seeding, and initialization regressions**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_tenant_skill_pool_scope.py \
  tests/unit/routers/test_skills_tenant_scope.py \
  tests/unit/workspace/test_tenant_skill_seeding.py \
  tests/unit/workspace/test_tenant_initializer.py \
  tests/unit/routers/test_agents_tenant_scope.py -q
```

Expected: all pass; new Pool installs are enabled, existing disabled replacements remain disabled, and tenant seeding preserves both states.

- [ ] **Step 7: Commit only Task 4 files**

```bash
git add src/swe/agents/skills_manager.py \
  src/swe/app/workspace/tenant_initializer.py \
  src/swe/app/routers/agents.py \
  src/swe/app/routers/skills.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/routers/test_agents_tenant_scope.py \
  tests/unit/routers/test_skills_tenant_scope.py \
  tests/unit/workspace/test_tenant_skill_seeding.py
git commit --only -m "fix(skills): preserve disabled state during distribution" \
  src/swe/agents/skills_manager.py \
  src/swe/app/workspace/tenant_initializer.py \
  src/swe/app/routers/agents.py \
  src/swe/app/routers/skills.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/routers/test_agents_tenant_scope.py \
  tests/unit/routers/test_skills_tenant_scope.py \
  tests/unit/workspace/test_tenant_skill_seeding.py
```

### Task 5: Build the idempotent all-or-nothing migration engine

**Files:**

- Create: `src/swe/agents/workspace_skill_layout_migration.py`
- Create: `tests/unit/agents/test_workspace_skill_layout_migration.py`

- [ ] **Step 1: Write failing preflight and migration tests**

```python
# tests/unit/agents/test_workspace_skill_layout_migration.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

import pytest

from swe.agents.workspace_skill_layout_migration import (
    SkillLayoutMigrationError,
    apply_workspace_skill_layout_migration,
    check_workspace_skill_layout_migration,
)


def _legacy_workspace(root: Path, name: str, *, enabled: bool) -> Path:
    workspace = root / name / "workspaces" / "default"
    skill = workspace / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    (workspace / "skill.json").write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "version": 7,
                "skills": {
                    "demo": {
                        "enabled": enabled,
                        "channels": ["console"],
                        "config": {"token": "kept"},
                    },
                },
            },
        ),
        encoding="utf-8",
    )
    return workspace


def test_check_builds_plan_without_writing(tmp_path: Path) -> None:
    workspace = _legacy_workspace(tmp_path, "default", enabled=False)

    report = check_workspace_skill_layout_migration(tmp_path)

    assert report.success is True
    assert report.workspaces[0].status == "ready"
    assert (workspace / "skill.json").exists()
    assert not (workspace / ".skill_state").exists()
    assert not (workspace / ".disabled_skills").exists()


def test_apply_moves_disabled_packages_and_preserves_manifest_state(
    tmp_path: Path,
) -> None:
    workspace = _legacy_workspace(tmp_path, "default", enabled=False)

    report = apply_workspace_skill_layout_migration(tmp_path)

    assert report.success is True
    assert not (workspace / "skill.json").exists()
    manifest = json.loads(
        (workspace / ".skill_state" / "manifest.json").read_text(
            encoding="utf-8",
        ),
    )
    assert manifest["layout_version"] == 2
    assert manifest["version"] >= 7
    assert manifest["skills"]["demo"]["channels"] == ["console"]
    assert manifest["skills"]["demo"]["config"] == {"token": "kept"}
    assert (workspace / ".disabled_skills" / "demo" / "SKILL.md").exists()
    assert not (workspace / "skills" / "demo").exists()


def test_apply_is_idempotent_after_success(tmp_path: Path) -> None:
    _legacy_workspace(tmp_path, "default", enabled=True)
    apply_workspace_skill_layout_migration(tmp_path)

    report = apply_workspace_skill_layout_migration(tmp_path)

    assert report.success is True
    assert report.workspaces[0].status == "already_migrated"


def test_check_rejects_ambiguous_mixed_layout(tmp_path: Path) -> None:
    workspace = _legacy_workspace(tmp_path, "default", enabled=True)
    state = workspace / ".skill_state"
    state.mkdir()
    (state / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(SkillLayoutMigrationError, match="mixed layout"):
        check_workspace_skill_layout_migration(tmp_path)
```

Add a rollback test that fails the internal second-Workspace apply:

```python
def test_apply_rolls_back_all_workspaces_when_later_workspace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from swe.agents import workspace_skill_layout_migration as migration

    workspaces = [
        _legacy_workspace(tmp_path, "default", enabled=False),
        _legacy_workspace(tmp_path, "tenant-b", enabled=False),
    ]
    original_apply = migration._apply_workspace_migration
    call_count = 0

    def fail_on_second(*args: object, **kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("second workspace failed")
        original_apply(*args, **kwargs)

    monkeypatch.setattr(migration, "_apply_workspace_migration", fail_on_second)

    with pytest.raises(SkillLayoutMigrationError, match="second workspace failed"):
        apply_workspace_skill_layout_migration(tmp_path)

    for workspace in workspaces:
        assert (workspace / "skill.json").exists()
        assert (workspace / "skills" / "demo" / "SKILL.md").exists()
        assert not (workspace / ".skill_state").exists()
        assert not (workspace / ".disabled_skills").exists()
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/agents/test_workspace_skill_layout_migration.py -q
```

Expected: collection fails because `workspace_skill_layout_migration` does not exist.

- [ ] **Step 3: Implement report models, discovery, and read-only preflight**

```python
# src/swe/agents/workspace_skill_layout_migration.py
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .skills_manager import (
    WORKSPACE_SKILL_LAYOUT_VERSION,
    _default_workspace_manifest,
    _write_json_atomic,
    get_legacy_workspace_skill_manifest_path,
    get_workspace_disabled_skills_dir,
    get_workspace_skill_manifest_path,
    get_workspace_skill_state_dir,
    get_workspace_skills_dir,
)


class SkillLayoutMigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkspaceMigrationResult:
    workspace: Path
    status: str


@dataclass(frozen=True)
class SkillLayoutMigrationReport:
    success: bool
    workspaces: tuple[WorkspaceMigrationResult, ...]


def _discover_workspaces(working_dir: Path) -> list[Path]:
    root = Path(working_dir).expanduser()
    if not root.exists():
        return []
    return sorted(
        workspace
        for tenant in root.iterdir()
        if (tenant / "workspaces").is_dir()
        for workspace in (tenant / "workspaces").iterdir()
        if workspace.is_dir()
    )
```

Discovery treats `working_dir` as the release root and scans every `<tenant>/workspaces/<workspace>` directory, so preflight and rollback cover all tenants in one command. Preflight classifies each Workspace as `ready`, `already_migrated`, or invalid. `already_migrated` requires root `skill.json` absent, v2 manifest present, and every registered entry in the directory matching its enablement. `ready` requires legacy manifest present, no v2 manifest, no `.disabled_skills`, valid JSON object entries, and an on-disk `SKILL.md` for every registered package. Any mixed or missing registered state raises `SkillLayoutMigrationError` before writes begin.

- [ ] **Step 4: Implement temporary backups, apply, and rollback**

Implement `_apply_workspace_migration(workspace: Path, payload: dict[str, Any]) -> None` as the only single-Workspace mutator. It must copy the legacy payload, set `layout_version=2`, move each registered disabled directory from `skills/<name>` to `.disabled_skills/<name>`, atomically write `.skill_state/manifest.json`, and unlink `skill.json` last.

For each ready Workspace, copy these relative paths under one `TemporaryDirectory`: `skill.json`, `skills`, `.disabled_skills`, and `.skill_state`. Complete every preflight before creating or moving any Workspace content, then invoke `_apply_workspace_migration` sequentially.

On any exception, remove the four current paths for every Workspace already touched and restore their backups. Re-raise `SkillLayoutMigrationError` only after rollback succeeds; include both migration and rollback errors if restoration fails. Exiting `TemporaryDirectory` removes backups after success.

- [ ] **Step 5: Run migration-engine tests**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/agents/test_workspace_skill_layout_migration.py -q
```

Expected: all preflight, migration, idempotency, ambiguity, rollback, and cleanup tests pass.

- [ ] **Step 6: Commit only Task 5 files**

```bash
git add src/swe/agents/workspace_skill_layout_migration.py \
  tests/unit/agents/test_workspace_skill_layout_migration.py
git commit --only -m "feat(skills): add workspace layout migration engine" \
  src/swe/agents/workspace_skill_layout_migration.py \
  tests/unit/agents/test_workspace_skill_layout_migration.py
```

### Task 6: Expose the deployment-only migration CLI

**Files:**

- Modify: `src/swe/cli/skills_cmd.py:1-270`
- Create: `tests/unit/cli/test_cli_skills_migration.py`

- [ ] **Step 1: Write failing CLI tests**

```python
# tests/unit/cli/test_cli_skills_migration.py
# -*- coding: utf-8 -*-
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from swe.agents.workspace_skill_layout_migration import (
    SkillLayoutMigrationError,
    SkillLayoutMigrationReport,
    WorkspaceMigrationResult,
)
from swe.cli.skills_cmd import skills_group


def _report(path: Path, status: str) -> SkillLayoutMigrationReport:
    return SkillLayoutMigrationReport(
        success=True,
        workspaces=(WorkspaceMigrationResult(path, status),),
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
    assert "choose exactly one of --check or --apply" in missing.output


def test_migrate_layout_check_is_read_only(tmp_path: Path) -> None:
    runner = CliRunner()
    with patch(
        "swe.cli.skills_cmd.check_workspace_skill_layout_migration",
        return_value=_report(tmp_path / "default/workspaces/default", "ready"),
    ) as check, patch(
        "swe.cli.skills_cmd.apply_workspace_skill_layout_migration",
    ) as apply:
        result = runner.invoke(
            skills_group,
            ["migrate-layout", "--check", "--working-dir", str(tmp_path)],
        )

    assert result.exit_code == 0
    check.assert_called_once_with(tmp_path)
    apply.assert_not_called()
    assert "ready" in result.output
```

Add the write-mode and failure-path tests explicitly:

```python
def test_migrate_layout_apply_calls_write_engine(tmp_path: Path) -> None:
    runner = CliRunner()
    with patch(
        "swe.cli.skills_cmd.check_workspace_skill_layout_migration",
    ) as check, patch(
        "swe.cli.skills_cmd.apply_workspace_skill_layout_migration",
        return_value=_report(tmp_path / "default/workspaces/default", "migrated"),
    ) as apply:
        result = runner.invoke(
            skills_group,
            ["migrate-layout", "--apply", "--working-dir", str(tmp_path)],
        )

    assert result.exit_code == 0
    check.assert_not_called()
    apply.assert_called_once_with(tmp_path)
    assert "migrated" in result.output


def test_migrate_layout_reports_engine_error(tmp_path: Path) -> None:
    runner = CliRunner()
    with patch(
        "swe.cli.skills_cmd.check_workspace_skill_layout_migration",
        side_effect=SkillLayoutMigrationError("mixed layout"),
    ):
        result = runner.invoke(
            skills_group,
            ["migrate-layout", "--check", "--working-dir", str(tmp_path)],
        )

    assert result.exit_code != 0
    assert "mixed layout" in result.output
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/cli/test_cli_skills_migration.py -q
```

Expected: Click reports that `migrate-layout` is not a command.

- [ ] **Step 3: Add the Click command**

```python
@skills_group.command("migrate-layout")
@click.option("--check", "check_only", is_flag=True)
@click.option("--apply", "apply_changes", is_flag=True)
@click.option(
    "--working-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=WORKING_DIR,
    show_default=True,
)
def migrate_layout_cmd(
    check_only: bool,
    apply_changes: bool,
    working_dir: Path,
) -> None:
    """Check or migrate Workspace skills to layout v2."""
    if check_only == apply_changes:
        raise click.UsageError("choose exactly one of --check or --apply")
    try:
        report = (
            check_workspace_skill_layout_migration(working_dir)
            if check_only
            else apply_workspace_skill_layout_migration(working_dir)
        )
    except SkillLayoutMigrationError as exc:
        raise click.ClickException(str(exc)) from exc
    for item in report.workspaces:
        click.echo(f"{item.workspace}: {item.status}")
```

Import `SkillLayoutMigrationError`, `apply_workspace_skill_layout_migration`, and `check_workspace_skill_layout_migration` at module scope in `skills_cmd.py`; the migration module uses only the standard library and `skills_manager`, so no conditional import path is needed.

- [ ] **Step 4: Run CLI and existing skills CLI tests**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/cli/test_cli_skills_migration.py \
  tests/unit/workspace/test_cli_agent_id.py \
  tests/unit/cli/test_init_cmd_multi_tenant.py -q
```

Expected: all pass; `skills list` and `skills config` behavior remains unchanged.

- [ ] **Step 5: Commit only Task 6 files**

```bash
git add src/swe/cli/skills_cmd.py tests/unit/cli/test_cli_skills_migration.py
git commit --only -m "feat(cli): add disabled skill layout migration" \
  src/swe/cli/skills_cmd.py \
  tests/unit/cli/test_cli_skills_migration.py
```

### Task 7: Run cross-flow verification and review the final blast radius

**Files:**

- None. This task verifies the files changed in Tasks 1–6.

- [ ] **Step 1: Run formatting and static checks on changed Python files**

```bash
venv/bin/python -m black --check \
  src/swe/agents/skills_manager.py \
  src/swe/agents/skill_invocation_detector.py \
  src/swe/agents/workspace_skill_layout_migration.py \
  src/swe/app/routers/agents.py \
  src/swe/app/routers/skills.py \
  src/swe/app/workspace/tenant_initializer.py \
  src/swe/cli/skills_cmd.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_skill_invocation_detector.py \
  tests/unit/agents/test_workspace_skill_layout_migration.py \
  tests/unit/cli/test_cli_skills_migration.py \
  tests/unit/app/test_runner_session_skill_freshness.py \
  tests/unit/routers/test_agents_tenant_scope.py \
  tests/unit/routers/test_skills_tenant_scope.py
```

Expected: exit code 0.

- [ ] **Step 2: Run the complete skill and Workspace regression slice**

```bash
venv/bin/python -m pytest \
  tests/unit/agents \
  tests/unit/routers/test_skills_tenant_scope.py \
  tests/unit/routers/test_agents_tenant_scope.py \
  tests/unit/workspace/test_tenant_initializer.py \
  tests/unit/workspace/test_tenant_skill_seeding.py \
  tests/unit/workspace/test_cli_agent_id.py \
  tests/unit/cli/test_cli_skills_migration.py \
  tests/unit/app/test_runner_session_skill_freshness.py -q
```

Expected: exit code 0 with no failures.

- [ ] **Step 3: Run GitNexus change detection required by AGENTS.md**

Run GitNexus `detect_changes({scope: "compare", base_ref: "main"})`, then `detect_changes({scope: "staged"})` immediately before any final commit. Review initialization, Agent creation, SkillService router, Pool distribution, hook loading, and tenant seeding processes. Report any HIGH or CRITICAL result before proceeding.

- [ ] **Step 4: Inspect the final diff without disturbing unrelated staged work**

```bash
git status --short
git diff --check
git diff -- src/swe/agents/skills_manager.py \
  src/swe/agents/skill_invocation_detector.py \
  src/swe/agents/workspace_skill_layout_migration.py \
  src/swe/app/routers/agents.py \
  src/swe/app/routers/skills.py \
  src/swe/app/workspace/tenant_initializer.py \
  src/swe/cli/skills_cmd.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_skill_invocation_detector.py \
  tests/unit/agents/test_workspace_skill_layout_migration.py \
  tests/unit/cli/test_cli_skills_migration.py \
  tests/unit/app/test_runner_session_skill_freshness.py \
  tests/unit/routers/test_agents_tenant_scope.py \
  tests/unit/routers/test_skills_tenant_scope.py
```

Expected: only planned task files plus the pre-existing staged `tests/unit/app/test_runtime_diagnostic.py`; no whitespace errors or unrelated edits.
