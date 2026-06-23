## Context

This change originally explored a Claude-inspired Console direction. During calibration, the accepted repository direction moved back to a CoPaw-first white embedded management baseline with `#3769FC` as the primary management and Conversation Workspace emphasis.

The follow-up change `enhance-console-design-with-impeccable` now supersedes this Claude-specific migration. Claude remains useful as a reference for restraint, hierarchy, spacing, boundaries, radii, editorial rhythm, and quiet confidence, but it is not the active palette, typography, or migration mandate.

## Goals / Non-Goals

**Goals:**

- Preserve this change as exploration history.
- Avoid leaving warm/coral Claude-specific requirements active beside the CoPaw-first design direction.
- Keep `console/DESIGN.md` as the only durable Console design authority.
- Let `enhance-console-design-with-impeccable` define the active CoPaw-first design-system and quality-gate direction.

**Non-Goals:**

- Continuing a separate Claude-inspired warm/coral implementation path.
- Replacing the current white-first embedded Management Console baseline.
- Changing Console UI implementation, APIs, routes, state semantics, permissions, iframe contracts, or business behavior.

## Decisions

### 1. Supersede this change with CoPaw-first direction

This change should not be completed as a distinct visual migration. Its artifacts are amended so that any remaining useful content is absorbed into the CoPaw-first baseline and the active follow-up change.

### 2. Keep Claude as reference input

Claude guidance may still inform restraint, boundaries, spacing, radii, rhythm, and quiet confidence. Those qualities must be rewritten as CoPaw-specific rules in `console/DESIGN.md` before they become authoritative.

### 3. Do not install or vendor external design documents

No Claude, Impeccable, or other third-party design document should be committed as a competing design authority. History belongs in Git and OpenSpec archives.

## Risks / Trade-offs

- **[Old artifacts confuse future work]** -> The specs and tasks are amended to point to the CoPaw-first direction and remove active warm/coral requirements.
- **[Useful exploration gets lost]** -> The historical context remains here, but operational rules move to `console/DESIGN.md` and `enhance-console-design-with-impeccable`.

## Migration Plan

1. Treat this change as superseded/absorbed.
2. Use `enhance-console-design-with-impeccable` as the active design-system direction.
3. Archive or otherwise close this change only after specs no longer assert a competing Claude-specific visual mandate.
