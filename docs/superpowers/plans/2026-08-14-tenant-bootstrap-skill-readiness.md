# Tenant Bootstrap Skill Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Do not block tenant bootstrap on skill manifests or skill directories.

**Architecture:** Keep `inspect_bootstrap_readiness()` responsible for core tenant artifacts only. Remove its skill-manifest parsing and manifest-to-directory correspondence checks; skill consumers retain their own validation at use time.

**Tech Stack:** Python, pytest.

---

### Task 1: Make skill artifacts optional for bootstrap readiness

**Files:**
- Modify: `tests/unit/workspace/test_bootstrap_state.py`
- Modify: `src/swe/app/workspace/bootstrap_state.py`

- [x] **Step 1: Write the failing test**

```python
def test_inspect_bootstrap_readiness_ignores_missing_skill_artifacts(tmp_path):
    tenant_dir = _make_ready_tenant(tmp_path)
    shutil.rmtree(tenant_dir / "skill_pool")
    (tenant_dir / "workspaces" / "default" / "skills").rmdir()

    readiness = inspect_bootstrap_readiness(tenant_dir)

    assert readiness.ready
```

- [x] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/unit/workspace/test_bootstrap_state.py -k skill_artifacts -v`

Expected: FAIL because the existing validator reports the missing skill pool,
manifest, or skills directory.

- [x] **Step 3: Write minimal implementation**

```python
# Do not read skill manifests or validate skill directories in
# inspect_bootstrap_readiness().
```

Remove only the skill constants, manifest reads, and calls that perform those
checks. Do not alter validation of configuration, agent, workspace files,
sessions, memory, or JSON state.

- [x] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/unit/workspace/test_bootstrap_state.py -k skill_artifacts -v`

Expected: PASS.

- [x] **Step 5: Run focused regression suite**

Run: `venv/bin/python -m pytest tests/unit/workspace/test_bootstrap_state.py tests/unit/workspace/test_tenant_recovery.py -v`

Expected: PASS.
