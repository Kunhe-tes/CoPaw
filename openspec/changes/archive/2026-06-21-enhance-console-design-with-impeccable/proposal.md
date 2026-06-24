## Why

CoPaw's Console design direction has been evolving through external references, including Claude-inspired exploration, but the project now needs a steadier way to discover and enforce the design language that best fits its own product. Impeccable can strengthen AI-assisted UI quality checks, but it must be integrated as a supporting review layer rather than replacing `console/DESIGN.md` as the single design authority.

## What Changes

- Clarify that `console/DESIGN.md` remains the only committed Console design authority while external references, including Claude and Impeccable, are treated as inputs to a CoPaw-specific standard.
- Add an Impeccable-assisted quality gate to the Console design workflow, focused on AI-generated UI risks such as low-contrast text, nested cards, excessive rounding, decorative gradients, cramped layouts, weak typography, overflow, and incomplete interaction states.
- Document which Impeccable commands are recommended for Console work and which commands require caution because they can generate competing design context or shift product identity.
- Plan a later, explicit tool-install step for `.impeccable/config.json`, optional Codex hook setup, and detector calibration after the design authority boundaries are accepted.
- Supersede the previously unfinished `adopt-claude-console-design` direction after this change is accepted, synchronizing the affected specs so Claude remains a reference input rather than a parallel design mandate.
- Keep this change documentation/tooling-only: no Console UI redesign, theme replacement, route change, API change, state semantics change, or business behavior change.

## Capabilities

### New Capabilities

- `console-design-quality-gate`: Defines how Impeccable-assisted design review, detector configuration, and optional hooks fit into Console UI work without becoming a competing design authority.

### Modified Capabilities

- `console-design-system`: Clarifies that CoPaw's design system may learn from external references and AI design tools while preserving `console/DESIGN.md` as the single source of truth and CoPaw-specific constraints as the final decision layer.

## Impact

- Documentation: `console/DESIGN.md` will gain Impeccable-assisted review guidance and stronger language about evaluating external references against CoPaw's product needs.
- OpenSpec: adds one new quality-gate capability and updates the existing Console design-system capability.
- Existing design migration state: the previously unfinished `adopt-claude-console-design` change is reconciled so its warm/coral Claude-specific requirements do not remain active beside the CoPaw-first design direction.
- Tooling plan: may later add `.impeccable/config.json` and optionally install the Impeccable Codex skill/hook, but only after the user accepts the proposal and apply phase starts.
- No frontend runtime behavior, UI implementation, API contracts, routes, permissions, iframe messages, stores, tests, or build outputs are intended to change in this proposal phase.
