## Why

The current Console baseline is visually grounded in Vercel-style neutral grays, while the preferred product direction is now Claude's warmer, editorial visual language. CoPaw needs one updated design authority and a reusable scoped theme that can migrate non-conversation pages consistently without changing the established blue Conversation Workspace.

## What Changes

- Replace the Vercel-primary reference direction in the existing `console/DESIGN.md` with a Claude-inspired warm editorial system adapted for a dense Chinese AI management console.
- Keep `console/DESIGN.md` as the only durable UI design source of truth; do not add a second design document, preserve an old design baseline, or vendor Claude's external `DESIGN.md`.
- Define reusable UI, editorial, and technical font roles using Windows-safe and macOS-safe platform stacks, with no external font service dependency. Local multilingual font assets are deferred to a separate typography change.
- Split shared styling into base tokens, a Claude-inspired Management Console theme, and the existing independent Conversation Workspace theme so later non-chat migrations can reuse the new system and later chat work can evolve separately.
- Recalibrate the global Header and navigation plus the complete `/models` experience to the warm canvas, warm ink, restrained borders, and coral primary-action treatment.
- Preserve the current Conversation Workspace, including its independent conversation sidebar, typography, and fixed `#3769FC` emphasis, during this change.
- Preserve all APIs, routes, permissions, state semantics, iframe behavior, validation, triggers, error handling, and business-operation outcomes.
- Continue incremental adoption: non-chat legacy pages outside the trial remain unchanged until their own migration.

## Capabilities

### New Capabilities

- `console-theme-scoping`: Layered base, Management Console, and Conversation Workspace token scopes that enable future page migrations without leaking the Claude-inspired theme into chat.

### Modified Capabilities

- `console-design-system`: Change the primary external reference and reusable visual foundation to a Claude-inspired warm editorial system while retaining a single `console/DESIGN.md` authority and incremental adoption.
- `console-navigation-visuals`: Change the standalone global shell and navigation from cool neutral presentation to the scoped warm management theme without changing behavior or logo configuration.
- `model-management-visuals`: Recalibrate `/models` and its dialogs as the first complete Claude-inspired management-page reference while preserving all model-management behavior.

## Impact

- Documentation: `console/DESIGN.md` is replaced in place with the latest accepted baseline; OpenSpec design and delta specs record the migration decision but do not become competing UI authorities.
- Frontend foundation: role-based platform font stacks, semantic design tokens, Management Console scoping, and existing Conversation Workspace isolation.
- Trial surfaces: the global Header/navigation and `console/src/pages/Settings/Models/`, including related dialogs and visual states.
- Build output: no additional font assets and no runtime font CDN requests in this change.
- Compatibility: Windows Chrome and Edge are primary review targets, with macOS/system fallbacks retained; `hideMenu=true` remains supported.
- No backend API, data model, route, permission, or business-flow changes are intended.
