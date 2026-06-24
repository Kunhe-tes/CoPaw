## Context

`console/DESIGN.md` is the committed visual source of truth for Console UI. The repository owner wants a stricter, high-quality enterprise SaaS direction that avoids generic AI-generated frontends, marketing-page composition, decorative gradients, vague card piles, and brittle layouts. Impeccable has been installed locally under `.agents/skills/impeccable`, but its context loader expects product context before its commands can run cleanly.

The current Console token file already defines the white-first management palette, blue action role, platform font stack, radii, shadows, and CSS variables documented by `console/DESIGN.md`. This change should therefore harden the written standard first, not force a token migration without a visual reason.

## Goals / Non-Goals

**Goals:**

- Make CoPaw's desired product character explicit: advanced, quiet, dense, enterprise SaaS, and task-oriented.
- Allow Impeccable to function as a local skill by adding strategic product context while preserving `console/DESIGN.md` as the only visual design authority.
- Add durable hardening rules for real product conditions: long text, CJK content, empty states, permissions, loading, errors, disabled states, responsive overflow, and embedded mode.
- Keep future UI generation anchored to local tokens and existing patterns.

**Non-Goals:**

- Do not run `/impeccable init`.
- Do not create a root visual `DESIGN.md` or copy Impeccable's generated design format into the repository.
- Do not change implemented Console pages, routes, APIs, stores, permissions, or business behavior.
- Do not install automatic hooks as a required gate.
- Do not replace `console/src/config/consoleDesignTokens.ts` values without a visual review-backed need.

## Decisions

1. Add `PRODUCT.md` as strategic context only.

   Rationale: Impeccable's skill loader treats missing `PRODUCT.md` as a setup blocker. A small product-context file resolves that blocker while keeping visual rules in `console/DESIGN.md`. Alternative considered: run `/impeccable init`; rejected because it would generate root design context and risk competing authority.

2. Strengthen `console/DESIGN.md` instead of generating a new design document.

   Rationale: Repository rules already make `console/DESIGN.md` the source of truth. Updating it preserves one authority and lets future page migrations inherit a better standard. Alternative considered: maintain an Impeccable-specific design doc; rejected because it would split guidance across documents.

3. Treat Impeccable as an advisory detector and review skill.

   Rationale: The detector is useful for generic AI UI smells and production hardening issues, but CoPaw-specific choices such as white-first embedding, compact Chinese management density, platform fonts, and `#3769FC` must remain intentional local decisions.

4. Leave tokens unchanged in this change.

   Rationale: The current token values match the accepted white-first embedded direction. Changing token values without a target surface review would create unnecessary UI blast radius. Future page-specific work can recalibrate tokens with viewport verification.

## Risks / Trade-offs

- Root `PRODUCT.md` could be mistaken for a visual design authority -> Mitigation: explicitly state that it is strategic context and that `console/DESIGN.md` owns Console UI design.
- Impeccable may still report findings that conflict with local rules -> Mitigation: document reconciliation rules and require updates to `console/DESIGN.md` or detector configuration for recurring valid findings.
- A stricter design standard can slow future quick UI edits -> Mitigation: keep adoption incremental and require full verification only for major desktop UI changes.
- Token values may later prove insufficient for all pages -> Mitigation: require token/documentation/visual verification updates together in a future scoped change.
