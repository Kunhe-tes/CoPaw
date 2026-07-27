# Resumable Skill Layout Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prune missing registered legacy skills and migrate Workspace skill layouts without full-workspace backups or rollback, while allowing a failed run to resume.

**Architecture:** Preflight will build a normalized legacy manifest and accept a disabled package that was already moved by a prior interrupted run. The apply path will make only the necessary moves, atomically replace `skill.json`, and stop on the first failed Workspace; no backup data is materialized and completed Workspaces are retained.

**Tech Stack:** Python 3.10+, `pathlib`, `json`, `tempfile`, Click, pytest.

---

## File map

- `src/swe/agents/workspace_skill_layout_migration.py` — remove backup/restore machinery; normalize stale registrations; validate and apply resumable legacy state.
- `tests/unit/agents/test_workspace_skill_layout_migration.py` — replace rollback/backup assertions with pruning, stop-on-error, and resume regression tests.
- `docs/superpowers/specs/2026-07-15-disabled-skill-discovery-suppression-design.md` — align the historical migration-contract section with no-backup, no-rollback operation.

### Task 1: Define cleanup and resume behavior in tests

**Files:**

- Modify: `tests/unit/agents/test_workspace_skill_layout_migration.py:359-504, 650-1410`

- [ ] **Step 1: Write the failing stale-registration tests**

Replace `test_check_rejects_missing_registered_skill_document` with these tests:

```python
def test_check_allows_missing_registered_skill_document_without_writing(
    tmp_path: Path,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    manifest_path = workspace / "skill.json"
    before = manifest_path.read_bytes()
    (workspace / "skills" / "demo" / "SKILL.md").unlink()

    report = check_workspace_skill_layout_migration(tmp_path)

    assert report.workspaces[0].status == "ready"
    assert manifest_path.read_bytes() == before


def test_apply_prunes_missing_registered_skill_document(
    tmp_path: Path,
) -> None:
    workspace = _legacy_workspace(
        tmp_path,
        "tenant-a",
        skills={
            "retained": {"enabled": True},
            "summarize": {"enabled": False},
        },
    )
    (workspace / "skills" / "summarize" / "SKILL.md").unlink()

    apply_workspace_skill_layout_migration(tmp_path)

    manifest = json.loads((workspace / "skill.json").read_text())
    assert manifest["layout_version"] == 2
    assert set(manifest["skills"]) == {"retained"}
    assert (workspace / "skills" / "retained" / "SKILL.md").is_file()
```

- [ ] **Step 2: Run the stale-registration tests and verify RED**

Run:

```bash
../../venv/bin/python -m pytest \
  tests/unit/agents/test_workspace_skill_layout_migration.py \
  -k 'missing_registered_skill_document' -q
```

Expected: `test_check_allows...` fails with `SkillLayoutMigrationError`, proving the current preflight rejects the stale entry.

- [ ] **Step 3: Write the failing no-rollback and resume tests**

Replace `test_apply_rolls_back_all_attempted_workspaces_exactly` with:

```python
def test_apply_stops_without_rolling_back_completed_workspaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _legacy_workspace(tmp_path, "tenant-a")
    second = _legacy_workspace(tmp_path, "tenant-b")
    original_apply = migration._apply_workspace_migration

    def fail_second(workspace: Path, payload: dict[str, Any]) -> None:
        if workspace == second:
            raise OSError("second workspace failed")
        original_apply(workspace, payload)

    monkeypatch.setattr(migration, "_apply_workspace_migration", fail_second)

    with pytest.raises(SkillLayoutMigrationError, match="second workspace failed"):
        apply_workspace_skill_layout_migration(tmp_path)

    assert json.loads((first / "skill.json").read_text())["layout_version"] == 2
    assert "layout_version" not in json.loads((second / "skill.json").read_text())


def test_apply_resumes_legacy_workspace_after_disabled_package_was_moved(
    tmp_path: Path,
) -> None:
    workspace = _legacy_workspace(
        tmp_path,
        "tenant-a",
        skills={"demo": {"enabled": False}},
    )
    (workspace / ".disabled_skills").mkdir()
    (workspace / "skills" / "demo").replace(
        workspace / ".disabled_skills" / "demo",
    )

    report = apply_workspace_skill_layout_migration(tmp_path)

    assert report.workspaces[0].status == "migrated"
    assert json.loads((workspace / "skill.json").read_text())["layout_version"] == 2
    assert (workspace / ".disabled_skills" / "demo" / "SKILL.md").is_file()
```

Delete all tests whose sole purpose is backup copying, identity restoration, rollback-error composition, or temporary-backup cleanup (`test_rollback_*`, `test_restore_*`, `test_temporary_backup_*`, and their support assertions).

- [ ] **Step 4: Run the no-rollback and resume tests and verify RED**

Run:

```bash
../../venv/bin/python -m pytest \
  tests/unit/agents/test_workspace_skill_layout_migration.py \
  -k 'stops_without_rolling_back or resumes_legacy_workspace' -q
```

Expected: the no-rollback assertion fails because the current engine restores `first`; the resume test fails because the current preflight rejects `.disabled_skills` with a legacy manifest.

### Task 2: Implement normalized, resumable legacy preflight

**Files:**

- Modify: `src/swe/agents/workspace_skill_layout_migration.py:43-55, 359-511`

- [ ] **Step 1: Add a normalized legacy-payload helper**

Add `_normalize_legacy_payload(workspace, payload)` next to `_validate_ready_workspace`. It must deep-copy the payload; iterate each `payload["skills"]` entry; reject symlinked active/disabled packages and documents; preserve entries whose document exists in their permitted location; and remove an entry only when neither managed root has a regular `SKILL.md` file. For `enabled=True`, require the active document. For disabled entries, accept exactly one of active or disabled documents, and reject both roots.

```python
def _normalize_legacy_payload(
    workspace: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(payload)
    active_root = workspace / "skills"
    disabled_root = get_workspace_disabled_skills_dir(workspace)
    for skill_name, entry in list(normalized["skills"].items()):
        active = active_root / skill_name
        disabled = disabled_root / skill_name
        for package, document, description in (
            (active, active / "SKILL.md", "registered active skill"),
            (disabled, disabled / "SKILL.md", "registered disabled skill"),
        ):
            _reject_symbolic_link(package, f"{description} package")
            _reject_symbolic_link(document, f"{description} document")
        active_exists = (active / "SKILL.md").is_file()
        disabled_exists = (disabled / "SKILL.md").is_file()
        if not active_exists and not disabled_exists:
            del normalized["skills"][skill_name]
        elif active_exists and disabled_exists:
            raise SkillLayoutMigrationError(
                f"Workspace {workspace} has ambiguous registered skill "
                f"{skill_name!r} in both managed roots",
            )
        elif entry.get("enabled", False) is True and not active_exists:
            raise SkillLayoutMigrationError(
                f"Workspace {workspace} registered enabled skill "
                f"{skill_name!r} is missing from the active root",
            )
    return normalized
```

Use the normalized payload in `_preflight_workspace` for a manifest without `layout_version`. Do not reject an existing `.disabled_skills` root merely because the manifest is legacy. Require write/execute access only for roots that the remaining normalized plan can modify. Keep the existing v2 validator unchanged so malformed completed layouts remain errors.

- [ ] **Step 2: Run Task 1 tests and verify GREEN for preflight**

Run:

```bash
../../venv/bin/python -m pytest \
  tests/unit/agents/test_workspace_skill_layout_migration.py \
  -k 'missing_registered_skill_document or resumes_legacy_workspace' -q
```

Expected: check is read-only and both stale-entry/resume preflight tests pass; the apply-pruning test may still fail until Task 3.

### Task 3: Remove backup/rollback implementation and make application idempotent

**Files:**

- Modify: `src/swe/agents/workspace_skill_layout_migration.py:1-80, 547-855`
- Test: `tests/unit/agents/test_workspace_skill_layout_migration.py`

- [ ] **Step 1: Remove backup-only production code**

Delete `SkillLayoutMigrationRollbackError`, `_PathIdentity`, `_WorkspaceBackup`, `_BACKUP_PATHS`, backup-readability checks, `_copy_backup_path`, `_capture_path_identities`, `_backup_workspace`, `_remove_path`, `_restore_symlink_mode`, `_restore_path_identity`, and `_restore_workspace_backup`. Retain `_write_manifest_atomic`, including its file-mode and owner preservation.

- [ ] **Step 2: Make one Workspace migration resume-safe**

In `_apply_workspace_migration`, begin from the normalized payload. For each remaining disabled entry, move `skills/<name>` only if it exists; if `.disabled_skills/<name>` already exists, leave it in place. After all required moves, set `layout_version` and atomically write `skill.json`. This ensures an interruption after a prior move can be resumed without copying data or moving a package twice.

```python
def _apply_workspace_migration(
    workspace: Path,
    payload: dict[str, Any],
) -> None:
    migrated_payload = copy.deepcopy(payload)
    active_root = workspace / "skills"
    disabled_root = get_workspace_disabled_skills_dir(workspace)
    for skill_name, entry in migrated_payload["skills"].items():
        if entry.get("enabled", False) is True:
            continue
        source = active_root / skill_name
        target = disabled_root / skill_name
        if (target / "SKILL.md").is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)
    migrated_payload["layout_version"] = WORKSPACE_SKILL_LAYOUT_VERSION
    _write_manifest_atomic(
        get_workspace_skill_manifest_path(workspace),
        migrated_payload,
    )
```

- [ ] **Step 3: Replace release-wide atomic apply with stop-on-error apply**

Replace the `TemporaryDirectory`/backup/restore block in `apply_workspace_skill_layout_migration` with a single ordered loop over `ready` plans. On the first exception, wrap it as `SkillLayoutMigrationError("Workspace skill layout migration failed: ...")` and return nonzero without modifying earlier successful Workspaces. On success, report `migrated` for ready plans and preserve other statuses.

```python
try:
    for plan in ready:
        if plan.payload is None:  # pragma: no cover - invariant
            raise SkillLayoutMigrationError(
                f"Missing preflight payload for {plan.workspace}",
            )
        _apply_workspace_migration(plan.workspace, plan.payload)
except Exception as exc:
    if isinstance(exc, SkillLayoutMigrationError):
        raise
    raise SkillLayoutMigrationError(
        f"Workspace skill layout migration failed: {exc}",
    ) from exc
```

- [ ] **Step 4: Run focused migration tests and verify GREEN**

Run:

```bash
../../venv/bin/python -m pytest \
  tests/unit/agents/test_workspace_skill_layout_migration.py -q
```

Expected: all migration tests pass; no remaining test imports or references backup/rollback helper names.

### Task 4: Update the migration contract and run regressions

**Files:**

- Modify: `docs/superpowers/specs/2026-07-15-disabled-skill-discovery-suppression-design.md:77-101`
- Modify: `docs/superpowers/plans/2026-07-27-resumable-skill-layout-migration.md`

- [ ] **Step 1: Update the prior design’s migration paragraph**

Replace its all-or-nothing/temporary-backup wording with: missing registered documents are pruned during apply; processing stops on the first failed Workspace; successful Workspaces are retained; the next invocation resumes from the materialized directory state; only the manifest’s atomic replacement is temporary.

- [ ] **Step 2: Run focused CLI and migration regressions**

Run:

```bash
../../venv/bin/python -m pytest \
  tests/unit/cli/test_cli_skills_migration.py \
  tests/unit/agents/test_workspace_skill_layout_migration.py -q
```

Expected: PASS.

- [ ] **Step 3: Inspect the change scope before committing**

Run GitNexus `detect_changes` with `scope: "all"` and this worktree path. Confirm only migration implementation, migration tests, and migration documentation are affected; investigate any unexpected process or symbol before staging.

- [ ] **Step 4: Commit only the implementation files**

```bash
git add src/swe/agents/workspace_skill_layout_migration.py \
  tests/unit/agents/test_workspace_skill_layout_migration.py \
  docs/superpowers/specs/2026-07-15-disabled-skill-discovery-suppression-design.md \
  docs/superpowers/plans/2026-07-27-resumable-skill-layout-migration.md
git commit --only -m "refactor(skills): make layout migration resumable" -- \
  src/swe/agents/workspace_skill_layout_migration.py \
  tests/unit/agents/test_workspace_skill_layout_migration.py \
  docs/superpowers/specs/2026-07-15-disabled-skill-discovery-suppression-design.md \
  docs/superpowers/plans/2026-07-27-resumable-skill-layout-migration.md
```
