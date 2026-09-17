## Why

Plan Mode is already a persistent per-chat state, but the Console UI does not surface that active state consistently. Users can enable it from the quick menu, yet historical chats and new-chat welcome state use different composer implementations, so the visible controls and close interaction drift.

## What Changes

- Rename visible Plan Mode entry text from `Plan` / `Plan Mode` to `计划模式`.
- Add a visible active Plan Mode button in the composer action area whenever the current chat has `meta.plan_mode_enabled === true`.
- Allow the active Plan Mode button to disable Plan Mode directly from the composer without opening the quick menu.
- Render the same active Plan Mode affordance in both:
  - the new-chat welcome composer;
  - the historical-chat bottom composer.
- Keep the existing quick-menu switch as the place to enable Plan Mode and inspect/toggle the mode.
- Preserve existing request metadata contracts: internal values remain `mode: "plan" | "normal"` and `meta.plan_mode_enabled`.

## Capabilities

### New Capabilities
- `plan-mode-composer-controls`: Active Plan Mode composer controls, localized label, and close interaction across chat composer variants.

### Modified Capabilities
- `chat-welcome-layout`: The welcome input card gains the same active mode affordance used by the standard bottom composer.
- `sidebar-task-list`: History session selection must load chats into a composer surface with the same active mode controls as new chats.

## Impact

- Frontend Chat page Plan Mode wiring in `console/src/pages/Chat/index.tsx`.
- Plan Mode UI helper components in `console/src/pages/Chat/planMode.tsx`.
- Welcome composer surface in `console/src/components/agentscope-chat/WelcomeCenterLayout/`.
- Standard bottom composer integration through `sender.prefix` in `AgentScopeRuntimeWebUI/core/Chat/Input`.
- Component tests for Plan Mode helpers, welcome composer controls, standard composer prefix controls, and history/new-chat parity.
- No backend API, storage, or Agent runtime changes are required.
