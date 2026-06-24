## 1. OpenSpec Artifacts

- [x] 1.1 Create proposal, design, delta specs, and implementation tasks for the enterprise SaaS hardening direction.
- [x] 1.2 Validate the new change and affected specs.

## 2. Impeccable Context

- [x] 2.1 Add minimal `PRODUCT.md` strategic context for Impeccable-assisted Console design work.
- [x] 2.2 Update repository guidance so `PRODUCT.md` is strategic context and `console/DESIGN.md` remains the visual source of truth.
- [x] 2.3 Re-run the Impeccable context loader to confirm it no longer blocks on missing product context.

## 3. Console Design System Hardening

- [x] 3.1 Update `console/DESIGN.md` with enterprise SaaS quality-bar rules.
- [x] 3.2 Add production hardening requirements for dynamic text, CJK content, empty/error/loading/permission states, responsive overflow, and embedded mode.
- [x] 3.3 Confirm central token values do not require changes for this documentation-only hardening pass.

## 4. Verification

- [x] 4.1 Run OpenSpec validation for the new change and affected specs.
- [x] 4.2 Run a local Impeccable detector or context check where applicable and document any limitations.
- [x] 4.3 Review git status to confirm the scope only includes expected documentation, OpenSpec, and local-tool context changes.
