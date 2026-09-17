# Plan review card message placement

## Goal

Render a `submit_proposed_plan` review card immediately after the assistant message that carries it, instead of above the chat composer.

## Design

The Chat message renderer will recognize `plan_review` card metadata and render the existing interactive `PlanReviewCard` in that message's content flow. The composer will no longer render `ActivePlanReviewCard`.

The existing card callbacks and decision-submission behavior are unchanged. After a decision is recorded, replayed history continues to render the existing read-only snapshot state.

## Scope and verification

Only Console chat rendering and its tests change. The backend tool contract, card metadata format, and plan-review actions do not change.

Tests will prove that an active review card appears after its originating assistant message, does not appear in the composer, and remains actionable.
