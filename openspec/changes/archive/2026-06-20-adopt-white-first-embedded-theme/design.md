## Context

The current Management Console theme is centralized in `CONSOLE_MANAGEMENT_TOKENS` and bridged to Less/CSS through root CSS custom properties. That architecture already supports direct palette recalibration without editing page-level selectors.

The previous embedded blue-gray palette improved separation compared with the earlier warm Claude-inspired direction, but the user now needs CoPaw to sit inside white host products. A visible blue-gray canvas makes the embedded Console feel like a separate nested product instead of part of the host page.

## Goals / Non-Goals

**Goals:**

- Make the Management Console theme white-first for white host embedding.
- Preserve a small amount of internal hierarchy through near-white subtle surfaces, neutral borders, and restrained blue feedback.
- Keep `#3769FC` as the management primary action color and the unchanged Conversation Workspace emphasis color.
- Update `console/DESIGN.md` and OpenSpec requirements so there is one current design authority.
- Keep the change UI-only and token/documentation scoped.

**Non-Goals:**

- Redesigning `/models` layout, provider-card structure, spacing, radii, or adaptive grid behavior.
- Changing chat, conversation sidebar, composer, or generated-content presentation.
- Adding runtime theme switching, host-provided arbitrary theming, dark mode, or multiple named palettes.
- Changing business logic, APIs, stores, permissions, iframe contracts, validation, or handlers.

## Decisions

### 1. Use a white-first embedded palette

The approved management palette is:

- canvas `#FFFFFF`;
- surface `#FFFFFF`;
- subtle surface `#F7F9FC`;
- navigation `#FFFFFF`;
- border `#E5E7EB`;
- strong border `#D0D7E2`;
- text `#111827`;
- secondary text `#4B5563`;
- muted text `#8A94A6`;
- primary `#3769FC`;
- primary hover `#2957DC`;
- primary soft `#EEF4FF`.

Pure white is used for the embedded page and navigation so CoPaw can merge with white host shells. `#F7F9FC` remains available for functional panels such as the Default LLM configuration so internal grouping is still legible.

### 2. Keep the primary action blue fixed

The blue action identity stays `#3769FC`. The problem being solved is large-area background mismatch, not the primary action brand. Keeping blue fixed also preserves continuity with the Conversation Workspace.

### 3. White global navigation with light boundaries

Global navigation becomes white instead of blue-gray, but it retains a subtle right border and shallow blue selected/hover/focus feedback. Fully borderless navigation was rejected because it can blur with the content area on white hosts.

### 4. Update tokens and documentation only

The implementation should change semantic token values and documentation/spec text. Existing components already consume CSS variables and token roles, so layout and behavior do not need structural edits.

### 5. Keep dropdown overlays aligned with the white-first theme

Management select dropdown overlays should use white elevated panels, near-white hover states, and primary-soft selected states. The default neutral gray selected fill was rejected because it visually conflicts with the white-first embedded baseline.

## Risks / Trade-offs

- **[Too much white reduces hierarchy]** -> Keep near-white `colorSurfaceSubtle`, neutral borders, and shallow blue selected states.
- **[White navigation blends into content]** -> Retain the navigation/content border and active-item treatment.
- **[Blue becomes too prominent on white]** -> Reserve saturated blue for primary actions, focus, and concise selected states.
- **[Existing staged design-system work is in progress]** -> Apply this as a small delta on top of the current token architecture without touching unrelated staged content.

## Migration Plan

1. Update the typed Management Console palette values.
2. Update `console/DESIGN.md` from blue-gray baseline language to white-first embedded baseline language.
3. Update OpenSpec delta requirements for the design system, navigation, theme configuration, and model management.
4. Calibrate management select dropdown overlays where component-library defaults conflict with the white-first theme.
5. Run formatting, type checks, relevant token tests, strict OpenSpec validation, and a source audit for stale blue-gray baseline wording.

Rollback is limited to restoring the previous token values and documentation/spec text.
