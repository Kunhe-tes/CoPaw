# Retain Workspace skill.json Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `workspace/skill.json` as the single writable Workspace skill manifest while retaining `.disabled_skills/<name>` for registered disabled packages and an explicit layout version.

**Architecture:** Restore the Workspace manifest helper in Swe and Market to `workspace/skill.json`; every runtime, management, seeding, and distribution path continues to consume that shared helper. Rework the deployment-only migration engine so it moves registered disabled packages and updates `layout_version` in the existing file without creating `.skill_state/manifest.json`. External-service edits are preserved by the existing registered-only reconciliation contract; cross-service concurrent-write coordination remains out of scope.

**Tech Stack:** Python 3.10+, Click, pathlib/shutil/tempfile, existing JSON file locks and atomic writes, pytest

---

## Risk and file map

GitNexus reports **CRITICAL** upstream impact for `get_workspace_skill_manifest_path`: 19 direct dependents, 157 total affected symbols, three affected process groups (`init_cmd`, `create_agent`, and skill configuration deletion), and five modules. The user approved this revised design after the warning. Before the first implementation edit, run fresh upstream impact for `get_workspace_skill_manifest_path`, `get_workspace_skill_state_dir`, `get_legacy_workspace_skill_manifest_path`, Market's `get_workspace_skill_manifest_path`, `SkillInvocationDetector.set_enabled_skills`, `_preflight_workspace`, and `_apply_workspace_migration`. Report any newly discovered HIGH or CRITICAL surface before editing.

Every commit must follow the repository gate: stage only the task files, run GitNexus `detect_changes({scope: "staged"})`, review the listed symbols and processes, and then commit with `git commit --only`. The pre-existing staged `tests/unit/app/test_runtime_diagnostic.py` belongs to the user and must never be modified or included in these commits.

**Modify:**

- `src/swe/agents/skills_manager.py` — restore the Workspace manifest path and remove obsolete v2-path helpers.
- `src/swe/agents/skill_invocation_detector.py` — document the shared `skill.json` setup-time metadata source.
- `src/swe/agents/workspace_skill_layout_migration.py` — perform in-place layout v2 migration.
- `src/swe/app/migration.py` — correct the Workspace manifest path comment.
- `market/src/market/marketplace/fs.py` — keep Market's Workspace path contract aligned with Swe.
- `market/src/market/marketplace/service.py` — correct Workspace manifest documentation.
- `market/src/market/app/routers/skills_browse.py` — correct Workspace manifest documentation.
- `tests/unit/agents/test_disabled_skill_layout.py` — path and external-writer reconciliation coverage.
- `tests/unit/agents/test_workspace_skill_layout_migration.py` — in-place migration and rollback coverage.
- `market/tests/unit/marketplace/test_fs.py` — shared path contract.
- `market/tests/unit/marketplace/test_skills_market.py` — Market manifest writes remain at `skill.json`.

No new production module is required. Do not change ordinary shell, glob, file search, File Guardian, Agent reload, or Pool manifest behavior.

### Task 1: Restore the shared Workspace manifest path

**Files:**

- Modify: `src/swe/agents/skills_manager.py:211-229,1850-1865`
- Modify: `src/swe/agents/skill_invocation_detector.py:257-265`
- Modify: `src/swe/app/migration.py:560-570`
- Modify: `market/src/market/marketplace/fs.py:446-480`
- Modify: `market/src/market/marketplace/service.py:2408-2415`
- Modify: `market/src/market/app/routers/skills_browse.py:1930-1938`
- Modify: `tests/unit/agents/test_disabled_skill_layout.py:9-100`
- Modify: `market/tests/unit/marketplace/test_fs.py:70-105`
- Modify: `market/tests/unit/marketplace/test_skills_market.py`

- [ ] **Step 1: Run the required upstream impact checks and report the CRITICAL helper blast radius**

Run GitNexus upstream impact for the seven symbols listed in the risk section. Use `summaryOnly: true` first for hubs, then inspect depth 1 for `get_workspace_skill_manifest_path`. Confirm that no newly affected process is outside initialization, Agent creation, Workspace skill management, Market distribution, and migration.

- [ ] **Step 2: Change the path contract tests first**

In `tests/unit/agents/test_disabled_skill_layout.py`, remove imports and assertions for `get_workspace_skill_state_dir` and `get_legacy_workspace_skill_manifest_path`, then make the path test assert the retained manifest:

```python
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
```

In `market/tests/unit/marketplace/test_fs.py`, update the explicit contract assertion:

```python
assert market_manifest_path == workspace_dir / "skill.json"
assert market_manifest_path == get_workspace_skill_manifest_path(workspace_dir)
```

Add or update the Market write assertion in `market/tests/unit/marketplace/test_skills_market.py` so distribution metadata is written to `workspace/skill.json` and `.skill_state/manifest.json` remains absent.

- [ ] **Step 3: Run the path tests and verify RED**

Run:

```bash
PYTHONPATH=src:market/src ../../venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py::test_workspace_skill_layout_paths \
  market/tests/unit/marketplace/test_fs.py::test_user_manifest_path_matches_swe_workspace_contract \
  market/tests/unit/marketplace/test_skills_market.py -q
```

Expected: the Swe and Market path assertions fail because both helpers still return `.skill_state/manifest.json`.

- [ ] **Step 4: Restore the Swe and Market path helpers**

In `src/swe/agents/skills_manager.py`, use the existing path as the only Workspace manifest helper and remove the two obsolete helper functions:

```python
def get_workspace_skill_manifest_path(workspace_dir: Path) -> Path:
    """Return the shared writable Workspace skill manifest path."""
    return Path(workspace_dir) / "skill.json"


def get_workspace_disabled_skills_dir(workspace_dir: Path) -> Path:
    """Return the workspace disabled skill directory."""
    return Path(workspace_dir) / ".disabled_skills"
```

Remove `get_workspace_skill_state_dir()` and `get_legacy_workspace_skill_manifest_path()`; the migration module will use an internal obsolete-path constant in Task 3. Update the `SkillService` examples and `SkillInvocationDetector.set_enabled_skills()` docstring to name `skill.json`.

In `market/src/market/marketplace/fs.py`:

```python
def get_workspace_skill_manifest_path(workspace_dir: Path) -> Path:
    """Return the shared writable Workspace skill manifest path."""
    return Path(workspace_dir) / "skill.json"
```

Update the Market service/router docstrings and the comment in `src/swe/app/migration.py` to say `workspace/skill.json`. Do not change per-package Market `skill.json` or `skill_pool/skill.json` behavior.

- [ ] **Step 5: Run focused runtime and Market regressions**

Run:

```bash
PYTHONPATH=src:market/src ../../venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_skill_invocation_detector.py \
  tests/unit/app/test_runner_session_skill_freshness.py \
  market/tests/unit/marketplace/test_fs.py \
  market/tests/unit/marketplace/test_skills_market.py -q
```

Expected: all tests pass and no fixture creates `.skill_state/manifest.json`.

- [ ] **Step 6: Stage, detect changes, and commit Task 1 only**

```bash
git add src/swe/agents/skills_manager.py \
  src/swe/agents/skill_invocation_detector.py \
  src/swe/app/migration.py \
  market/src/market/marketplace/fs.py \
  market/src/market/marketplace/service.py \
  market/src/market/app/routers/skills_browse.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  market/tests/unit/marketplace/test_fs.py \
  market/tests/unit/marketplace/test_skills_market.py
```

Run GitNexus `detect_changes({scope: "staged"})`, then:

```bash
git commit --only -m "refactor(skills): retain workspace skill manifest path" \
  src/swe/agents/skills_manager.py \
  src/swe/agents/skill_invocation_detector.py \
  src/swe/app/migration.py \
  market/src/market/marketplace/fs.py \
  market/src/market/marketplace/service.py \
  market/src/market/app/routers/skills_browse.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  market/tests/unit/marketplace/test_fs.py \
  market/tests/unit/marketplace/test_skills_market.py
```

### Task 2: Preserve external-service edits during reconciliation

**Files:**

- Modify: `tests/unit/agents/test_disabled_skill_layout.py`
- Modify only if the new regression fails: `src/swe/agents/skills_manager.py:1385-1480`

- [ ] **Step 1: Add a regression that models the external service contract**

Append a test that writes through the shared JSON contract without calling CoPaw APIs:

```python
def test_reconcile_preserves_external_manifest_edits_and_moves_package(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    disabled = workspace / ".disabled_skills" / "demo"
    active = workspace / "skills" / "demo"
    _write_skill(disabled, "disabled-copy")
    _write_manifest(workspace, {"demo": _entry(enabled=False)})

    manifest_path = workspace / "skill.json"
    external_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    external_payload["external_manifest_field"] = {"kept": True}
    external_payload["skills"]["demo"]["enabled"] = True
    external_payload["skills"]["demo"]["config"] = {"token": "external"}
    external_payload["skills"]["demo"].setdefault("metadata", {})[
        "external_note"
    ] = "preserved"
    manifest_path.write_text(
        json.dumps(external_payload, indent=2),
        encoding="utf-8",
    )

    reconciled = reconcile_workspace_manifest(workspace)

    assert active.exists()
    assert not disabled.exists()
    assert reconciled["external_manifest_field"] == {"kept": True}
    assert reconciled["skills"]["demo"]["enabled"] is True
    assert reconciled["skills"]["demo"]["config"] == {
        "token": "external",
    }
    assert reconciled["skills"]["demo"]["metadata"]["external_note"] == (
        "preserved"
    )
```

This test intentionally covers unknown metadata. Existing CoPaw-computed metadata such as the name, description, source, and requirements keep their current refresh semantics.

- [ ] **Step 2: Run the regression**

Run:

```bash
PYTHONPATH=src ../../venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py::test_reconcile_preserves_external_manifest_edits_and_moves_package -q
```

Expected: PASS using registered-only reconciliation. If it fails, make the minimum change in `_merge_existing_metadata()` or the reconciliation entry construction necessary to preserve unknown external keys without stopping the refresh of CoPaw-computed keys.

- [ ] **Step 3: Run lifecycle, router, and seeding regressions**

Run:

```bash
PYTHONPATH=src ../../venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/routers/test_skills_tenant_scope.py \
  tests/unit/routers/test_agents_tenant_scope.py \
  tests/unit/workspace/test_tenant_initializer.py \
  tests/unit/workspace/test_tenant_skill_seeding.py -q
```

Expected: all tests pass; external edits remain in `skill.json`, and enablement-driven directory moves remain unchanged.

- [ ] **Step 4: Stage, detect changes, and commit Task 2 only**

```bash
git add tests/unit/agents/test_disabled_skill_layout.py
```

If production code was required, also stage `src/swe/agents/skills_manager.py`. Run GitNexus `detect_changes({scope: "staged"})`, then commit only the paths actually changed:

```bash
git commit --only -m "test(skills): preserve external manifest updates" \
  tests/unit/agents/test_disabled_skill_layout.py
```

If `skills_manager.py` changed, include it explicitly in the same `--only` commit.

### Task 3: Migrate layout v2 in place

**Files:**

- Modify: `src/swe/agents/workspace_skill_layout_migration.py`
- Modify: `tests/unit/agents/test_workspace_skill_layout_migration.py`
- Regression: `tests/unit/cli/test_cli_skills_migration.py`

- [ ] **Step 1: Rewrite the migration fixtures around one manifest path**

Replace `_legacy_workspace` with `_workspace` and make `layout_version` optional. Replace `_write_v2_manifest` with an in-place helper:

```python
def _workspace(
    root: Path,
    tenant: str,
    *,
    workspace_name: str = "default",
    skills: dict[str, dict[str, Any]] | None = None,
    layout_version: int | None = None,
) -> Path:
    workspace = root / tenant / "workspaces" / workspace_name
    entries = skills or {
        "demo": {
            "enabled": False,
            "channels": ["console"],
            "config": {"token": "kept"},
            "custom_entry_field": {"kept": True},
        },
    }
    for skill_name in entries:
        _write_skill(workspace / "skills" / skill_name)
    payload: dict[str, Any] = {
        "schema_version": "workspace-skill-manifest.v1",
        "version": 7,
        "custom_manifest_field": ["kept"],
        "skills": entries,
    }
    if layout_version is not None:
        payload["layout_version"] = layout_version
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "skill.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return workspace
```

For already-migrated fixtures, create enabled packages in `skills/`, disabled packages in `.disabled_skills/`, and write `layout_version=2` to the same `skill.json`.

- [ ] **Step 2: Change the migration expectations and verify RED**

Update the success test to assert in-place behavior:

```python
def test_apply_moves_disabled_and_updates_manifest_in_place(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path, "tenant-a")
    manifest_path = workspace / "skill.json"

    report = apply_workspace_skill_layout_migration(tmp_path)

    assert report.workspaces[0].status == "migrated"
    assert manifest_path.exists()
    assert not (workspace / ".skill_state").exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["layout_version"] == 2
    assert manifest["version"] == 7
    assert manifest["custom_manifest_field"] == ["kept"]
    assert manifest["skills"]["demo"]["config"] == {"token": "kept"}
    assert (workspace / ".disabled_skills" / "demo" / "SKILL.md").exists()
    assert not (workspace / "skills" / "demo").exists()
```

Add a mixed-state test that creates `.skill_state/manifest.json` beside `skill.json` and expects `SkillLayoutMigrationError` without any writes. Remove the old assertion that `.skill_state/notes.txt` is part of the migrated state; an unrelated `.skill_state` directory without `manifest.json` is not created, modified, or backed up by this CLI.

Run:

```bash
PYTHONPATH=src ../../venv/bin/python -m pytest \
  tests/unit/agents/test_workspace_skill_layout_migration.py -q
```

Expected: failures show that the engine still writes `.skill_state/manifest.json` and unlinks `skill.json`.

- [ ] **Step 3: Refactor preflight to classify the in-place manifest**

In `workspace_skill_layout_migration.py`, remove imports of the deleted state/legacy helpers and add an internal obsolete-path constant:

```python
_OBSOLETE_V2_MANIFEST = Path(".skill_state") / "manifest.json"
_BACKUP_PATHS = (
    "skill.json",
    "skills",
    ".disabled_skills",
)
```

In `_preflight_workspace`:

```python
manifest = get_workspace_skill_manifest_path(workspace)
obsolete_state_root = workspace / ".skill_state"
obsolete_manifest = workspace / _OBSOLETE_V2_MANIFEST
disabled_root = get_workspace_disabled_skills_dir(workspace)
active_root = workspace / "skills"

_reject_symbolic_link(active_root, "active skills root")
_reject_symbolic_link(disabled_root, "disabled skills root")
_reject_symbolic_link(manifest, "Workspace skill manifest")
_reject_symbolic_link(obsolete_state_root, "obsolete skill state root")
_reject_symbolic_link(obsolete_manifest, "obsolete v2 skill manifest")

if obsolete_manifest.exists() or obsolete_manifest.is_symlink():
    raise SkillLayoutMigrationError(
        f"Workspace {workspace} has mixed layout: unexpected "
        ".skill_state/manifest.json",
    )
if not manifest.exists():
    if disabled_root.exists():
        raise SkillLayoutMigrationError(
            f"Workspace {workspace} has invalid partial skill layout state",
        )
    return _WorkspaceMigrationPlan(workspace, "not_applicable")

payload = _read_manifest(manifest)
if payload.get("layout_version") == WORKSPACE_SKILL_LAYOUT_VERSION:
    _validate_migrated_workspace(workspace, payload)
    return _WorkspaceMigrationPlan(workspace, "already_migrated", payload)
if disabled_root.exists():
    raise SkillLayoutMigrationError(
        f"Workspace {workspace} has mixed layout: pre-v2 manifest exists "
        "with the disabled skill root",
    )
_validate_ready_workspace(workspace, payload)
return _WorkspaceMigrationPlan(workspace, "ready", payload)
```

Reject unsupported non-null layout versions instead of treating them as v1. A missing `layout_version` is the only legacy-ready form.

- [ ] **Step 4: Write the upgraded payload back to the same file**

Finish `_apply_workspace_migration` with:

```python
_write_manifest_atomic(
    get_workspace_skill_manifest_path(workspace),
    migrated_payload,
)
```

Remove the legacy-manifest unlink. Keep the existing all-Workspace preflight, temporary backups, exact reverse-order rollback, rollback-error reporting, and temporary-directory cleanup.

- [ ] **Step 5: Run migration engine and CLI regressions**

Run:

```bash
PYTHONPATH=src ../../venv/bin/python -m pytest \
  tests/unit/agents/test_workspace_skill_layout_migration.py \
  tests/unit/cli/test_cli_skills_migration.py -q
```

Expected: all migration and CLI tests pass, successful workspaces retain `skill.json`, and no test creates `.skill_state/manifest.json` except the explicit mixed-layout rejection fixture.

- [ ] **Step 6: Stage, detect changes, and commit Task 3 only**

```bash
git add src/swe/agents/workspace_skill_layout_migration.py \
  tests/unit/agents/test_workspace_skill_layout_migration.py
```

Run GitNexus `detect_changes({scope: "staged"})`, then:

```bash
git commit --only -m "fix(skills): migrate workspace manifest in place" \
  src/swe/agents/workspace_skill_layout_migration.py \
  tests/unit/agents/test_workspace_skill_layout_migration.py
```

### Task 4: Cross-flow verification and final review

**Files:**

- None. This task verifies Tasks 1-3.

- [ ] **Step 1: Confirm no production path points Workspace state at `.skill_state`**

Run:

```bash
rg -n '\.skill_state/manifest\.json|get_workspace_skill_state_dir|get_legacy_workspace_skill_manifest_path' \
  src/swe market/src
```

Expected: only the migration engine's obsolete mixed-layout rejection constant/message and explanatory migration documentation may mention `.skill_state/manifest.json`; no runtime or Market path helper returns it.

- [ ] **Step 2: Run formatting checks on every changed Python file**

```bash
../../venv/bin/python -m black --check --line-length=79 \
  src/swe/agents/skills_manager.py \
  src/swe/agents/skill_invocation_detector.py \
  src/swe/agents/workspace_skill_layout_migration.py \
  src/swe/app/migration.py \
  market/src/market/marketplace/fs.py \
  market/src/market/marketplace/service.py \
  market/src/market/app/routers/skills_browse.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_workspace_skill_layout_migration.py \
  market/tests/unit/marketplace/test_fs.py \
  market/tests/unit/marketplace/test_skills_market.py
```

Expected: all files are unchanged.

- [ ] **Step 3: Run the full affected regression slice**

```bash
PYTHONPATH=src:market/src ../../venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_skill_invocation_detector.py \
  tests/unit/agents/test_utf8_skill_cleanup.py \
  tests/unit/agents/test_workspace_skill_layout_migration.py \
  tests/unit/agents/test_tenant_skill_pool_scope.py \
  tests/unit/routers/test_skills_tenant_scope.py \
  tests/unit/routers/test_agents_tenant_scope.py \
  tests/unit/workspace/test_tenant_initializer.py \
  tests/unit/workspace/test_tenant_skill_seeding.py \
  tests/unit/workspace/test_cli_agent_id.py \
  tests/unit/cli/test_cli_skills_migration.py \
  tests/unit/app/test_runner_session_skill_freshness.py \
  market/tests/unit/marketplace/test_fs.py \
  market/tests/unit/marketplace/test_skills_market.py -q
```

Expected: exit code 0. This slice covers Workspace runtime state, external-edit reconciliation, Market, Pool, Agent creation, routers, tenant seeding, CLI migration, and session skill refresh.

- [ ] **Step 4: Review GitNexus and the final worktree**

Run GitNexus:

```text
detect_changes({scope: "compare", base_ref: "fbf754211"})
detect_changes({scope: "staged"})
```

Review the initialization, Agent creation, skill management, Market distribution, Pool distribution, tenant seeding, runtime registration, and migration surfaces. The staged report may include the user's pre-existing `tests/unit/app/test_runtime_diagnostic.py`; it must not appear in any task commit.

Then run:

```bash
git status --short
git diff --check
git diff --cached --check
```

Expected: no task-related uncommitted change remains; only the user's staged `tests/unit/app/test_runtime_diagnostic.py` may remain.
