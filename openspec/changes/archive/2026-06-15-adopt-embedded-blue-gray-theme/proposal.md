## Why

The current warm cream and coral Management Console palette does not integrate cleanly with the host products where CoPaw is embedded. The Console now needs an embedding-first neutral blue-gray palette aligned with the existing `#3769FC` product blue, plus one maintainable theme configuration surface for later color calibration.

## What Changes

- Replace warm cream management backgrounds, warm borders, warm ink, and coral actions with a neutral light blue-gray palette and `#3769FC` primary actions.
- Treat embedded presentation as the only color target for the current Management Console baseline; no separate standalone palette is maintained.
- Keep the existing Claude-inspired layout restraint, spacing, density, radii, card composition, typography, and responsive behavior while removing Claude's warm color direction as a requirement.
- Make `consoleDesignTokens.ts` the authoritative management-theme configuration and apply those values to CSS variables from application code instead of duplicating theme hex values in CSS.
- Recalibrate the global shell/navigation and `/models` surfaces, dialogs, focus states, active states, and buttons through semantic theme roles only.
- Update `console/DESIGN.md` in place as the single current design authority.
- Preserve the Conversation Workspace layout and behavior; its existing `#3769FC` identity remains unchanged.
- Preserve all routes, APIs, permissions, iframe contracts, handlers, validation, state semantics, error handling, and business outcomes.

## Capabilities

### New Capabilities

- `console-theme-configuration`: A single typed management-theme configuration that supplies runtime CSS variables and documents how later palette changes are made without editing page styles.

### Modified Capabilities

- `console-design-system`: Replace the mandatory warm editorial palette with an embedding-first neutral blue-gray palette while retaining the accepted structural and interaction rules.
- `console-navigation-visuals`: Change global navigation backgrounds, selection, hover, focus, icon, and text colors to the neutral blue-gray management theme.
- `model-management-visuals`: Change `/models` panels, cards, controls, dialogs, and primary actions to the neutral blue-gray management theme without changing layout or behavior.

## Impact

- Documentation: `console/DESIGN.md` and this change's OpenSpec artifacts.
- Theme foundation: `console/src/config/consoleDesignTokens.ts`, the application theme-variable bridge, and `console/src/styles/console-theme.css`.
- Calibrated surfaces: global Header/navigation and `console/src/pages/Settings/Models/` including related dialogs.
- Compatibility: the embedded page remains light-only and uses `#3769FC`; no font assets or external theme dependencies are introduced.
- No backend, route, API, data, permission, or workflow changes are intended.
