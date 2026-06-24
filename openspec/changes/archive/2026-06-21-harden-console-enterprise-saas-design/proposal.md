## Why

The Console now has a CoPaw-first design baseline, but it still needs a stricter enterprise SaaS quality bar so future AI-assisted UI work produces task-focused product screens instead of generic, decorative, or fragile pages. Impeccable can help as a detector and hardening framework, but the repository needs explicit local rules that turn that input into durable Console standards.

## What Changes

- Add minimal project product context so Impeccable can run as a skill without using `/impeccable init` or generating a competing root `DESIGN.md`.
- Strengthen `console/DESIGN.md` with enterprise SaaS product standards: task-first composition, compact operational density, stable component vocabulary, complete states, resilient text handling, and anti-slop boundaries.
- Clarify how Impeccable is used as an advisory review and hardening layer rather than a visual authority.
- Keep existing Console token values and UI implementation unchanged unless a later page-specific migration requires token recalibration.

## Capabilities

### New Capabilities

- `console-product-context`: Defines the strategic product context required for Impeccable-assisted Console design work without creating a competing visual design authority.

### Modified Capabilities

- `console-design-system`: Strengthens the design-system requirements for enterprise SaaS quality, product density, visual restraint, and resilient state handling.
- `console-design-quality-gate`: Clarifies manual Impeccable skill usage after local skill installation and keeps detector findings subordinate to `console/DESIGN.md`.

## Impact

- Adds `PRODUCT.md` as strategic product context only.
- Updates `AGENTS.md` to clarify that `PRODUCT.md` does not replace `console/DESIGN.md`.
- Updates `console/DESIGN.md`.
- Updates OpenSpec specs and this change's artifacts.
- No API, route, state, component, or token runtime behavior changes are intended.
