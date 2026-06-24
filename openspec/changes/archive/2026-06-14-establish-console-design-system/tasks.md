## 1. Establish the Design Contract

- [x] 1.1 Create and commit `console/DESIGN.md` with the agreed light-theme foundations, reference strategy, conversation and management patterns, component guidance, UI-only boundaries, incremental adoption policy, and verification checklist.
- [x] 1.2 Define the initial neutral surface, typography, spacing, radius, border, elevation, semantic-state, and interaction tokens needed by the trial without broadly restyling untouched legacy pages.
- [x] 1.3 Document and encode the distinction between fixed `#3769FC` conversation emphasis and the restrained neutral/accent treatment used by global navigation and management pages.

## 2. Refine the Global Navigation Presentation

- [x] 2.1 Restyle the standalone global navigation shell, group labels, menu items, active/hover/focus states, separators, and content boundary using scoped light, low-distraction styles.
- [x] 2.2 Restyle and position the existing navigation collapse control while preserving its current expanded/collapsed behavior.
- [x] 2.3 Align navigation icon sizing and state colors without changing menu semantics, route mapping, permissions, ordering, or source-specific logo assets and dimensions.
- [x] 2.4 Verify that `hideMenu=true` continues to remove the Header and global Sidebar and that surrounding layout changes do not alter iframe behavior.

## 3. Redesign the Model-Management Page

- [x] 3.1 Recompose the `/models` page hierarchy and bounded adaptive content layout while preserving the existing default-LLM and provider-management logic.
- [x] 3.2 Redesign the default LLM configuration area with the trial management-page patterns and unchanged fields, actions, save state, and distribution behavior.
- [x] 3.3 Redesign provider search and page-level actions, correcting any visible raw localization-key leakage without changing action semantics.
- [x] 3.4 Implement compact adaptive provider cards that retain provider icon, name, ID, availability, Base URL or applicable connection summary, model count, visible primary actions, and discoverable low-frequency actions.
- [x] 3.5 Apply the design system to custom-provider, provider-configuration, remote-model, local-model/runtime, model-management, and provider-distribution dialogs without changing fields, validation, confirmations, handlers, or outcomes.
- [x] 3.6 Unify loading, empty, error, disabled, unavailable, and in-progress visual states while preserving their existing triggers, permissions, retry behavior, and state transitions.
- [x] 3.7 Extract only the presentational components and scoped Less/CSS Module rules needed to remove trial-area duplication, leaving business hooks, stores, requests, and event semantics in place.

## 4. Functional and Static Verification

- [x] 4.1 Run TypeScript/build, formatting or lint checks, and relevant existing frontend tests for the touched navigation and model-management code.
- [x] 4.2 Verify provider search, default-model selection/save, provider add/configure, model management, distribution, test, download/runtime, confirmation, permission, and error paths still invoke their existing behavior.
- [x] 4.3 Inspect representative untouched legacy pages after shared-token changes and scope or revert any global styling that causes unintended visual migration.

## 5. First Visual Calibration

- [x] 5.1 Review standalone global navigation and `/models` at `1280x720`, `1440x900`, and `1920x1080`, checking hierarchy, bounded width, adaptive card columns, clipping, overlap, and operation discoverability.
- [x] 5.2 Review `/models` with `hideMenu=true` to confirm embedded layout use and unchanged shell behavior.
- [x] 5.3 Capture first-round screenshots and present the implemented trial to the user for design feedback before expanding or finalizing the design system.

## 6. Final Calibration and Acceptance

- [x] 6.1 Apply the user's first-round feedback to `console/DESIGN.md`, visual tokens, navigation presentation, and model-management presentation without expanding the approved functional scope.
- [x] 6.2 Repeat functional checks and the required standalone and embedded viewport review after calibration changes.
- [x] 6.3 Confirm `console/DESIGN.md` and the trial implementation agree, record any deferred legacy-page migrations as separate future OpenSpec changes, and prepare the completed change for archive.
