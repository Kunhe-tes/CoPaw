# Console Skill Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Console users select effective skills with `@` and submit trusted, server-resolved skill-use directives for the current chat turn.

**Architecture:** The Console composer owns transient selected-skill chips and sends only ordered runtime names. A skills endpoint returns the current console-effective name/description list. The runner validates and de-duplicates selected names against the target workspace, then appends `<SKILL-USE-V1>` blocks to the trusted system-prompt context before constructing the Agent.

**Tech Stack:** React 18, TypeScript, Ant Design, Vitest, FastAPI, Pydantic-compatible AgentRequest extras, pytest.

---

### Task 1: Resolve and expose effective skill candidates

**Files:**
- Modify: `src/swe/app/routers/skills.py`
- Test: `tests/unit/routers/test_skills_tenant_scope.py`

- [ ] Add a failing router test that creates enabled/disabled and channel-scoped skills, then asserts the effective endpoint returns only `name` and `description` for console-effective skills.
- [ ] Run the focused pytest test and verify it fails because the endpoint/helper does not exist.
- [ ] Add a small response model and `GET /skills/effective` handler that derives results from the request workspace's `resolve_effective_skills(workspace, "console")` result.
- [ ] Re-run the focused pytest test and verify it passes.

### Task 2: Build trusted skill-use directives in the runner

**Files:**
- Create: `src/swe/app/runner/skill_selection.py`
- Modify: `src/swe/app/runner/runner.py`
- Test: `tests/unit/app/test_skill_selection.py`

- [ ] Add failing unit tests for five-name limiting, duplicate runtime-name removal with first-order retention, unavailable/unreadable omission, and `<SKILL-USE-V1>` rendering with a server-resolved absolute path.
- [ ] Run the focused pytest module and verify it fails because the resolver is absent.
- [ ] Implement a pure resolver that accepts ordered request names, workspace path, and channel; resolves only effective/readable packages and emits directive text without accepting client paths or descriptions.
- [ ] Append resolved directives to the runner's trusted system-prompt injections before Agent construction; preserve ordinary behavior for empty/invalid selections and command requests.
- [ ] Re-run the focused pytest module and verify it passes.

### Task 3: Add Composer skill selection UI and request payload

**Files:**
- Modify: `console/src/api/modules/skill.ts`
- Modify: `console/src/api/types/skill.ts`
- Modify: `console/src/components/agentscope-chat/Sender/index.tsx`
- Modify: `console/src/components/agentscope-chat/ChatAnywhere/Input/index.tsx`
- Modify: `console/src/components/agentscope-chat/ChatAnywhere/hooks/types.ts`
- Modify: `console/src/pages/Chat/index.tsx`
- Test: `console/src/components/agentscope-chat/Sender/index.test.tsx`

- [ ] Add failing Sender tests for valid whitespace-bounded `@` opening, name-only filtering, keyboard selection, five visible chips, duplicate chips, and chip removal.
- [ ] Run the focused Vitest test and verify it fails because mention selection is unsupported.
- [ ] Add typed mention-selector props to the composer, render chips above the textarea, and add accessible loading, empty, keyboard, and error states without changing slash-command behavior.
- [ ] Fetch `GET /skills/effective` once when a valid `@` menu opens; retain ordinary text when no candidate is chosen or loading fails.
- [ ] Bind the selected names to the next normal chat request only; omit and clear them for control commands, then clear the composer selection after submission.
- [ ] Re-run the focused Vitest test and verify it passes.

### Task 4: Verify integration and review the changed UI

**Files:**
- Verify: `tests/unit/routers/test_skills_tenant_scope.py`
- Verify: `tests/unit/app/test_skill_selection.py`
- Verify: `console/src/components/agentscope-chat/Sender/index.test.tsx`

- [ ] Run focused backend and frontend tests, then `console` TypeScript/build checks appropriate to the changed surface.
- [ ] Review the composer against `console/DESIGN.md` and the CoPaw F2E checklist: keyboard operation, focus visibility, long names, empty/error/loading states, and narrow containers.
- [ ] Run `git diff --check` and GitNexus `detect_changes()` before handoff.
