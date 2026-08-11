## Context

The Console currently has two composer surfaces:

- New chats with no messages render the custom welcome composer in `WelcomeCenterLayout`.
- Existing or historical chats with messages render the standard bottom composer through `AgentScopeRuntimeWebUI/core/Chat/Input` and `ChatInput`.

Plan Mode state is already persisted on each chat as `meta.plan_mode_enabled` and is synchronized into `planModeEnabled` in `console/src/pages/Chat/index.tsx`. The quick menu can toggle the mode, but the active state is not surfaced as a persistent composer control. The visible label also still falls back to English (`Plan` / `Plan Mode`) in several frontend paths.

## Goals / Non-Goals

**Goals:**

- Show a visible `计划模式` active-state button whenever the current chat has Plan Mode enabled.
- Let users disable Plan Mode directly from that composer button.
- Keep the active-state control consistent between the welcome composer and the standard bottom composer.
- Keep the quick-menu switch for enabling, disabling, and discovering Plan Mode.
- Localize visible Plan Mode entry labels to `计划模式`.
- Preserve per-chat state when switching between new chats and historical chats.

**Non-Goals:**

- No backend changes to `ChatSpec.meta`, `/console/chat`, or Agent runtime Plan Mode behavior.
- No changes to internal request enum values such as `mode: "plan" | "normal"`.
- No replacement of the welcome composer with the standard bottom composer.
- No redesign of the whole quick menu or sidebar history list.

## Decisions

### Decision: Extract a shared active Plan Mode composer button

Create a reusable Plan Mode active button near existing helpers in `console/src/pages/Chat/planMode.tsx`. It should accept `enabled`, `disabled`, `label`, and `onDisable`/`onClick` props and render nothing when disabled by state (`enabled === false`).

Rationale:

- `Chat/index.tsx` is already the source of `planModeEnabled` and `persistPlanMode`.
- A shared component prevents the welcome composer and bottom composer from drifting.
- The button can be tested independently from session loading.

Alternative considered: duplicate a small button in both composer implementations. Rejected because the existing bug is already caused by split composer implementations drifting.

### Decision: Use `sender.prefix` for the historical-chat bottom composer

Inject the active Plan Mode button into `sender.prefix` from the Chat page options. `ChatInput` already renders `prefix` in the bottom action bar next to the quick menu, which matches the target screenshot.

Rationale:

- This avoids changing the generic `ChatInput` API.
- The active control remains colocated with composer actions and does not compete with send/cancel controls.

Alternative considered: add a new `activeModeItems` option to the AgentScope runtime sender. Rejected for the first implementation because `prefix` already provides the needed extension point.

### Decision: Add a small explicit extension point to `WelcomeCenterLayout`

Add a prop such as `prefixItems?: React.ReactNode | React.ReactNode[]` to `WelcomeCenterLayout` and render those nodes inside `.welcome-input-actions-left` after the quick menu.

Rationale:

- The welcome composer is custom and does not consume `sender.prefix`.
- A narrow prop keeps the welcome layout aligned with the standard composer without forcing a larger abstraction.

Alternative considered: make `WelcomeCenterLayout` consume all `sender` options. Rejected because it would widen the component contract and increase coupling to runtime internals.

### Decision: Keep quick-menu switch and active button responsibilities separate

The quick-menu item remains a switch and can turn Plan Mode on or off. The active button is shown only when Plan Mode is on and its primary action is to turn it off.

Rationale:

- The quick menu remains the discoverable mode settings entry.
- The active button provides the fast visible exit path requested by the UI.
- This mirrors the screenshot: enabled mode becomes visible in the composer action row.

### Decision: Session switching only reads persisted chat metadata

Do not introduce a global Plan Mode UI store. The active button follows `activePlanModeSession` and `getPlanModeEnabled(activePlanModeSession)`.

Rationale:

- Plan Mode is per chat, not global.
- Existing `useEffect` already resets `planModeEnabled` when the active session metadata changes.
- Avoids leaking state between historical chats and new local sessions.

## Risks / Trade-offs

- Historical session metadata may arrive after the composer first renders → render from existing `planModeEnabled` state and let the existing session metadata sync update the button when loading completes.
- Persisting Plan Mode off can fail → reuse `persistPlanMode(false)` rollback and error handling so the visible button reverts to the session-derived state.
- Welcome and bottom composer spacing may diverge on small screens → use compact, stable button sizing and add tests for DOM presence; visual QA should cover narrow and desktop widths before final delivery.
- Existing tests expect English labels → update expectations to `计划模式` and keep ARIA labels explicit.

## Migration Plan

1. Add the shared active Plan Mode button component and styles.
2. Replace English Plan Mode visible fallbacks with `计划模式`.
3. Inject the active button through `sender.prefix` for the standard bottom composer.
4. Add `prefixItems` to `WelcomeCenterLayout` and pass the same active button from Chat welcome render options.
5. Update tests for helper labels, bottom composer controls, welcome composer controls, and session switching behavior.
6. Rollback by removing the injected active button props; existing quick-menu Plan Mode behavior continues to function.
