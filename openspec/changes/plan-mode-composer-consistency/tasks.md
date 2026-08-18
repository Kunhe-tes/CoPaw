## 1. Test Coverage First

- [x] 1.1 Update `console/src/pages/Chat/planMode.test.tsx` expectations from `Plan` to `计划模式` and add coverage for the active Plan Mode composer button rendering and disable click callback.
- [x] 1.2 Add or update `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/Input/index.test.tsx` coverage proving `sender.prefix` renders a custom active mode control and can dispatch its click handler.
- [x] 1.3 Update `console/src/components/agentscope-chat/WelcomeCenterLayout/index.test.tsx` to verify welcome composer action-row extension controls render next to the quick menu.
- [x] 1.4 Add Chat page level coverage, or the narrowest available component seam, proving Plan Mode active state follows the selected session metadata and does not leak between sessions.

## 2. Shared Plan Mode Controls

- [x] 2.1 Add a reusable active Plan Mode button component in `console/src/pages/Chat/planMode.tsx` that renders `计划模式` only when enabled.
- [x] 2.2 Wire the active button click to a caller-provided disable handler without embedding session persistence logic inside the button.
- [x] 2.3 Add scoped styles in `console/src/pages/Chat/index.module.less` for compact action-row rendering, hover/focus states, disabled state, and dark mode.
- [x] 2.4 Replace visible Plan Mode fallback labels and descriptions in `console/src/pages/Chat/index.tsx` with Chinese copy: `计划模式`, `进入计划模式`, and `计划模式使用只读工具先产出计划`.

## 3. Standard Bottom Composer Integration

- [x] 3.1 Build a memoized active Plan Mode control in `console/src/pages/Chat/index.tsx` from `planModeEnabled` and `persistPlanMode(false)`.
- [x] 3.2 Pass the active Plan Mode control into `sender.prefix` so historical chats with messages show it in the bottom composer action row.
- [x] 3.3 Preserve any existing `sender.prefix` content by composing the new control with existing prefix nodes rather than replacing them.
- [x] 3.4 Ensure the active button is hidden while Plan Mode is disabled and reappears when the active session metadata enables it.

## 4. Welcome Composer Integration

- [x] 4.1 Add a narrow `prefixItems?: React.ReactNode | React.ReactNode[]` prop to `WelcomeCenterLayout`.
- [x] 4.2 Render `prefixItems` inside `.welcome-input-actions-left` after the quick menu and before the send button.
- [x] 4.3 Pass the shared active Plan Mode control from `Chat/index.tsx` into the welcome render function.
- [x] 4.4 Verify the welcome composer keeps existing upload, file paste, featured-case fill, and send behavior unchanged.

## 5. Session Consistency

- [x] 5.1 Confirm `activePlanModeSession` resolution covers `id`, `realId`, `sessionId`, and `session_id` for both historical chats and local new-chat sessions.
- [x] 5.2 Confirm `persistPlanMode(false)` updates the current chat metadata and rolls back local UI state on failure.
- [x] 5.3 Ensure opening a history item with Plan Mode enabled shows the active button after session load.
- [x] 5.4 Ensure opening a history item without Plan Mode enabled hides the active button after session load.

## 6. Verification

- [x] 6.1 Run focused frontend tests for Plan Mode helpers, runtime input, and welcome composer.
- [x] 6.2 Run focused Chat page/session tests covering Plan Mode metadata sync if available.
- [x] 6.3 Run `pnpm test:run` for the affected frontend test suite if the focused tests pass.
- [ ] 6.4 Manually verify in the browser that new-chat welcome composer and historical-chat bottom composer both show and disable `计划模式` consistently.
- [x] 6.5 Run `gitnexus_detect_changes()` before any commit to verify the affected symbols and flows match this plan.
