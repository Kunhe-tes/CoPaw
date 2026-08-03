# File Manager Column Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make shortcut roots appear as a left-hand navigation anchor and make folder selections move the three-column directory window according to their source column.

**Architecture:** Keep directory API responses as the source of list content, but make column movement explicit in a small navigation helper inside `FileManager`. A shortcut root begins with a synthetic left anchor, its direct listing in the middle column, and the first child listing in the right column. Directory selection derives its next `[left, middle, right]` window from the selected source column, while files preserve the existing right-side detail flow.

**Tech Stack:** React, TypeScript, Vitest, React Testing Library, AgentScope/Ant Design.

---

### Task 1: Specify the changed navigation behaviour with failing component tests

**Files:**
- Modify: `console/src/pages/Chat/components/FileManager/index.test.tsx`
- Test: `console/src/pages/Chat/components/FileManager/index.test.tsx`

- [ ] **Step 1: Write failing shortcut-anchor and column-shift tests**

  Add directory fixtures for `working`, `docs`, `guides`, and their parents. Assert that opening the manager places `工作目录` in column 1 while its child list is loaded for column 2; assert a folder click from column 1 loads the parent/current/selected-child window; assert a folder click from column 3 produces the prior-middle/prior-right/selected-child window.

- [ ] **Step 2: Run the focused test file to verify it fails**

  Run: `pnpm test:run src/pages/Chat/components/FileManager`

  Expected: the new tests fail because the existing implementation places the shortcut root listing in column 1 and has no source-column-specific left backfill.

### Task 2: Implement explicit directory-window transitions

**Files:**
- Modify: `console/src/pages/Chat/components/FileManager/index.tsx:83-321`
- Test: `console/src/pages/Chat/components/FileManager/index.test.tsx`

- [ ] **Step 1: Add a synthetic shortcut-anchor list and initial window loader**

  Represent the active shortcut root as a non-actionable directory entry in the left column. Load its actual directory listing into the middle column and load the first child directory into the right column. Keep `currentDirectory` bound to the middle column so upload semantics do not change.

- [ ] **Step 2: Add the directory selection transition rules**

  In `selectEntry`, retain file handling. For a directory selected in column 1, load the old left directory's parent for column 1, move the old left page to column 2, and place the selected directory page in column 3. For column 2, retain columns 1 and 2 and load the selection into column 3. For column 3, move old columns 2 and 3 into columns 1 and 2 and load the selection into column 3. At the shortcut anchor boundary, do not navigate above the root.

- [ ] **Step 3: Keep related state coherent for every transition**

  Reset the detail and preview state on a directory transition; reset only the replaced column query and selected path; retain independent paging for retained list pages; use the existing loading/error slot for the destination column. Ensure breadcrumb navigation reanchors via the same window builder.

- [ ] **Step 4: Run focused tests to verify they pass**

  Run: `pnpm test:run src/pages/Chat/components/FileManager`

  Expected: all File Manager tests pass, including the new shortcut and source-column navigation cases.

### Task 3: Update the source-of-truth interaction specification

**Files:**
- Modify: `docs/superpowers/specs/2026-07-29-chat-file-manager-design.md:44-61`
- Modify: `design_file_manager.md:61-110`

- [ ] **Step 1: Correct the shortcut and selection rules**

  State that shortcut selection uses a left-hand root anchor, with the root's list in the middle column, and record the left/middle/right folder transition rules. Preserve file-preview behaviour and the middle-column upload target.

- [ ] **Step 2: Run the full relevant checks**

  Run: `pnpm test:run src/pages/Chat/components/FileManager && pnpm exec tsc --noEmit`

  Expected: tests and TypeScript compilation complete successfully.

### Task 4: Review and commit the scoped change

**Files:**
- Modify: `console/src/pages/Chat/components/FileManager/index.tsx`
- Modify: `console/src/pages/Chat/components/FileManager/index.test.tsx`
- Modify: `docs/superpowers/specs/2026-07-29-chat-file-manager-design.md`
- Modify: `design_file_manager.md`

- [ ] **Step 1: Inspect the final diff and check whitespace**

  Run: `git diff --check` and inspect only the four files above. Confirm that no unrelated user changes are staged.

- [ ] **Step 2: Run GitNexus changed-symbol detection**

  Run `detect_changes()` for the workspace. If the service is unavailable, record the transport failure and rely on the focused test and TypeScript evidence.

- [ ] **Step 3: Commit the implementation**

  Run: `git add console/src/pages/Chat/components/FileManager/index.tsx console/src/pages/Chat/components/FileManager/index.test.tsx docs/superpowers/specs/2026-07-29-chat-file-manager-design.md design_file_manager.md docs/superpowers/plans/2026-07-30-file-manager-column-navigation.md && git commit -m "fix(chat): refine file manager directory navigation"`
