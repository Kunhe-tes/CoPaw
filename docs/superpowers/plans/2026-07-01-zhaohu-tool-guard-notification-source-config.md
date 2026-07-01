# Zhaohu Tool Guard Notification Source Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let each Source System Configuration decide whether Tool Guard approval pending/result notifications are sent to zhaohu.

**Architecture:** Add a registered boolean source config setting under `approval_notifications.zhaohu_tool_guard_enabled`, defaulting to `false`. The zhaohu approval notification hooks read the current effective source config and skip only zhaohu notification sends when the setting is `false`; approval creation, console approval commands, audit events, and Tool Guard enforcement remain unchanged.

**Tech Stack:** Python/Pydantic/FastAPI source config registry, pytest, React/TypeScript/Ant Design system config page, Vitest.

---

### Task 1: Backend Source Config And Runtime Helper

**Files:**
- Modify: `src/swe/app/source_system_config/registry.py`
- Modify: `src/swe/app/source_system_config/runtime.py`
- Modify: `src/swe/app/source_system_config/__init__.py`
- Test: `tests/unit/app/test_source_system_config.py`

- [ ] **Step 1: Write failing tests**

Add tests asserting the default source config includes:

```python
"approval_notifications": {
    "zhaohu_tool_guard_enabled": False,
}
```

Add runtime helper tests asserting `is_zhaohu_tool_guard_notification_enabled(None)` returns `False` and a config with `{"approval_notifications": {"zhaohu_tool_guard_enabled": True}}` returns `True`.

- [ ] **Step 2: Run backend source config tests to verify failure**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_config.py -q
```

Expected: FAIL because the new helper and default key do not exist.

- [ ] **Step 3: Implement registered setting and helper**

Add `APPROVAL_NOTIFICATIONS_ZHAOHU_TOOL_GUARD_ENABLED_SETTING` to the registry, include it in `CURRENT_SOURCE_SYSTEM_CONFIG_SETTINGS`, and implement/export `is_zhaohu_tool_guard_notification_enabled()` in `runtime.py` and `__init__.py`.

- [ ] **Step 4: Re-run backend source config tests**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_config.py -q
```

Expected: PASS.

### Task 2: Approval Notification Guard

**Files:**
- Modify: `src/swe/app/approvals/external.py`
- Test: `tests/unit/app/test_external_approvals.py`

- [ ] **Step 1: Write failing tests**

Add tests binding an effective source config with `approval_notifications.zhaohu_tool_guard_enabled = False`, then assert:

```python
await notify_cron_approval_pending(...)
assert workspace.channel_manager.zhaohu.pending_calls == []
```

and, for `submit_external_approval_decision`, assert the console submission still happens while `zhaohu.result_calls == []`.

- [ ] **Step 2: Run approval tests to verify failure**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_external_approvals.py -q
```

Expected: FAIL because zhaohu notification is still always attempted.

- [ ] **Step 3: Implement notification guard**

In `notify_cron_approval_pending()` and `notify_cron_approval_result()`, call the source config helper before resolving the zhaohu channel. If disabled, return without sending zhaohu and without recording zhaohu notification events.

- [ ] **Step 4: Re-run approval tests**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_external_approvals.py -q
```

Expected: PASS.

### Task 3: System Config Page Switch

**Files:**
- Modify: `console/src/api/types/sourceSystemConfig.ts`
- Modify: `console/src/pages/SystemConfigPage/registry.ts`
- Modify: `console/src/pages/SystemConfigPage/registry.test.ts`
- Modify: `console/src/pages/SystemConfigPage/index.test.tsx`

- [ ] **Step 1: Write failing frontend registry/page tests**

Add a registry test that writing the new switch produces:

```typescript
{
  approval_notifications: {
    zhaohu_tool_guard_enabled: true,
  },
}
```

Update page switch-index helpers and add a page test that toggles the zhaohu approval notification switch and saves the same payload.

- [ ] **Step 2: Run frontend tests to verify failure**

Run:

```powershell
Push-Location console
.\node_modules\.bin\vitest.cmd run src/pages/SystemConfigPage/registry.test.ts src/pages/SystemConfigPage/index.test.tsx --testTimeout=30000
Pop-Location
```

Expected: FAIL because the switch is not registered yet.

- [ ] **Step 3: Implement frontend switch**

Add `approval_notifications.zhaohu_tool_guard_enabled` to `CURRENT_SOURCE_SYSTEM_CONFIG_SWITCHES` with default `false`, title `Tool Guard 审批招乎通知`, and description explaining that enabling it sends zhaohu approval notifications for the current source only.

- [ ] **Step 4: Re-run frontend tests**

Run:

```powershell
Push-Location console
.\node_modules\.bin\vitest.cmd run src/pages/SystemConfigPage/registry.test.ts src/pages/SystemConfigPage/index.test.tsx --testTimeout=30000
Pop-Location
```

Expected: PASS.

### Task 4: Final Verification

**Files:**
- All modified files above

- [ ] **Step 1: Run targeted backend tests**

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_config.py tests/unit/app/test_external_approvals.py -q
```

- [ ] **Step 2: Run targeted frontend tests**

```powershell
Push-Location console
.\node_modules\.bin\vitest.cmd run src/pages/SystemConfigPage/registry.test.ts src/pages/SystemConfigPage/index.test.tsx --testTimeout=30000
Pop-Location
```

- [ ] **Step 3: Review diff**

Confirm the diff only adds source-scoped zhaohu Tool Guard notification configuration and does not alter approval enforcement, console submission, or unrelated dirty worktree files.
