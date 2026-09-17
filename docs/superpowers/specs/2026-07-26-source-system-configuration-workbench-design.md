# Source System Configuration Workbench Design

## Goal

Redesign the existing **系统特性配置** page so administrators can understand the current source-scoped runtime behavior at a glance, locate a capability quickly, and make deliberate changes without altering the configuration API, permission boundary, persistence semantics, or runtime behavior.

## Scope

The page name remains **系统特性配置**. It remains an administrator-only, source-scoped configuration surface and preserves the existing single-draft, single-save model.

The redesign replaces the long vertical stack of form cards with a configuration workbench. It does not add or remove configuration fields, change defaults, change validation, or add backend endpoints.

## Information Architecture

The overview is a responsive capability-card grid with five fixed groups:

1. **对话与执行** — task-progress display and system-prompt injections.
2. **安全与审批** — database-access guard and Tool Guard approval notifications.
3. **模型调用** — query retries and LLM concurrency/rate limits.
4. **定时任务** — unread pause, weekend notifications, session cleanup, and archive maintenance.
5. **工具输出** — historic tool-result compression and file-read truncation.

The page header continues to identify the active source. A compact overview reports capability count and the counts for custom, default, and unsaved states. A status filter offers **全部**, **已自定义**, and **有未保存修改**; search is intentionally omitted because there are only five capability groups.

Each card presents an icon, capability name, one-sentence impact description, explicit state, and one or two key effective-value summaries. Its state is always distinguishable by label as well as color:

- **采用默认值** — no source-specific override for the capability.
- **已自定义** — the current source has an explicit configuration value.
- **有未保存修改** — the draft differs from the loaded saved configuration.

For settings whose existing semantics already support it, the detail view uses the more precise label **继承 Agent 配置** rather than treating every default as Agent inheritance.

## Detail Interaction

Selecting a capability opens a right-side, approximately 560px drawer. The overview remains visible in the background; on narrow containers the drawer becomes full-screen. Closing the drawer keeps the draft intact.

The drawer starts with the capability's current impact and configuration source. When an item has no override, it displays the current effective value read-only and offers **自定义此项**. Choosing it copies the current effective value into the existing draft so that the administrator edits a known baseline. Existing actions that restore inheritance retain their semantics and wording.

Primary controls remain directly visible: switches, prompt segments, key concurrency/QPM values, maximum retry count, and scheduled run time. Dense numeric configuration moves secondary thresholds, waiting, pause, jitter, and byte-size values into an **高级参数** disclosure. Numeric fields retain their existing validation and show a visible unit, range, and helper text.

System-prompt injections become an ordered list editor instead of one text area separated by blank lines. Each prompt is an editable, expandable segment with add, remove, and move-up/move-down actions. The list serializes to the existing ordered `string[]` payload, so execution order and duplicate/empty normalization remain unchanged.

Disabling the database-access guard is marked as a high-impact action. It requires a confirmation dialog before the draft changes and remains visibly marked in its card and detail panel. Ordinary switches update the draft directly.

## Save and Recovery

A persistent page-level save bar replaces the current detached action row. It states the unsaved change count, offers **查看变更**, **放弃修改**, and **保存全部修改**, and continues to submit the complete existing draft in one request.

The change review lists affected capabilities and fields, and navigates to the appropriate card/drawer section. Attempting to navigate away, switch source, or refresh with a dirty draft prompts the administrator to save, discard, or continue editing. Existing loading, validation-error, request-error, permission-denied, and save-failure states remain available and preserve entered draft values where the current page does.

## Visual Direction

The page follows the existing management-console visual language: white-first operational surfaces, high information density, blue primary interactions, restrained icons, and shallow functional grouping. It intentionally avoids decorative gradients, dashboard-style metric heroes, or nested ornamental cards. Warning color is reserved for high-impact safety changes, errors, and unsaved attention states.

## Implementation Boundaries

The frontend continues to use `sourceSystemConfigApi`, `useSourceSystemConfigStore`, the existing registry read/write/validation helpers, and the existing source and permission state. No route, API contract, iframe contract, source-selection behavior, runtime configuration semantics, or backend code changes are part of this work.

## Verification

Frontend tests cover capability grouping and state summaries, status filtering, opening/closing drawers without losing draft state, effective-value-to-custom initialization, prompt-segment ordering and serialization, advanced-parameter disclosure, high-impact confirmation, unified save, change review navigation, and dirty-draft leave confirmation.

Existing registry and page behavior tests continue to cover validation, defaults, inheritance, request errors, permissions, and save/delete behavior. The changed Console surface is also checked for keyboard reachability, visible labels, long source IDs and Chinese/English text, narrow embedded containers, loading/error/disabled states, and light/dark theme compatibility.
