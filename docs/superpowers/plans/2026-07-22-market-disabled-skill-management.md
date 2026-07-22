# Market Disabled-Skill Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Market manage registered disabled Workspace skills from `.disabled_skills/` without changing Market's shared-manifest and best-effort-reload boundary.

**Architecture:** Keep `workspace/skill.json` as the only state file. Add Market-local helpers that validate a pre-existing v2 manifest and resolve a registered package across `skills/` and `.disabled_skills/`; mutation paths use those helpers before touching package files. SWE reconciliation owns the default active-collision promotion, while Market mutating management paths apply the same rule; Market continues to show and maintain ordinary unmanaged active-directory content until an explicit enable claims it.

**Tech Stack:** Python 3.10+, FastAPI, pathlib/shutil, pytest, existing atomic JSON writes and SWE file lock.

---

## File map

- `src/swe/agents/skills_manager.py` — reconcile the active/disabled same-name collision by preserving `skills/<name>` and promoting its registered entry to enabled.
- `market/src/market/marketplace/fs.py` — centralize Market's disabled-root path, v2 manifest validation, strict mutation read, and registered package resolution.
- `market/src/market/marketplace/service.py` — route lifecycle, distribution, maintenance, deletion, recall, migration, and reload decisions through the resolver.
- `market/src/market/app/routers/skills_browse.py` — remove router-level `skills/<name>` assumptions for download/upload conflict handling.
- `tests/unit/agents/test_disabled_skill_layout.py` — update SWE collision behavior coverage.
- `market/tests/unit/marketplace/test_fs.py` — test v2 validation, strict preflight, and both-root resolution.
- `market/tests/unit/marketplace/test_service.py` — test Market list, enable/disable, maintenance, deletion, distribution, recall, migration, and reload behavior.
- `market/tests/unit/marketplace/test_skills_browse.py` — test upload/download handling for disabled and unmanaged packages.
- `CONTEXT.md`, `docs/adr/0012-disabled-skills-move-outside-runtime-skill-path.md`, `docs/superpowers/specs/2026-07-15-disabled-skill-discovery-suppression-design.md` — already updated during the design session; retain them in the first documentation commit.

### Task 1: Commit the agreed terminology and decision record

**Files:**

- Modify: `CONTEXT.md`
- Modify: `docs/adr/0012-disabled-skills-move-outside-runtime-skill-path.md`
- Modify: `docs/superpowers/specs/2026-07-15-disabled-skill-discovery-suppression-design.md`
- Create: `docs/superpowers/plans/2026-07-22-market-disabled-skill-management.md`

- [ ] **Step 1: Review the documentation against the approved decisions**

Confirm it states all of the following: v2-only Market mutations; registered-package dual-root resolution; state-preserving distribution; disabled maintenance; deletion restriction for registered skills; legacy unmanaged handling; active collision promotion; reload trigger and failure semantics.

- [ ] **Step 2: Check documentation formatting**

Run: `git diff --check`

Expected: exit code 0 and no whitespace errors.

- [ ] **Step 3: Stage only documentation and inspect the staged scope**

Run:

```bash
git add CONTEXT.md \
  docs/adr/0012-disabled-skills-move-outside-runtime-skill-path.md \
  docs/superpowers/specs/2026-07-15-disabled-skill-discovery-suppression-design.md \
  docs/superpowers/plans/2026-07-22-market-disabled-skill-management.md
```

Run GitNexus `detect_changes({scope: "staged"})`; it must report documentation-only scope. Do not include unrelated staged files.

- [ ] **Step 4: Commit the approved design record**

```bash
git commit --only \
  CONTEXT.md \
  docs/adr/0012-disabled-skills-move-outside-runtime-skill-path.md \
  docs/superpowers/specs/2026-07-15-disabled-skill-discovery-suppression-design.md \
  docs/superpowers/plans/2026-07-22-market-disabled-skill-management.md \
  -m "docs(skills): define Market disabled-skill management"
```

### Task 2: Make SWE reconciliation promote active collisions

**Files:**

- Modify: `src/swe/agents/skills_manager.py:596-626`
- Test: `tests/unit/agents/test_disabled_skill_layout.py`

- [ ] **Step 1: Run the required upstream impact checks before editing symbols**

Run GitNexus upstream impact for `_reconcile_registered_skill_location` and `reconcile_workspace_manifest`. Report direct callers, affected processes, and any HIGH/CRITICAL risk before editing.

- [ ] **Step 2: Write failing collision tests**

Add tests that create both `workspace/skills/demo/SKILL.md` and `workspace/.disabled_skills/demo/SKILL.md` with a manifest entry `{ "enabled": false }`. After `reconcile_workspace_manifest(workspace)`, assert:

```python
manifest = json.loads((workspace / "skill.json").read_text(encoding="utf-8"))
assert manifest["skills"]["demo"]["enabled"] is True
assert (workspace / "skills" / "demo" / "SKILL.md").read_text() == "active-copy"
assert not (workspace / ".disabled_skills" / "demo").exists()
```

Keep the existing enabled-both-root case and assert the same active-copy result.

- [ ] **Step 3: Verify the tests fail under the old behavior**

Run:

```bash
PYTHONPATH=src ../../venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py -q
```

Expected: the new disabled-entry collision assertion fails because the old code moves the active copy back to `.disabled_skills/` and preserves `enabled=false`.

- [ ] **Step 4: Implement the promotion at the reconciliation boundary**

Change `_reconcile_registered_skill_location()` so its both-root branch reports promotion, rather than treating it as an ordinary location mismatch. Keep the active copy and remove the disabled copy:

```python
if active.exists() and disabled.exists():
    shutil.rmtree(disabled)
    entry["enabled"] = True
    return active
```

The caller must derive `enabled` only after this helper runs, so `next_entry["enabled"]` becomes `True` and the package remains in `skills/`. Do not promote a package that exists in only one root.

- [ ] **Step 5: Verify SWE behavior and formatting**

Run:

```bash
PYTHONPATH=src ../../venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py -q
venv/bin/python -m black --check --line-length=79 \
  src/swe/agents/skills_manager.py \
  tests/unit/agents/test_disabled_skill_layout.py
```

Expected: all selected tests pass and Black reports both files unchanged.

- [ ] **Step 6: Inspect staged impact and commit**

Stage exactly the two files, run GitNexus staged `detect_changes`, then commit:

```bash
git commit --only src/swe/agents/skills_manager.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  -m "fix(skills): promote active disabled-skill collisions"
```

### Task 3: Add Market's strict v2 manifest and package-resolution contract

**Files:**

- Modify: `market/src/market/marketplace/fs.py:265-275,461-587`
- Test: `market/tests/unit/marketplace/test_fs.py`

- [ ] **Step 1: Run upstream impact checks before editing helpers**

Run GitNexus upstream impact for `get_user_skills_dir`, `read_user_skill_manifest`, `mutate_user_skill_manifest`, and `copy_skill_to_user`. Report any HIGH/CRITICAL result before changing code.

- [ ] **Step 2: Write failing filesystem-contract tests**

Cover these cases with a workspace containing `skill.json`:

```python
active_root = get_user_skills_dir(root, "tenant", "default", "source")
assert get_user_disabled_skills_dir(root, "tenant", "default", "source") == (
    active_root.parent / ".disabled_skills"
)
```

Add parameterized invalid manifests: invalid UTF-8/JSON, missing `layout_version`, `layout_version != 2`, non-dict `skills`, non-dict entry, missing `enabled`, and non-bool `enabled`. Assert every mutation/preflight helper raises a `WorkspaceSkillManifestError` before any destination directory is created or removed. Add resolution tests for enabled target, disabled target, target-missing fallback, and both-root active preference.

- [ ] **Step 3: Verify the tests fail**

Run:

```bash
PYTHONPATH=src:market/src ../../venv/bin/python -m pytest \
  market/tests/unit/marketplace/test_fs.py -q
```

Expected: new disabled-root helper/resolver tests fail, and v1/structurally invalid manifests are currently accepted by Market mutation code.

- [ ] **Step 4: Implement local strict validation and pure resolution**

Add a Market-local exception and helpers; do not import SWE private helpers:

```python
class WorkspaceSkillManifestError(ValueError):
    pass

def get_user_disabled_skills_dir(
    swe_root: Path,
    user_id: str,
    agent_id: str = DEFAULT_AGENT_ID,
    source_id: str | None = None,
) -> Path:
    return get_user_skill_manifest_path(
        swe_root, user_id, agent_id, source_id
    ).parent / ".disabled_skills"

def validate_workspace_skill_manifest_v2(payload: object) -> dict:
    if not isinstance(payload, dict) or payload.get("layout_version") != 2:
        raise WorkspaceSkillManifestError("Run skills migrate-layout --apply")
    skills = payload.get("skills")
    if not isinstance(skills, dict):
        raise WorkspaceSkillManifestError("skills must be an object")
    for name, entry in skills.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            raise WorkspaceSkillManifestError("invalid skill entry")
        if "enabled" not in entry or not isinstance(entry["enabled"], bool):
            raise WorkspaceSkillManifestError("enabled must be a boolean")
    return payload
```

Use the default v2 payload only when `skill.json` is absent. Make mutation/preflight reads call this validator. Add a resolver that accepts a validated manifest and registered name, prefers the root selected by `enabled`, falls back to the other root, and returns the active root for a both-root collision without mutating state.

- [ ] **Step 5: Make distribution preflight strict before copying**

Change `copy_skill_to_user()` to receive the validated manifest and destination path selected by the caller, or to obtain them through the new strict preflight helper. Perform that preflight before `shutil.rmtree()` or `shutil.copytree()`. Preserve customized conflict behavior and `created_at` retention.

- [ ] **Step 6: Verify and commit**

Run the Task 3 test command plus Black on `fs.py` and its test. Stage only `fs.py` and `test_fs.py`, run GitNexus staged `detect_changes`, then commit:

```bash
git commit --only market/src/market/marketplace/fs.py \
  market/tests/unit/marketplace/test_fs.py \
  -m "fix(market): resolve validated workspace skill packages"
```

### Task 4: Make Market lifecycle and maintenance paths layout-aware

**Files:**

- Modify: `market/src/market/marketplace/service.py:570-907,1377-1417,1939-1975,2173-2541,3344-3380,3804-3849`
- Test: `market/tests/unit/marketplace/test_service.py`

- [ ] **Step 1: Run upstream impact checks before editing service methods**

Run GitNexus upstream impact for `_scan_skill_or_raise`, `register_skill_in_manifest`, `enable_skill`, `disable_skill`, `batch_delete_skills`, `batch_enable_skills`, `batch_disable_skills`, `get_my_skills`, `list_skill_files`, `read_skill_file`, `save_skill_file`, `delete_skill`, `migrate_skill_json_to_manifest`, `_sync_cn_name_to_user_workspace`, `update_skill_cn_name`, `_recall_skill_from_user`, `publish_skill`, and `distribute_skill`. Report any HIGH/CRITICAL result before editing.

- [ ] **Step 2: Write failing service tests for dual-root behavior**

Add focused tests for the following observable behavior:

```python
# registered disabled package is listed with enabled=False and can be read/edited
items = await svc.get_my_skills(source, user)
assert [item.skill_name for item in items] == ["disabled", "manual"]
assert next(item for item in items if item.skill_name == "disabled").enabled is False

# registered hidden package can be enabled; Market writes true then requests reload
result = await svc.enable_skill(user, "disabled", "default", source)
assert result == {"success": True}
after_enable = json.loads(
    get_user_skill_manifest_path(swe_root, user, "default", source).read_text(
        encoding="utf-8"
    )
)
assert after_enable["skills"]["disabled"]["enabled"] is True

# registered enabled package cannot be deleted; registered disabled package is deleted from hidden root
assert await svc.delete_skill(user, "enabled", "default", source) is False
assert await svc.delete_skill(user, "disabled", "default", source) is True

# manual active package remains listed and only enable claims it
assert "manual" not in manifest["skills"]
await svc.enable_skill(user, "manual", "default", source)
after_claim = json.loads(
    get_user_skill_manifest_path(swe_root, user, "default", source).read_text(
        encoding="utf-8"
    )
)
assert after_claim["skills"]["manual"]["enabled"] is True
```

Also test active collision promotion on a mutating Market operation: delete the hidden copy, retain the active content, and persist `enabled=True`. Test list/read/save/publish/Chinese-name sync against a disabled package, asserting edits stay hidden and `enabled` remains false. Test `migrate_skill_json_to_manifest()` across both roots but only for registered entries. Router tests in Task 5 cover download behavior.

- [ ] **Step 3: Verify the tests fail**

Run:

```bash
PYTHONPATH=src:market/src ../../venv/bin/python -m pytest \
  market/tests/unit/marketplace/test_service.py -q
```

Expected: disabled packages are absent from `get_my_skills`, enable/delete/file operations return not found, and migration skips hidden packages.

- [ ] **Step 4: Add service-level registered and unmanaged resolvers**

Implement one private service helper for mutating registered operations. It must strict-read/validate the manifest, apply active collision promotion atomically with its manifest mutation, and return the resolved existing package path. Use a separate read-only helper for listing that merges:

```python
registered_items = [
    resolved_path
    for name, entry in manifest["skills"].items()
    if (
        resolved_path := resolve_registered_skill_path(
            workspace_dir=workspace_dir,
            skill_name=name,
            entry=entry,
        )
    )
]
unmanaged_active = [
    path for path in skills_dir.iterdir()
    if path.is_dir() and path.name not in manifest["skills"]
]
```

Deduplicate by directory name. Do not enumerate `.disabled_skills/` entries that are absent from the manifest.

- [ ] **Step 5: Route all existing service paths through the resolver**

Replace direct `get_user_skills_dir(swe_root, user_id, agent_id, source_id) / skill_name` use in: security scan for a registered package, enable/disable, single and batch delete, list/read/save files, per-package `skill.json` migration, cn-name sync, market recall, and publish-source copying. Preserve legacy active-root operations for an unmanaged package; only explicit enable scans and claims it. For a registered deletion, reject `enabled=True` without changing files or state; for a registered disabled deletion, remove the resolved path, manifest entry, and DB row.

- [ ] **Step 6: Preserve enablement during distribution and schedule reloads**

Before copying a market package, strictly load the destination manifest. For an existing entry, resolve and overwrite its actual package directory while retaining its `enabled` value; for an absent entry, copy to `skills/` and register enabled. After a new distribution, enabled-package update, or any deletion, call `_trigger_agent_reload`; do not call it for disabled-package maintenance. Keep reload errors as warnings and do not roll back completed writes.

- [ ] **Step 7: Verify and commit**

Run the Task 4 test command and Black on `service.py` and `test_service.py`. Stage only the two files, run GitNexus staged `detect_changes`, then commit:

```bash
git commit --only market/src/market/marketplace/service.py \
  market/tests/unit/marketplace/test_service.py \
  -m "fix(market): manage disabled workspace skills"
```

### Task 5: Remove router-level active-root assumptions

**Files:**

- Modify: `market/src/market/app/routers/skills_browse.py:820-830,1289-1338,1417-1422`
- Test: `market/tests/unit/marketplace/test_skills_browse.py`

- [ ] **Step 1: Run upstream impact checks before editing router helpers**

Run GitNexus upstream impact for `_check_skill_name_exists_user`, `upload_skill_to_workspace`, and `download_my_skill`. Report any HIGH/CRITICAL result before editing.

- [ ] **Step 2: Write failing route tests**

Add tests that assert a download request for a registered disabled custom skill returns a ZIP from `.disabled_skills/<name>`, and that an upload/distribution with a disabled same-name registered package invokes the service collision/distribution flow rather than treating the hidden package as absent. Add an invalid-v2 manifest upload test that asserts no `skills/<name>` directory was created.

- [ ] **Step 3: Verify the tests fail**

Run:

```bash
PYTHONPATH=src:market/src ../../venv/bin/python -m pytest \
  market/tests/unit/marketplace/test_skills_browse.py -q
```

Expected: download returns 404 for the hidden package and invalid manifest upload can create an active directory before failure.

- [ ] **Step 4: Delegate path decisions to MarketplaceService**

Replace router-level active-root path construction with service methods that use Task 4 resolution. Make `_check_skill_name_exists_user` inspect active and disabled managed roots through the filesystem helper, while leaving a normal active unmanaged directory visible to the existing upload naming UX. Run upload strict preflight before `mkdir()` and import, then register imported packages using the service's state-preserving registration path.

- [ ] **Step 5: Verify and commit**

Run the Task 5 test command and Black on `skills_browse.py` and its test. Stage only those files, run GitNexus staged `detect_changes`, then commit:

```bash
git commit --only market/src/market/app/routers/skills_browse.py \
  market/tests/unit/marketplace/test_skills_browse.py \
  -m "fix(market): expose disabled skill management paths"
```

### Task 6: Run cross-surface verification and final review

**Files:**

- Verify: all files modified by Tasks 1-5

- [ ] **Step 1: Run the complete affected regression slice**

Run:

```bash
PYTHONPATH=src:market/src ../../venv/bin/python -m pytest \
  tests/unit/agents/test_disabled_skill_layout.py \
  tests/unit/agents/test_skill_invocation_detector.py \
  market/tests/unit/marketplace/test_fs.py \
  market/tests/unit/marketplace/test_service.py \
  market/tests/unit/marketplace/test_skills_browse.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run formatting and diff checks**

Run:

```bash
venv/bin/python -m black --check --line-length=79 \
  src/swe/agents/skills_manager.py \
  market/src/market/marketplace/fs.py \
  market/src/market/marketplace/service.py \
  market/src/market/app/routers/skills_browse.py \
  tests/unit/agents/test_disabled_skill_layout.py \
  market/tests/unit/marketplace/test_fs.py \
  market/tests/unit/marketplace/test_service.py \
  market/tests/unit/marketplace/test_skills_browse.py
git diff --check
git diff --cached --check
```

Expected: every command exits 0.

- [ ] **Step 3: Run final GitNexus scope review**

Run `detect_changes({scope: "compare", base_ref: "main"})` and staged `detect_changes({scope: "staged"})`. Review affected processes for Workspace skill management, Market distribution, Agent reload, and migration. Resolve every new Critical or Important finding before handoff.

- [ ] **Step 4: Inspect the final worktree**

Run `git status --short` and verify no unrelated user changes are staged or committed. Report the exact test, formatting, and GitNexus evidence in the implementation handoff.
