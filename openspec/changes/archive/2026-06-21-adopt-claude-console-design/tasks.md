## 1. Single Design Authority

- [x] 1.1 Rewrite `console/DESIGN.md` in place as the latest CoPaw-first baseline, replacing Vercel as a mandatory primary reference while preserving the light-theme, incremental-adoption, UI-only, embedded, logo, and verification constraints.
- [x] 1.2 Document the approved white-first palette, blue primary actions, multilingual typography roles, medium-high management density, and the distinction between Management Console and Conversation Workspace presentation.
- [x] 1.3 Confirm that no alternate live project design manual, old baseline copy, or vendored third-party `DESIGN.md` is added and that future UI work still has one design authority.

## 2. Platform Font Foundation

- [x] 2.1 Define centralized UI, editorial, and technical platform font stacks that prioritize Windows readability and retain macOS fallbacks.
- [x] 2.2 Confirm this change adds no bundled font assets and no runtime font CDN dependency; record optional local multilingual fonts as deferred work.

## 3. Scoped Theme Architecture

- [x] 3.1 Refactor `consoleDesignTokens.ts` and related style entry points into reusable base, CoPaw Management Console, and existing Conversation Workspace semantic roles.
- [x] 3.2 Add an explicit reusable Management Console scope for white canvas/surfaces, text, borders, blue primary actions, typography, focus, disabled, status, radius, elevation, and motion roles.
- [x] 3.3 Preserve compatible Conversation Workspace roles, including `#3769FC`, and avoid global `body` font or primary-color changes that would migrate chat.
- [x] 3.4 Replace calibrated-surface hard-coded colors and fonts with semantic theme roles where needed for reuse, without globally restyling untouched legacy pages.

## 4. Global Shell And Navigation Calibration

- [x] 4.1 Apply the Management Console scope to the standalone Header and global Sidebar using the approved white canvas, restrained borders, compact UI typography, and low-distraction hierarchy.
- [x] 4.2 Recalibrate active, hover, focus, expanded, collapsed, disabled, separator, icon, and collapse-control presentation without changing navigation semantics or state behavior.
- [x] 4.3 Preserve configured logo assets and dimensions, Header/Sidebar visibility rules, menu ordering, routes, permissions, and `hideMenu=true` behavior.
- [x] 4.4 Verify that the global shell can appear beside the unchanged blue Conversation Workspace without theme or font leakage.

## 5. Model Management Calibration

- [x] 5.1 Apply the Management Console scope and approved font roles to `/models` while retaining the accepted breadcrumb-only header, compact hierarchy, practical desktop gutters, and left-aligned bounded card grid.
- [x] 5.2 Recalibrate default-LLM configuration, provider search, page actions, blue primary buttons, secondary actions, provider identity, summaries, status, and operation rows using the Management theme.
- [x] 5.3 Recalibrate custom-provider, provider-configuration, model-management, distribution, local-runtime, confirmation, result, loading, empty, error, disabled, unavailable, and in-progress presentation.
- [x] 5.4 Keep UI and operational text in the platform UI stack, keep IDs and URLs in the technical stack, and avoid broad serif use on the dense `/models` workflow.
- [x] 5.5 Preserve all existing provider/model requests, filtering, additions, removals, configuration, distribution, tests, downloads, runtime controls, validation, confirmations, permissions, handlers, and result semantics.

## 6. Functional And Isolation Verification

- [x] 6.1 Run frontend formatting, lint, relevant tests, type checks, and the production build for all touched design-system, navigation, font, and model-management code.
- [x] 6.2 Verify provider search, default-model save, provider add/configure, model management, distribution, test, download/runtime, confirmation, permission, loading, error, and retry paths still invoke existing behavior.
- [x] 6.3 Compare a representative chat route before and after to confirm unchanged blue emphasis, typography, conversation sidebar, composer, content layout, and interaction behavior.
- [x] 6.4 Inspect representative untouched non-chat legacy pages and scope any unintended management-theme or font leakage.
- [x] 6.5 Confirm the platform font stack produces no external font-network requests and remains readable in Windows Chrome and Edge.

## 7. Visual Calibration And Completion

- [x] 7.1 Review standalone navigation and `/models` at `1280x720`, `1440x900`, and `1920x1080` for hierarchy, density, typography, clipping, overlap, horizontal overflow, and action discoverability.
- [x] 7.2 Review `/models` with `hideMenu=true` and confirm the expanded embedded layout retains the Management theme without requiring Header or Sidebar.
- [x] 7.3 Present first-round screenshots to the user and apply accepted feedback to the implementation and the single `console/DESIGN.md` together.
- [x] 7.4 Repeat functional, Windows platform-font, chat-isolation, standalone, and embedded checks after calibration changes.
- [x] 7.5 Confirm implementation, `console/DESIGN.md`, delta specs, and deferred migration guidance agree; validate OpenSpec and prepare the accepted change for archive.
