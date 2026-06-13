# Distribution Ownership Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add management surfaces for cron distribution children and application-market skill owner lookup.

**Architecture:** Cron management is implemented as backend APIs because child jobs live in target-tenant CronManagers and need server-side validation before delete or rerun. Market skill owner lookup is a Console aggregation because this repository only contains the frontend market API calls; it matches source users' current skills by stable skill name rather than distribution records.

**Tech Stack:** FastAPI, Pydantic, pytest, React, TypeScript, Ant Design, Vitest.

---

### Task 1: Cron Backend Distribution Management

**Files:**
- Modify: `src/swe/app/crons/api.py`
- Test: `tests/unit/app/test_tenant_cron_api.py`

- [ ] **Step 1: Write failing backend tests**

Add tests that create a source job and target tenant managers. Cover:
- `GET /cron/jobs/{job_id}/broadcast/children` returns `[]` for no children.
- Existing children are listed by `meta.broadcast_source_job_id`.
- `POST /cron/jobs/{job_id}/broadcast/children/delete` deletes only children belonging to the source.
- `POST /cron/jobs/{job_id}/broadcast/children/run` runs enabled children and returns a skipped item for disabled children.
- Rebroadcast to an existing target child updates source task fields but preserves child ID, tenant identity, dispatch target, and `enabled`.

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\app\test_tenant_cron_api.py -q`
Expected before implementation: failures for missing routes or unchanged skip behavior.

- [ ] **Step 2: Implement backend APIs and merge helper**

In `src/swe/app/crons/api.py`:
- Add response models for child summaries and batch results.
- Add helpers to scan logical source tenants and resolve target CronManagers.
- Add `GET /jobs/{job_id}/broadcast/children`.
- Add `POST /jobs/{job_id}/broadcast/children/delete`.
- Add `POST /jobs/{job_id}/broadcast/children/run`.
- Replace duplicate-child skip with a helper that builds a source-derived child spec and merges only task-definition fields into the existing child while preserving target-owned fields.

- [ ] **Step 3: Verify backend tests pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\app\test_tenant_cron_api.py -q`
Expected: all tests in the file pass.

### Task 2: Cron Console Child Management

**Files:**
- Modify: `console/src/api/types/cronjob.ts`
- Modify: `console/src/api/modules/cronjob.ts`
- Modify: `console/src/pages/Control/CronJobs/index.tsx`
- Modify: `console/src/pages/Control/CronJobs/components/columns.tsx`
- Create: `console/src/pages/Control/CronJobs/components/BroadcastChildrenModal.tsx`

- [ ] **Step 1: Write focused frontend test if practical**

Prefer a helper-level or component-level test if the existing Cron Jobs tests can mount action columns. Validate that child batch results map to the intended status labels.

- [ ] **Step 2: Add API types and methods**

Add TypeScript types for child summary, lookup response, batch request, batch result, and batch response. Add client methods:
- `listCronBroadcastChildren(jobId)`
- `deleteCronBroadcastChildren(jobId, items)`
- `runCronBroadcastChildren(jobId, items)`

- [ ] **Step 3: Add modal and menu action**

Add a menu action for every job: "查看分发用户". The modal loads children, shows an empty state when none exist, supports row selection, and calls delete/rerun batch APIs. Disabled children remain visible; batch rerun results show skipped disabled items as "已暂停，未执行".

- [ ] **Step 4: Verify frontend targeted tests**

Run the focused Vitest command for changed Cron Jobs files.

### Task 3: Market Skill Owner Lookup

**Files:**
- Modify: `console/src/api/modules/market.ts`
- Modify: `console/src/pages/Market/MarketSkills.tsx`
- Modify: `console/src/pages/Market/SkillCard.tsx`
- Modify: `console/src/pages/Market/SkillDetailDrawer.tsx`
- Create: `console/src/pages/Market/components/SkillOwnerLookupModal.tsx`
- Create: `console/src/pages/Market/skillOwnerLookup.ts`
- Test: `console/src/pages/Market/skillOwnerLookup.test.ts`

- [ ] **Step 1: Write failing helper tests**

Test that a stable market skill name matches user skills by `skill_name`, returns market/user version, and marks update-needed when `has_update` is true or versions differ.

Run: `cd console; npm.cmd run test:run -- src/pages/Market/skillOwnerLookup.test.ts`
Expected before implementation: missing module/test failure.

- [ ] **Step 2: Implement lookup helper and API support**

Add a market API helper that can fetch a user's received/current skills with `X-Source-Id` and target-user header support if available. Add pure matching helpers that are easy to test.

- [ ] **Step 3: Add management action and modal**

Add "查看拥有用户" beside existing manager actions on skill cards and detail drawer. The modal loads source tenants, fetches each user's skills, filters same-name matches, and shows user name, tenant ID, bbk ID, market version, installed version, and update status.

- [ ] **Step 4: Verify frontend tests**

Run the helper Vitest command and any affected Market component tests available in the repo.

### Task 4: Docs And Final Verification

**Files:**
- Modify: `wiki/cron/README.md`
- Modify or create: `wiki/cron/cron-distribution-management.md`
- Create: `wiki/market-skill-owner-lookup/README.md`
- Modify: `openspec/changes/add-distribution-ownership-management/tasks.md`

- [ ] **Step 1: Update docs**

Document cron child lookup/batch actions and market skill name-based owner lookup. Make clear that skill lookup is current-state name matching, not distribution-log history.

- [ ] **Step 2: Run verification**

Run:
- `.\.venv\Scripts\python.exe -m pytest tests\unit\app\test_tenant_cron_api.py -q`
- frontend targeted Vitest commands for Market helper and Cron Jobs changes
- `openspec.cmd validate add-distribution-ownership-management --strict`
- `git diff --check`

- [ ] **Step 3: Review final diff**

Check `git diff --stat`, `git status --short`, and GitNexus `detect_changes(scope=all)`. Update tasks to checked only after matching verification has run.
