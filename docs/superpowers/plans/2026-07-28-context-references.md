# Context References Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cached, typed Skill, MCP Tool, and Workspace File selection to the Console `@` overlay and inject each validated selection into one chat request.

**Architecture:** A backend Context Reference service owns cache, discovery, scope validation, and trusted instruction rendering. The Console fetches its grouped results only while `@` is active, sends structured selections, and replaces the skill-only editor/menu with a compact typed-reference editor.

**Tech Stack:** FastAPI/Pydantic, asyncio, pytest; React/TypeScript, Ant Design, Vitest/Testing Library.

---

### Task 1: Backend typed discovery and cache

**Files:**
- Create: `src/swe/app/context_references.py`
- Modify: `src/swe/app/routers/console.py`
- Modify: `src/swe/app/mcp/manager.py`
- Test: `tests/unit/app/test_context_references.py`
- Test: `tests/unit/routers/test_console_chat_stream.py`

- [ ] **Step 1: Write failing backend tests**

Cover scope-key isolation, fixed TTLs (300s Skills; 180s MCP/files), LRU capacity of 128, expired-entry removal, single-flight refresh, 5,000-file-per-root cap, filename-only matching, four-result group limits, and MCP discovery where successful clients are returned while failed/timed-out clients are omitted.

- [ ] **Step 2: Run the new tests and verify RED**

Run: `../../venv/bin/python -m pytest tests/unit/app/test_context_references.py -q`

Expected: FAIL because the context-reference service and endpoint do not exist.

- [ ] **Step 3: Implement the minimal service and endpoint**

Create typed reference models (`skill`, `mcp_tool`, `workspace_file`), an LRU cache using `time.monotonic`, and a `/console/context-references` endpoint that resolves the request workspace. Use the workspace MCP manager's active clients, run `list_tools(timeout=2)` concurrently, stop waiting after three seconds, and only keep success results. Index `media`/`static` metadata without file content and return grouped, capped results.

- [ ] **Step 4: Run backend tests and verify GREEN**

Run: `../../venv/bin/python -m pytest tests/unit/app/test_context_references.py tests/unit/routers/test_console_chat_stream.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/swe/app/context_references.py src/swe/app/routers/console.py src/swe/app/mcp/manager.py tests/unit/app/test_context_references.py tests/unit/routers/test_console_chat_stream.py
git commit -m "feat(chat): discover context references"
```

### Task 2: Trusted request resolution and instruction injection

**Files:**
- Create: `src/swe/app/runner/context_references.py`
- Modify: `src/swe/app/routers/console.py`
- Modify: `src/swe/app/runner/runner.py`
- Test: `tests/unit/app/runner/test_context_references.py`
- Test: `tests/unit/app/runner/test_skill_selection.py`

- [ ] **Step 1: Write failing request-resolution tests**

Test that duplicate stable identities are collapsed, selected skills still render existing skill directives, MCP references render a preference-only instruction after active-client validation, and file references are re-resolved under only the workspace `media` or `static` roots before rendering on-demand-read context. Test invalid, missing, cross-root, disabled, and unavailable references produce no directive.

- [ ] **Step 2: Run the tests and verify RED**

Run: `../../venv/bin/python -m pytest tests/unit/app/runner/test_context_references.py -q`

Expected: FAIL because structured references are not accepted or rendered.

- [ ] **Step 3: Implement structured request propagation**

Add `context_references` to Console payload extraction and native metadata. Add runner helpers that read the metadata, resolve the effective workspace and active MCP clients, and merge validated renderers into system prompt injections. Preserve `selected_skill_names` compatibility while new skill selections flow through the structured contract.

- [ ] **Step 4: Run request-resolution tests and verify GREEN**

Run: `../../venv/bin/python -m pytest tests/unit/app/runner/test_context_references.py tests/unit/app/runner/test_skill_selection.py tests/unit/routers/test_console_chat_stream.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/swe/app/runner/context_references.py src/swe/app/routers/console.py src/swe/app/runner/runner.py tests/unit/app/runner/test_context_references.py tests/unit/app/runner/test_skill_selection.py tests/unit/routers/test_console_chat_stream.py
git commit -m "feat(chat): inject validated context references"
```

### Task 3: Frontend API and grouped mention state

**Files:**
- Create: `console/src/api/modules/contextReferences.ts`
- Modify: `console/src/api/modules/chat.ts`
- Modify: `console/src/components/agentscope-chat/SkillMentions/useSkillMentions.ts`
- Test: `console/src/components/agentscope-chat/SkillMentions/index.test.tsx`
- Test: `console/src/components/agentscope-chat/SkillMentions/SkillTokenEditor.test.tsx`

- [ ] **Step 1: Write failing Vitest cases**

Test grouped defaults, query-only file results, result order, omission of empty groups, a shared empty state, type-aware stable selection deduplication, and token removal for skill/MCP/file selections.

- [ ] **Step 2: Run the Vitest cases and verify RED**

Run: `pnpm --dir console test:run src/components/agentscope-chat/SkillMentions/index.test.tsx src/components/agentscope-chat/SkillMentions/SkillTokenEditor.test.tsx`

Expected: FAIL because the current model only accepts skill names.

- [ ] **Step 3: Implement typed client models and state**

Add grouped API models and a fetch function. Generalize mention items and selected state to typed Context References, add a 200 ms query debounce, preserve arrows/Enter/Escape, and only request files after a non-empty query.

- [ ] **Step 4: Run focused Vitest cases and verify GREEN**

Run: `pnpm --dir console test:run src/components/agentscope-chat/SkillMentions/index.test.tsx src/components/agentscope-chat/SkillMentions/SkillTokenEditor.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add console/src/api/modules/contextReferences.ts console/src/api/modules/chat.ts console/src/components/agentscope-chat/SkillMentions/useSkillMentions.ts console/src/components/agentscope-chat/SkillMentions/index.test.tsx console/src/components/agentscope-chat/SkillMentions/SkillTokenEditor.test.tsx
git commit -m "feat(chat): model typed mention references"
```

### Task 4: Compact overlay and Chat request integration

**Files:**
- Modify: `console/src/components/agentscope-chat/SkillMentions/index.tsx`
- Modify: `console/src/components/agentscope-chat/SkillMentions/SkillTokenEditor.tsx`
- Modify: `console/src/pages/Chat/welcomeSkillMentions.ts`
- Modify: `console/src/pages/Chat/index.tsx`
- Test: `console/src/pages/Chat/welcomeSkillMentions.test.ts`
- Test: `console/src/components/agentscope-chat/SkillMentions/index.test.tsx`

- [ ] **Step 1: Write failing UI/integration tests**

Test compact left-aligned rows, one-line clipped secondary text without tooltip or horizontal overflow, the empty-query discovery hint, category labels/icons, request-scoped clearing, and that Chat sends `context_references` for the pending selection.

- [ ] **Step 2: Run focused Vitest cases and verify RED**

Run: `pnpm --dir console test:run src/pages/Chat/welcomeSkillMentions.test.ts src/components/agentscope-chat/SkillMentions/index.test.tsx`

Expected: FAIL because the existing UI is skill-only and sends `selected_skill_names`.

- [ ] **Step 3: Implement compact categorized UI and payload wiring**

Render typed grouped rows with compact icons, labels, and clipped secondary text; lower row/panel height and enforce `minWidth: 0`, `overflowX: hidden`, and `textOverflow: ellipsis`. Render type-specific atomic tokens without tooltips. Replace the Chat page's skill-only pending state with Context References, preserve slash-command behavior, and include the structured array in outgoing request metadata.

- [ ] **Step 4: Run focused frontend tests and verify GREEN**

Run: `pnpm --dir console test:run src/pages/Chat/welcomeSkillMentions.test.ts src/components/agentscope-chat/SkillMentions/index.test.tsx src/components/agentscope-chat/SkillMentions/SkillTokenEditor.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add console/src/components/agentscope-chat/SkillMentions/index.tsx console/src/components/agentscope-chat/SkillMentions/SkillTokenEditor.tsx console/src/pages/Chat/welcomeSkillMentions.ts console/src/pages/Chat/index.tsx console/src/pages/Chat/welcomeSkillMentions.test.ts console/src/components/agentscope-chat/SkillMentions/index.test.tsx
git commit -m "feat(chat): render compact context reference overlay"
```

### Task 5: Full verification and review

**Files:**
- Verify: `goal.md`
- Verify: `CONTEXT.md`
- Verify: backend and Console test suites

- [ ] **Step 1: Run backend and frontend suites**

Run: `../../venv/bin/python -m pytest tests/unit/app/test_context_references.py tests/unit/app/runner/test_context_references.py tests/unit/routers/test_console_chat_stream.py -q`

Run: `pnpm --dir console test:run src/components/agentscope-chat/SkillMentions src/pages/Chat/welcomeSkillMentions.test.ts`

Run: `pnpm --dir console build`

- [ ] **Step 2: Perform visual walk-through**

Use the Console with `@`, query skills/MCP/files, verify all empty/loading/timeout states, keyboard selection/removal, compact clipping, and no horizontal scrollbar.

- [ ] **Step 3: Run change impact and independent reviews**

Run GitNexus `detect_changes` and delegate spec-compliance and code-quality reviews. Address every actionable issue and rerun the relevant tests.

- [ ] **Step 4: Audit goal coverage and commit the finished implementation**

Compare every `goal.md` item with source, tests, and UI evidence. Commit only the expected files after `git diff --check` and all verification commands pass.
