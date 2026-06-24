## Why

CoPaw Console currently contains multiple independently evolved visual languages across chat, configuration, and analytics pages, with extensive local styling and no shared frontend design contract. Establishing a versioned design system now provides a stable basis for gradual UI-only modernization while using the model-management page as a real implementation sample before broader adoption.

## What Changes

- Add `console/DESIGN.md` as the committed source of truth for CoPaw Console frontend design, using a light-theme system informed by Vercel's neutral foundation, Linear's restrained information hierarchy, optional Claude warmth, and CoPaw's existing product identity.
- Define shared visual foundations, the conversation-workspace pattern, and three management-console page templates while keeping adoption incremental for untouched legacy pages.
- Refine the existing global navigation and surrounding layout presentation without changing menu structure, route mapping, permissions, collapse behavior, branding assets, or iframe `hideMenu` behavior.
- Redesign the complete `/models` model-management experience, including the default LLM area, provider cards, search and actions, dialogs, loading, empty, error, disabled, and in-progress states.
- Preserve all existing APIs, stores, request parameters, event handlers, routing, iframe messaging, business rules, and operation semantics; the change is UI-only except for fixing unambiguous presentation defects such as leaked translation keys.
- Validate the design at desktop viewport sizes `1280x720`, `1440x900`, and `1920x1080`, including standalone and `hideMenu=true` embedded presentation, through two rounds of visual calibration before using the system for later page migrations.

## Capabilities

### New Capabilities

- `console-design-system`: Defines the committed design source of truth, visual foundations, page patterns, adoption boundaries, and UI verification rules for `console/`.
- `console-navigation-visuals`: Defines the light, low-distraction presentation of the existing global navigation while preserving its behavior and embedded-mode contract.
- `model-management-visuals`: Defines the redesigned presentation and complete visual-state coverage of the `/models` management experience without changing model or provider operations.

### Modified Capabilities

None.

## Impact

- Affected documentation: new `console/DESIGN.md` with external reference links but no vendored third-party design documents.
- Affected frontend areas: shared visual tokens and scoped styling, `console/src/layouts/`, `console/src/pages/Settings/Models/`, and closely related presentational components.
- Existing Ant Design, Less/CSS Modules, system fonts, `@agentscope-ai/icons`, and Lucide dependencies remain in use; no external font or new visual regression dependency is introduced.
- Existing dark-theme code remains untouched by this change, but the new design requirements and newly redesigned surfaces target light theme only.
- Existing backend APIs, routing, iframe integration, authentication, provider/model state, and business behavior are not changed.
