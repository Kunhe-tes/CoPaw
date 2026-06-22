## Context

CoPaw already has a Console design authority at `console/DESIGN.md`, a central token entry point at `console/src/config/consoleDesignTokens.ts`, and project-level rules that prevent external design documents from becoming competing authorities. Previous Claude-inspired work was a useful exploration of restraint, hierarchy, editorial rhythm, and quiet boundaries, but the owner now wants the durable design system to be the one that best fits CoPaw rather than one named external style.

Impeccable is useful because it gives AI agents a sharper design vocabulary and deterministic detector rules for common AI-generated UI problems. Its default setup also introduces `PRODUCT.md` and `DESIGN.md`, so the integration needs explicit boundaries before any tool installation happens.

## Goals / Non-Goals

**Goals:**

- Reframe `console/DESIGN.md` as a CoPaw-first design standard that can learn from Claude, Linear, Impeccable, and other references without adopting any of them wholesale.
- Add Impeccable-assisted quality gates for Console UI work while keeping `console/DESIGN.md` as the final authority.
- Define safe and risky Impeccable command categories for this repository.
- Plan detector and hook calibration before enabling automatic enforcement.
- Supersede the previously unfinished Claude-specific migration path so Claude remains available as a design reference without leaving a second active design mandate.
- Keep the first implementation documentation/tooling-only unless the accepted apply phase explicitly installs tool files.

**Non-Goals:**

- Replacing `console/DESIGN.md` with an Impeccable-generated `DESIGN.md`.
- Running `/impeccable init` as-is and committing a second root design manual.
- Redesigning any Console page or changing the current palette, typography, tokens, routing, APIs, state, permissions, iframe contracts, or business behavior.
- Resolving all open visual-direction questions in one pass. The quality gate should help future decisions converge through evidence.

## Decisions

### 1. Treat Impeccable as a reviewer, not an authority

`console/DESIGN.md` remains the authoritative source. Impeccable commands and detector output are used as critique inputs. If Impeccable flags something that CoPaw deliberately permits, the accepted rule belongs in `console/DESIGN.md` or `.impeccable/config.json`, not in ad hoc agent memory.

**Alternative considered:** let Impeccable generate a new project `DESIGN.md`. Rejected because it would conflict with the repository's single-authority rule and lose CoPaw-specific constraints.

### 2. Separate "design direction" from "quality gate"

The design direction answers what CoPaw should feel like: white-first embedded management console, Chinese operational density, clear Conversation Workspace identity, and incremental migration. The quality gate answers whether a specific AI-generated UI proposal has common design defects: nested cards, generic gradients, weak text contrast, text overflow, decorative excess, missing states, and unstable responsive behavior.

This lets the owner continue exploring visual references without repeatedly rewriting the enforcement mechanism.

### 3. Use a staged tool adoption path

The first apply step updates project documentation and specs. A later step may add `.impeccable/config.json` with calibrated ignores and design-system settings. Installing the Codex hook or vendored skill files should remain optional until the repository owner accepts the boundaries and understands which files will be added.

**Alternative considered:** install Impeccable immediately. Rejected because the current request is about reshaping the design standard, and hook installation changes the editing workflow.

### 4. Calibrate against CoPaw exceptions up front

Some Impeccable defaults are intentionally broad. CoPaw should explicitly allow or contextualize choices such as platform UI font stacks, white-first surfaces, neutral management text roles, `#3769FC`, and compact management density when they are documented project decisions. This avoids treating deliberate CoPaw choices as recurring detector noise.

### 5. Supersede the Claude-specific migration

The existing `adopt-claude-console-design` change previously remained in progress and still contained warm/coral Claude-specific intent in its artifacts, while the current `console/DESIGN.md` and token values reflected a white-first blue management baseline. Now that this CoPaw-first change is accepted, the Claude-specific change is reconciled instead of completed as a separate direction.

The reconciliation should update active specs so Claude is described as a useful reference for restraint, hierarchy, spacing, boundaries, and editorial rhythm, not as a required palette or standalone migration target. The old change can then be archived, superseded, or amended according to OpenSpec's archive workflow, but it must not remain as a competing active design plan.

## Risks / Trade-offs

- **[Detector noise creates fatigue]** -> Calibrate `.impeccable/config.json` only after reviewing actual findings on representative Console surfaces.
- **[External style churn continues]** -> Keep external references in a "reference inputs" section and require durable rules to be rewritten as CoPaw-specific principles.
- **[Hook installation surprises agents]** -> Do not install automatic hooks in the initial documentation phase; document approval and rollback steps first.
- **[Quality gate slows small UI fixes]** -> Scope mandatory Impeccable review to new UI, substantial visible changes, reusable visual rules, and pre-ship polishing; keep typo/doc-only work exempt.
- **[A tool-generated document competes with `console/DESIGN.md`]** -> Prohibit committing alternate live design manuals unless a future approved design-system change explicitly replaces the authority structure.
- **[The old Claude change remains active and confusing]** -> Reconcile and close or supersede `adopt-claude-console-design` after this direction is accepted.

## Migration Plan

1. Update `console/DESIGN.md` with a CoPaw-first reference model and an Impeccable-assisted quality gate.
2. Add a new OpenSpec capability for design quality gates and update the existing design-system capability.
3. Reconcile `adopt-claude-console-design` by syncing affected specs and marking the old direction as superseded, amended, or ready for archive under the CoPaw-first baseline.
4. Optionally add `.impeccable/config.json` in the apply phase only if the accepted task scope includes local detector calibration.
5. Run documentation/spec validation and, if any tool files are added, run the relevant detector command without changing UI code.
6. Defer Codex hook installation until after the owner confirms automatic post-edit feedback is desired.

Rollback consists of reverting the documentation/spec/tooling files added by this change. No runtime rollback is required because no product behavior changes are planned.

## Open Questions

- Should the first apply phase include a minimal `.impeccable/config.json`, or should it update documentation only and leave detector calibration to a follow-up after sampling real findings?
- Which exact OpenSpec archive/supersede mechanics should be used for `adopt-claude-console-design` after the CoPaw-first specs are synchronized?
