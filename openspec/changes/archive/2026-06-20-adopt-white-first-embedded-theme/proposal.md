## Why

CoPaw is primarily embedded into white host products, and the current blue-gray management canvas can read as a separate framed application inside those hosts. The management design baseline should shift to a white-first embedded theme while preserving internal hierarchy, the `#3769FC` action identity, and UI-only behavior boundaries.

## What Changes

- Replace the Management Console color baseline with a white-first embedded palette:
  - white canvas and navigation;
  - white operational surfaces;
  - near-white gray-blue subtle surfaces;
  - neutral gray borders and text;
  - unchanged `#3769FC` primary action roles.
- Update `console/DESIGN.md` so the white-first embedded theme is the single latest design authority.
- Keep Claude as a structural reference only and continue to reject warm cream/coral palette roles.
- Preserve existing layout, density, radii, adaptive provider-card behavior, typography, routes, handlers, iframe behavior, and chat presentation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `console-design-system`: Replace the blue-gray management palette requirement with the white-first embedded palette baseline.
- `console-navigation-visuals`: Require white global navigation with restrained boundaries and shallow blue selected/focus states.
- `console-theme-configuration`: Clarify that palette changes continue through the typed token authority and must support white-first embedded calibration.
- `model-management-visuals`: Replace the blue-gray `/models` palette requirement with white-first page canvas, white cards, near-white functional panels, and blue primary actions.

## Impact

- Affected code:
  - `console/src/config/consoleDesignTokens.ts`
  - `console/DESIGN.md`
  - OpenSpec design-system specs
- No API, route, permission, iframe message, state, event-handler, validation, error-handling, or business-operation changes.
- No chat theme or layout changes.
