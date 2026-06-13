## 1. Current-Source Raw Config APIs

- [x] 1.1 Add current-source raw config response and request models for `GET/PUT/DELETE /api/source-system-config/current`
- [x] 1.2 Implement current-source router handlers that resolve `source_id` only from request context and never from caller-supplied path/body fields
- [x] 1.3 Return default-state payloads for missing current-source records and keep effective config API semantics unchanged
- [x] 1.4 Add tests for authorized current-source reads, updates, deletes, default-state reads, and non-manager rejection

## 2. Registered Feature Switch Save Semantics

- [x] 2.1 Add a code-owned registry for current-source system-config switches, including default values and the initial `feature_switches.chat_task_progress_enabled` entry
- [x] 2.2 Implement merge-and-prune logic that preserves unknown raw config keys and removes explicit overrides equal to defaults
- [x] 2.3 Delete the current-source config record when pruning leaves an empty config object
- [x] 2.4 Add tests for unknown-key preservation, default-value pruning, and empty-config deletion

## 3. Console Current Source Config Page

- [x] 3.1 Extend `console/src/api/modules/sourceSystemConfig.ts` with current-source raw config read/write/delete APIs
- [x] 3.2 Add current-source config page state, form binding, and save/delete flows on `system-config-page` without a source selector
- [x] 3.3 Render the registered `chat_task_progress_enabled` switch and a default-state indication based on the current-source raw config response
- [x] 3.4 Refresh the effective source config store after successful save/delete and add focused UI/store tests

## 4. Permissions And Runtime Gating

- [x] 4.1 Update `console/src/api/authHeaders.ts` to send `X-User-Role: admin|manager` from iframe context
- [x] 4.2 Add frontend permission guards that hide the page entry for non-managers and show a 403-style state on direct access
- [x] 4.3 Gate `ReactAgent` system prompt construction with `feature_switches.chat_task_progress_enabled`
- [x] 4.4 Make `update_task_progress` no-op when the current source disables task progress
- [x] 4.5 Prevent runner stream attachment and chat UI rendering of task progress when the switch is disabled
- [x] 4.6 Add backend and frontend tests covering enabled/disabled task progress behavior

## 5. Verification And Documentation

- [x] 5.1 Update analysis/playbook documentation for current-source system-config editing, permissions, and task progress switch behavior
- [x] 5.2 Run focused backend tests for source-system-config and task-progress gating
- [x] 5.3 Run focused Console tests for current-source config page, auth headers, and effective-config refresh
- [x] 5.4 Run `openspec status --change current-source-system-config-page` and confirm the change is apply-ready
