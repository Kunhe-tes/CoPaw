## 1. Design Authority Update

- [x] 1.1 Update `console/DESIGN.md` to frame CoPaw's Console design direction as CoPaw-first, with Claude, Linear, Impeccable, and other references treated as inputs rather than mandates.
- [x] 1.2 Add an Impeccable-assisted quality gate section covering routine review commands, cautious commands, detector reconciliation, and the rule that `console/DESIGN.md` remains authoritative.
- [x] 1.3 Document that generated `PRODUCT.md`, generated `DESIGN.md`, or other external design manuals must not be committed as competing authorities without a separate approved design-system change.

## 2. Detector And Tooling Plan

- [x] 2.1 Decide whether this apply phase adds documentation only or also adds a minimal `.impeccable/config.json` for detector calibration.
- [x] 2.2 If detector config is added, encode narrow CoPaw allowances for documented choices such as platform fonts, white-first management surfaces, neutral text roles, compact density, and `#3769FC`.
- [x] 2.3 Leave Codex hook installation disabled unless the owner explicitly approves adding `.codex/hooks.json` and Impeccable skill assets in this change.

## 3. Verification

- [x] 3.1 Validate the OpenSpec change after editing docs and any optional tooling files.
- [x] 3.2 If `.impeccable/config.json` is added, run a manual detector command against representative Console source files and record any noisy findings for follow-up calibration.
- [x] 3.3 Confirm no Console UI implementation, API contract, route, permission, iframe message, store semantics, or business behavior changed.
- [x] 3.4 Review the still-open `adopt-claude-console-design` change after this CoPaw-first direction is accepted and decide the exact OpenSpec closeout path.
- [x] 3.5 Synchronize affected specs so `adopt-claude-console-design` is archived, superseded, or amended without leaving warm/coral Claude-specific requirements active beside the CoPaw-first baseline.
- [x] 3.6 Confirm Claude remains documented only as a reference input for restraint, hierarchy, spacing, boundaries, and editorial rhythm unless a future approved design-system change says otherwise.
