# Agent-owned SubAgent Experts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace JSON-based reusable SubAgent registration with Agent-owned TOML expert packages and a structured expert center.

**Architecture:** A focused TOML repository owns filesystem, revision, validation, and preservation behavior. The Background SubAgent tool assembles a four-source catalog at Main-Agent turn construction. A scoped router exposes only the current Agent Profile's packages, and the Console consumes that router with a dedicated `/experts` page.

**Tech Stack:** Python/FastAPI/Pydantic/tomllib, pytest, React/TypeScript/Ant Design/Vitest.

---

### Task 1: Agent-owned TOML repository and models

**Files:**
- Create: `src/swe/app/subagents/agent_definitions.py`
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/app/subagents/skill_definitions.py`
- Test: `tests/unit/subagents/test_agent_definitions.py`

- [ ] Write failing tests for UUID filenames, TOML parse errors, unknown-field round trips, canonical TOML, revision mismatch, and enabled-name collision.
- [ ] Run `venv/bin/python -m pytest tests/unit/subagents/test_agent_definitions.py -v` and observe failure because the repository does not exist.
- [ ] Implement the minimal Agent-owned package parser/repository, atomic writes, definition source metadata, and a shared parser that retains unknown TOML fields.
- [ ] Run the same test command until green.
- [ ] Commit the repository and tests.

### Task 2: Runtime catalog and Main Agent tool contract

**Files:**
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/app/subagents/skill_definitions.py`
- Modify: `src/swe/app/subagents/__init__.py`
- Modify: `src/swe/agents/tools/subagent_background.py`
- Modify: `src/swe/agents/react_agent.py`
- Delete: `src/swe/app/subagents/definition_store.py`
- Delete: `src/swe/app/subagents/definition_service.py`
- Delete: `src/swe/app/subagents/matcher.py`
- Test: `tests/unit/subagents/test_background_tools.py`
- Test: `tests/unit/subagents/test_skill_definitions.py`

- [ ] Write failing tests that an enabled Agent-owned TOML is listed with built-in and Skill-owned definitions, source values are explicit, exact-name resolution wins, and `register_subagent_definition` is never registered.
- [ ] Run the focused tests and observe their expected failures.
- [ ] Replace the JSON registry construction with the Agent-owned repository; add all catalog entries to the tool description without source labels; retain the unknown-name instruction fallback; make Agent-owned dependency handling equal to Skill-owned handling.
- [ ] Run focused unit tests until green, then commit.

### Task 3: Expert management API

**Files:**
- Create: `src/swe/app/routers/experts.py`
- Modify: `src/swe/app/routers/agent_scoped.py`
- Test: `tests/unit/routers/test_experts.py`

- [ ] Write failing API tests for list/detail/create/update/preview/enable/disable/delete, invalid-package repair, `If-Match` conflicts, and current-Agent path isolation.
- [ ] Run `venv/bin/python -m pytest tests/unit/routers/test_experts.py -v` and observe failure.
- [ ] Implement a scoped router backed by the TOML repository; use request Agent context, canonical responses, explicit 409/422 responses, and no arbitrary workspace parameter.
- [ ] Run router and subagent tests until green, then commit.

### Task 4: Expert center Console page

**Files:**
- Create: `console/src/api/modules/experts.ts`
- Create: `console/src/pages/Experts/index.tsx`
- Create: `console/src/pages/Experts/index.test.tsx`
- Modify: `console/src/api/index.ts`
- Modify: `console/src/layouts/MainLayout/index.tsx`
- Modify: `console/src/layouts/Sidebar.tsx`
- Modify: `console/src/layouts/constants.ts`
- Modify: applicable locale files

- [ ] Read `console/DESIGN.md` and write failing tests for empty state, create-disabled default, save-without-toggle, invalid repair, dependency warnings, conflict messaging, and deletion confirmation.
- [ ] Run the focused Vitest test and observe failure because the page/API adapter does not exist.
- [ ] Implement the structured list/form and read-only TOML preview using existing style and data sources. Do not display built-in or Skill-owned definitions and do not add a test-run action.
- [ ] Run focused frontend tests and type/lint checks until green, then commit.

### Task 5: Full verification and review closure

**Files:**
- Modify only files identified by review findings.

- [ ] Run the full related backend and frontend suites.
- [ ] Dispatch spec-compliance and code-quality reviewers after each commit; fix findings and rerun their affected tests.
- [ ] Run `pre-commit run --all-files` where feasible and `git diff --check`.
- [ ] Use GitNexus `detect_changes` before the final commit and review all changed execution flows.
- [ ] Commit review fixes and report feature/test evidence.
