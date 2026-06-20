## Context

CoPaw currently has an accepted light-theme Console baseline documented in `console/DESIGN.md`, centralized values in `consoleDesignTokens.ts`, and two calibrated surfaces: the global shell/navigation and `/models`. That baseline uses Vercel as its primary visual reference, Linear for density, and Claude only as an optional influence.

The product direction has changed. All non-conversation Console surfaces should move toward the warm editorial character documented by Claude's design-md, while the Conversation Workspace must retain its existing `#3769FC` identity, current typography, and independent conversation sidebar. The first recalibration remains the global shell/navigation and the complete model-management experience.

The Console is used primarily on Windows, including Chrome and Edge, and contains substantial Chinese text. This change therefore uses explicit platform font roles that prioritize Windows readability and retain macOS fallbacks. A local multilingual font package can be evaluated separately without blocking the visual migration.

`console/DESIGN.md` remains the only durable design authority. This change's OpenSpec artifacts explain and govern the migration, but they are not an alternative day-to-day design manual. The final implementation replaces the contents of `console/DESIGN.md` in place and does not retain a Vercel-era copy or vendor Claude's external design document.

## Goals / Non-Goals

**Goals:**

- Make Claude the primary external reference for non-conversation Console design through an adapted warm editorial system suitable for a dense Chinese management product.
- Keep one latest `console/DESIGN.md` and update it together with the implementation and formal specs.
- Establish reusable base, Management Console, and Conversation Workspace token layers so future non-chat migrations can adopt the new system without page-specific color duplication.
- Define stable UI, editorial, and technical font roles using platform fonts that are readable on Windows and macOS without network loading.
- Recalibrate the global shell/navigation and `/models`, including dialogs and states, to the new system while preserving behavior.
- Keep the Conversation Workspace visually and behaviorally unchanged.

**Non-Goals:**

- Redesigning chat content, the conversation sidebar, composer, tasks/history, tool calls, generated files, or any other Conversation Workspace surface.
- Migrating every legacy management page in this change.
- Adding theme switching, expanding dark-theme support, or deleting dormant dark-theme infrastructure.
- Copying Claude's marketing-site scale, low information density, complete typography usage, or exact page composition.
- Changing APIs, routes, permissions, state semantics, iframe contracts, validation, operation triggers, error handling, or business outcomes.
- Keeping multiple versions of the project design manual.
- Introducing or evaluating bundled multilingual font assets; that remains a separate optional typography change.

## Decisions

### 1. Replace the design manual in place

`console/DESIGN.md` will be rewritten as the latest accepted Claude-inspired baseline. It will retain relevant CoPaw product constraints, incremental migration policy, UI-only boundaries, page patterns, and verification rules, but Vercel will no longer be the primary reference. No `DESIGN-v1.md`, `DESIGN-VERCEL.md`, `DESIGN-CLAUDE.md`, or vendored third-party design file will be created.

OpenSpec `design.md` answers how and why this migration is performed. It does not compete with `console/DESIGN.md` as the working UI authority.

**Alternative considered:** preserve the old file and add a Claude-specific design document. Rejected because multiple authorities make later AI and human implementation ambiguous.

### 2. Adapt Claude's visual language rather than clone it

The initial management palette will use semantic roles centered on:

- warm canvas and standard card floor `#FAF9F5`;
- warm subtle surface `#F5F0E8`;
- warm ink `#141413`;
- secondary ink `#3D3D3A`;
- warm border `#E6DFD8`;
- coral primary action `#CC785C`;
- coral hover `#A9583E`.

These are calibration values, not page-level literals. Status colors, focus visibility, disabled states, and text contrast must remain accessible. Management pages retain medium-high information density, practical desktop gutters, compact controls, and operation discoverability instead of adopting marketing-page spacing.

**Alternative considered:** copy Claude design-md values and composition literally. Rejected because Chinese management workflows, existing Ant Design controls, and CoPaw's density require adaptation.

### 3. Use three token layers and explicit scope boundaries

The visual foundation will be organized conceptually as:

1. **Base tokens**: spacing, radii, elevation, motion, semantic status roles, and shared accessibility behavior.
2. **Management Console theme**: warm surfaces and ink, coral actions, management typography, and component presentation.
3. **Conversation Workspace theme**: existing blue emphasis and existing conversation typography/presentation.

Management theme variables will be applied through an explicit shell or management-surface scope rather than changing the global `body` font or replacing shared values that chat currently inherits. The global Header and navigation use the Management theme even when shown beside chat; the chat content region and independent conversation sidebar stay in the Conversation scope.

New non-chat pages will consume semantic roles such as canvas, surface, text, border, primary action, UI font, and editorial font. They must not depend on `/models` CSS classes or copy its literal colors.

**Alternative considered:** globally replace existing tokens. Rejected because it would silently alter chat and untouched legacy pages.

### 4. Use platform font stacks with role boundaries

The current change uses font roles that do not require bundled assets. The intended stacks are:

- UI: `Segoe UI`, `Microsoft YaHei`, `PingFang SC`, `Helvetica Neue`, sans-serif;
- editorial: `Georgia`, `Songti SC`, `SimSun`, serif;
- technical: the existing cross-platform monospace stack.

The UI role will be used for navigation, breadcrumbs, forms, buttons, compact cards, metadata, and management section headings. The editorial role remains limited to page-level editorial titles, welcome or guidance content, and selected content-led surfaces; `/models` remains primarily sans-serif. Technical IDs and URLs remain monospace.

The implementation will use UI weights 400/500/600 and editorial weights 500/600 where the selected platform fonts support them. Font loading must not depend on a runtime CDN. A future change may introduce locally hosted Poppins/Noto Sans SC and Lora/Noto Serif SC after licensing, payload, and rendering are reviewed.

**Alternative considered:** bundle multilingual webfonts in this change. Deferred because the visual direction can be validated first with platform fonts and the user explicitly chose not to introduce font assets yet.

### 5. Recalibrate existing reference surfaces, not all legacy pages

The global Header/navigation and `/models` remain the reference implementation. Their visual values will be migrated from hard-coded neutral grays to semantic management roles. `/models` will continue to preserve its accepted compact hierarchy, card content, breadcrumb treatment, visible actions, responsive desktop grid, dialogs, and business handlers while adopting warmer surfaces, typography, coral primary actions, and Claude-inspired restraint.

The full-width default-model panel uses the light canvas surface with a warm hairline border and 16px radius. The darker subtle surface remains reserved for smaller nested groups so large management panels do not become visually heavy.

Untouched non-chat pages remain legacy surfaces until separate migrations. Later changes can opt into the Management scope and reuse the same font declarations and semantic tokens.

### 6. Verify isolation and cross-platform behavior explicitly

The trial will be reviewed at `1280x720`, `1440x900`, and `1920x1080`, including `hideMenu=true` for `/models`. Windows Chrome and Edge are primary font and rendering targets. A representative chat route will be compared before and after to confirm that conversation fonts, blue emphasis, layout, and sidebar presentation did not change. Representative untouched management pages will be checked for unintended theme leakage.

## Risks / Trade-offs

- **[Platform typography differs between Windows and macOS]** -> Keep explicit ordered stacks, stable line heights, and Windows Chrome/Edge as primary review targets.
- **[Coral primary actions conflict with chat blue]** -> Enforce explicit Management and Conversation scopes; never expose a single global primary color as both product identities.
- **[Hard-coded legacy colors weaken reuse]** -> Convert only calibrated surfaces to semantic roles in this change and record remaining legacy migration separately rather than applying risky global overrides.
- **[Ant Design tokens leak into chat or legacy UI]** -> Scope provider/theme configuration and CSS variables as locally as the component architecture permits; verify representative routes.
- **[Claude-inspired styling becomes a cosmetic clone]** -> Keep CoPaw density, Chinese typography, embedded behavior, existing logo rules, and operational hierarchy documented as first-class constraints.
- **[Only one latest design manual removes historical comparison]** -> Preserve history through Git and the archived OpenSpec change, not through competing live design files.

## Migration Plan

1. Record the new Claude-inspired direction, typography roles, scope layers, palette, and unchanged Conversation boundary in `console/DESIGN.md`, replacing the old baseline in place.
2. Define centralized platform font role variables without adding bundled assets or runtime CDN requests.
3. Refactor centralized design tokens into base, Management Console, and Conversation Workspace layers while preserving compatibility for existing chat consumers.
4. Apply the Management scope to the global Header/navigation without changing layout behavior, menu semantics, collapse, logo handling, or `hideMenu` behavior.
5. Recalibrate `/models` and its dialogs/states using semantic management roles without changing handlers or workflows.
6. Run lint, tests, type/build checks, business-path checks, desktop and embedded visual review, Windows platform-font review, chat isolation review, and untouched-page leakage review.
7. Apply user feedback to both the implementation and the single `console/DESIGN.md`, validate OpenSpec, and archive the change after acceptance.

Rollback consists of reverting the theme/token, navigation, model-management, documentation, and spec changes as one change set. No data migration or backend rollback is required.

## Open Questions

No blocking design questions remain. Bundled multilingual font families, licensing, and subsetting remain deferred to a separate optional typography change.
