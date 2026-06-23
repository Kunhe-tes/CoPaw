## Context

The Console is a React 18, Vite, Ant Design 5, and Less application with an existing brand-theme provider, light/dark theme infrastructure, iframe integration, and page-local styling. Visual inspection shows several independently evolved UI languages: the chat workspace uses a three-column layout and fixed CoPaw blue emphasis, management pages range from card forms to split panes, and analytics pages use a separate dashboard style. Styling is frequently local or inline, while `src/config/designTokens.ts` covers only part of the chat homepage.

This change establishes a committed design contract for all future `console/` UI work, then validates it through the global navigation and the complete `/models` page. The Console is also embedded in host products; `hideMenu=true` removes the Header and global Sidebar, so redesigned content must work with both standalone and embedded shells. The user requires UI-only change: business inputs, behavior, outputs, API contracts, state semantics, routes, permissions, and iframe messages must remain unchanged.

## Goals / Non-Goals

**Goals:**

- Establish `console/DESIGN.md` as the single committed design entry point for future Console UI work.
- Define a light-only, system-font visual foundation with medium-high management-page density and a dedicated conversation-workspace pattern.
- Use Vercel as the primary management/navigation color and surface reference, Linear for restrained information hierarchy, Claude only as an optional warmth reference, and CoPaw for product-specific identity.
- Keep `#3769FC` as the explicit conversation-workspace primary color while allowing navigation and management pages to use restrained neutral surfaces and contextual accent color.
- Redesign the existing global navigation and full model-management experience using scoped presentation changes and reusable visual components.
- Cover normal, loading, empty, error, disabled, and in-progress presentation states without changing their triggers or semantics.
- Calibrate the design system twice using the real page at `1280x720`, `1440x900`, and `1920x1080`, including `hideMenu=true` embedded presentation.

**Non-Goals:**

- Redesigning the chat page, analytics pages, or every legacy management page in this change.
- Changing menu structure, labels, ordering, routes, authorization, collapse state behavior, iframe integration, provider/model operations, or API behavior.
- Deleting the existing dark-theme implementation or adding new dark-theme styling.
- Changing Header logo assets or dimensions; only surrounding layout presentation may change.
- Introducing external fonts, a new component framework, or screenshot-baseline automation.
- Vendoring third-party `DESIGN.md` files.

## Decisions

### 1. Commit one project design source of truth

`console/DESIGN.md` will define foundations, component rules, page patterns, boundaries, and verification. It will link to external references and explain what is borrowed, but external documents will not be copied into the repository. This avoids competing design authorities and lets future UI changes cite one stable project document.

Alternative considered: commit Linear, Vercel, and Claude reference files beside the project document. Rejected because overlapping rules would create ambiguity and require external synchronization.

### 2. Separate global design authority from incremental code adoption

The document applies to all new or modified `console/` UI, but implementation in this change is scoped to shared safe foundations, global navigation, and model management. Global Ant Design tokens will change only when the value is broadly compatible; page-specific visual rules will use scoped Less/CSS Modules or scoped presentational components.

Alternative considered: globally override all Ant Design and legacy CSS at once. Rejected because it would visually mutate untouched pages and make regressions difficult to attribute.

### 3. Use one system with distinct conversation and management patterns

The design system will share typography, spacing logic, borders, icon rules, states, and accessibility across the Console while defining two product patterns:

- Conversation Workspace: fixed `#3769FC` emphasis and priority order of conversation/current task content, composer, task/history lists, tool/progress/file details, guidance content, and global navigation.
- Management Console: medium-high density with standard management, list-detail, and dashboard templates.

This avoids forcing chat and configuration workflows into one layout while preserving a recognizable product family.

### 4. Preserve existing shell and embedding behavior

The global navigation receives visual-only refinement. Existing menu definitions, selection mapping, expansion, collapse, permissions, Header rendering, and `hideMenu` conditions remain authoritative. Model management must fill the available content region when embedded without assuming the global navigation exists.

Alternative considered: automatically collapse navigation on chat routes. Rejected because route-driven shell changes exceed the UI-only scope and can conflict with host-product navigation.

### 5. Keep the technical stack and organize presentation code

Implementation will continue to use Ant Design, `@agentscope-ai/design`, Less/CSS Modules, and system fonts. Existing AgentScope semantic icons remain; new generic interface icons prefer Lucide, with Ant Design Icons used only where already coupled or no suitable icon exists. Emoji will not be used as functional icons.

Pure presentational components and visual tokens may be extracted. Business hooks, stores, request functions, event-handler semantics, and mutation ownership remain in their current logical boundaries.

### 6. Make provider cards compact but fully identifiable

The model provider area will retain cards because local and remote providers have heterogeneous summaries and actions. Each compact management card will visibly preserve provider icon, name, ID, availability, key connection summary such as Base URL, model count, and primary actions. Primary actions remain visible; low-frequency actions may move into a visible more-actions menu.

The final calibration uses a compact identity header, one continuous aligned summary list, and a quiet unfilled action row so the card reads as one surface rather than several nested panels. The page header uses only one compact breadcrumb trail and a small settings anchor icon, without duplicating the current page title or adding a hero-like description.

Alternative considered: convert providers to a table. Rejected because heterogeneous provider types and action sets would either produce sparse columns or force significant interaction restructuring.

### 7. Use adaptive desktop composition rather than mobile-first redesign

The model page will use efficient desktop gutters and a left-aligned provider-card grid with a practical maximum card width. The primary target is common desktop monitors; `1280x720` is the minimum desktop check, `1440x900` is the primary design viewport, and `1920x1080` verifies large-screen use. Basic overflow safety remains required, but dedicated phone layouts are outside scope.

### 8. Calibrate the design document through implementation

Round one creates the initial `DESIGN.md`, scoped tokens/styles, navigation, and complete model-management redesign. Browser review and user feedback then update the document and implementation together. Round two repeats the agreed viewport and embedding checks; only then is the design system treated as the basis for later page migrations.

## Risks / Trade-offs

- [A shared token unexpectedly changes an untouched page] -> Keep risky values scoped, inspect touched shared tokens against representative legacy pages, and revert unsafe global application without weakening the documented rule.
- [UI refactoring changes business behavior] -> Preserve hooks and handlers, keep operations wired to the same functions, and verify existing tests plus core model/provider interaction paths before and after the change.
- [The first page overfits the global design system] -> Separate global foundations from model-management-specific patterns and use the two-round calibration to revise rules that do not generalize.
- [Light-only requirements conflict with dormant dark-theme code] -> Do not delete or expand theme logic; ensure new scoped styles target the supported light presentation and record dark-theme removal as a separate future change.
- [Embedded layout differs across host products] -> Preserve `hideMenu` and iframe contracts, test the page without Header/Sidebar, and avoid fixed widths tied to the standalone shell.
- [Large screens make content sparse] -> Use moderate page gutters and maximum-width item cards rather than a narrow centered page container or cards that stretch to fill all remaining space.
- [No automated visual baseline allows visual regressions] -> Capture review screenshots and perform structured manual viewport checks during this calibration phase; reconsider automation after the design system stabilizes.

## Migration Plan

1. Add and review `console/DESIGN.md` with the agreed design foundations and UI-only boundaries.
2. Introduce or reorganize safe shared visual tokens without broad legacy overrides.
3. Apply scoped navigation visual changes while preserving shell behavior.
4. Apply the complete model-management visual redesign, including dialogs and all existing states.
5. Run build, lint/tests relevant to touched code, and functional checks for preserved provider/model operations.
6. Perform first-round browser review at the agreed viewports and in standalone/embedded presentation.
7. Capture user feedback, revise `DESIGN.md`, tokens, and scoped implementation together.
8. Repeat verification for final acceptance.

Rollback is file-scoped: revert the design document, scoped tokens/styles, and presentational component changes. No data migration or backend rollback is required.

## Open Questions

None. Detailed color values and component measurements are intentionally finalized during the first implementation calibration, within the constraints defined here and in the capability specs.
