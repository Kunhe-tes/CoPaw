## Context

The current in-progress Console redesign established reusable layout, density, typography, card, radius, and isolation rules, but coupled the Management Console theme to Claude-inspired cream surfaces and coral actions. CoPaw is now evaluated primarily as embedded content inside blue-branded host products, where that warm palette appears unrelated to the surrounding product.

Management colors currently exist in both `consoleDesignTokens.ts` and literal CSS custom-property declarations. That duplication makes calibration error-prone: changing the TypeScript token object does not automatically update Less/CSS consumers, and page-specific literals can drift from both sources.

This change is presentation-only. The Conversation Workspace already uses `#3769FC`; its layout, typography, and behavior remain outside scope. The global shell and `/models` remain the calibrated management reference surfaces.

## Goals / Non-Goals

**Goals:**

- Replace warm cream/coral management colors with a neutral light blue-gray palette centered on `#3769FC`.
- Optimize the management baseline for embedding only; do not maintain a separate standalone color identity.
- Make one typed token object the source of truth for management colors and expose it to CSS variables at application startup.
- Keep existing layout, spacing, radii, card adaptation, typography, navigation hierarchy, and interaction behavior.
- Update `console/DESIGN.md`, navigation, `/models`, and management dialogs consistently.

**Non-Goals:**

- Redesigning chat, changing its blue emphasis, or merging management and conversation component styles.
- Adding runtime theme switching, host-controlled arbitrary colors, dark mode, or multiple named palettes.
- Changing routes, iframe messages, APIs, permissions, state, validation, handlers, or business outcomes.
- Migrating untouched management pages beyond shared shell effects.

## Decisions

### 1. Use one embedding-first palette

The management palette will use:

- canvas `#F5F7FB`;
- surface `#FFFFFF`;
- subtle surface `#F0F3F9`;
- navigation `#F7F8FC`;
- border `#E2E7F0`;
- strong border `#CBD3E1`;
- text `#1D2433`;
- secondary text `#566074`;
- muted text `#8992A3`;
- primary `#3769FC`;
- primary hover `#2957DC`;
- primary soft `#EAF0FF`.

This palette is cool enough to integrate with the host brand while remaining light and low-distraction. Pure white is reserved for cards, dialogs, and interactive surfaces; the blue-gray canvas separates CoPaw content from host chrome without looking like a second brand.

**Alternative considered:** neutral gray without blue. Rejected because it weakens continuity with the existing `#3769FC` host and conversation identity. **Alternative considered:** host-injected arbitrary theme variables. Deferred because the user wants one direct palette and arbitrary host input would require compatibility and contrast guarantees.

### 2. Keep structural Claude influence, remove color dependence

Claude remains a reference for restraint, information hierarchy, spacing, soft boundaries, and radius usage. It is no longer the palette authority. `console/DESIGN.md` will describe CoPaw as an embedding-first blue-gray management system rather than a warm editorial system.

### 3. Treat TypeScript tokens as the color authority

`CONSOLE_MANAGEMENT_TOKENS` will remain the editable configuration surface. Application startup will serialize the approved token fields into root CSS custom properties through `document.documentElement.style.setProperty` before React renders. `console-theme.css` will provide structural rules, while calibrated components consume variables rather than duplicate palette literals.

Future palette changes should normally edit only `consoleDesignTokens.ts`, update the documented role table, and run visual/contrast verification.

**Alternative considered:** generate a CSS file during build. Rejected because it adds tooling for a small token set. **Alternative considered:** keep TypeScript and CSS synchronized manually. Rejected because it preserves the current drift risk.

### 4. Recalibrate scoped surfaces only

The global Header/navigation and `/models` will replace coral and warm literals with semantic variables. Status colors retain their semantic meaning. Conversation files will not be edited, and management variables remain separately named even though both themes currently share `#3769FC` as a primary color.

## Risks / Trade-offs

- **[Blue appears overused]** -> Reserve saturated blue for primary actions, focus, and concise selected states; use pale blue-gray for large surfaces.
- **[Runtime variable application causes a flash]** -> Apply variables synchronously during application startup before React renders.
- **[Page literals preserve warm colors]** -> Search calibrated files for old palette values and replace presentation literals with semantic variables where applicable.
- **[Shared shell changes affect chat adjacency]** -> Keep Conversation Workspace content unscoped and verify chat retains its current layout and interaction presentation.
- **[One palette limits future host branding]** -> Keep semantic token roles stable so a later approved change can replace values without rewriting page styles.

## Migration Plan

1. Add the neutral blue-gray values to the typed management token object and add a root CSS-variable bridge.
2. Remove duplicated management palette declarations from CSS and replace calibrated warm/coral literals with semantic roles.
3. Recalibrate Header/navigation, `/models`, and management dialogs without changing structure or handlers.
4. Rewrite the affected color/reference sections of `console/DESIGN.md` and document the future palette-edit workflow.
5. Run formatting, type checks, tests, production build, strict OpenSpec validation, palette-literal audit, and embedded visual review.

Rollback consists of reverting the token values, variable bridge, scoped presentation changes, and documentation. No backend or data rollback is required.

## Open Questions

No blocking questions remain. Host-controlled multi-brand theming is explicitly deferred.
