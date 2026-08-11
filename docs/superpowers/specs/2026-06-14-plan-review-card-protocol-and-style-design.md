# Plan Review Card Protocol and Style Design

## Context

Plan Mode uses two Plan Interaction Tools:

- `ask_plan_clarification` asks the user for missing planning information.
- `submit_proposed_plan` presents a Proposed Plan for a Plan Review Decision.

The current `submit_proposed_plan` review card still renders with a generic
`OperateCard`/AntD shape and includes `open_questions` and `confidence` fields.
Those two fields do not drive the user's Plan Review Decision. If the Main
Agent still has unresolved questions, it should ask them through
`ask_plan_clarification` before it submits a Proposed Plan.

## Goals

- Remove `open_questions` and `confidence` from the Proposed Plan protocol,
  persisted model, accepted-plan execution context, and frontend card contract.
- Redesign the `submit_proposed_plan` frontend card to visually match the
  `ask_plan_clarification` card style while keeping it in the normal chat
  message stream.
- Preserve the current Plan Review Decision behavior: `revise`, `execute`, and
  `exit_plan` continue to submit the same decision payload shape.
- Keep keyboard behavior unchanged. Do not migrate Enter/Escape shortcuts from
  the clarification card to the review card.

## Non-Goals

- Do not support legacy `open_questions` or `confidence` fields. This feature
  has not launched, so the protocol can change cleanly.
- Do not add semantic backend validation that tries to infer whether the plan
  still contains unresolved questions. The model is guided by tool schema and
  tool description; the backend only rejects old protocol fields by using
  strict models.
- Do not replace or hide the normal chat input when rendering the plan review
  card. Only `ask_plan_clarification` keeps its existing composer-adjacent
  active-card behavior.

## Domain Model

`Proposed Plan` contains:

- `plan_id`
- `title`
- `summary`
- `steps[]`
- `risks[]`
- `verification[]`

`open_questions[]` and `confidence` are no longer part of the Proposed Plan
domain language, the tool protocol, or the user-facing card.

## Backend Design

`ProposedPlanCreate` removes `open_questions` and `confidence`. Because the
plan models already forbid unknown fields, calls that still send those old
fields fail validation instead of being silently accepted.

`PlanReviewCard.from_plan()` emits only the retained fields. The plan store
continues writing the full `ProposedPlan` model to JSON, but the model no
longer contains the removed fields.

`submit_proposed_plan` accepts only:

- `title`
- `summary`
- `steps`
- `risks`
- `verification`

Its tool description should state that the Main Agent must not call the tool
while unresolved planning questions remain; it should call
`ask_plan_clarification` first.

Accepted-plan execution context removes `open_questions` and `confidence`, so
normal execution receives only the fields that belong to the accepted plan.

## Frontend Design

`ChatPlanReviewCardData` and `normalizePlanInteractionCard()` require only the
retained Proposed Plan fields. Cards containing the old fields are not treated
as valid through a compatibility path.

`PlanReviewCard` keeps the current long-form information structure:

- header with title and summary
- list sections for Steps, Risks, and Verification
- feedback textarea
- decision buttons for continuing modification, executing, and exiting Plan
  Mode

The component stops using the generic `OperateCard` visual wrapper for this
scenario. It uses the same design language as `PlanClarificationCard`:

- soft olive card background
- rounded border and subtle shadow
- muted section labels and compact spacing
- matching textarea focus style
- matching weak-button and primary-button colors, hover states,
  focus-visible state, and disabled state

`Execute` is the primary action. `Continue modifying` and `Exit Plan Mode` are
secondary actions. The labels can remain in the current language for this
change unless the surrounding UI is already localized.

## Interaction Design

Decision behavior remains unchanged:

- `revise` submits `mode: "plan"` and includes optional feedback.
- `execute` submits `mode: "normal"` and accepts the persisted Proposed Plan.
- `exit_plan` submits `mode: "normal"` and exits Plan Mode without starting
  execution by default.

After any decision is submitted, the card stores the submitted `plan_id` in
session storage and disables duplicate decisions.

The review card does not add Enter or Escape keyboard shortcuts. This avoids
accidental execution or exit while the user is typing feedback.

## Testing

Backend tests should verify:

- `ProposedPlanCreate` requires the retained fields and rejects removed fields.
- `submit_proposed_plan` persists a plan and returns a review card without
  `open_questions` or `confidence`.
- Accepted-plan context excludes removed fields.
- Console plan decision recording still returns accepted context for execute.

Frontend tests should verify:

- plan review metadata extracts without the removed fields.
- old cards that only satisfy the old protocol are rejected.
- the review card renders title, summary, Steps, Risks, Verification, and
  feedback.
- review decisions still submit the same decision metadata and disable
  duplicates.
- the card uses the new review-card structure and action classes rather than
  the generic `OperateCard` mock path.

## Rollout

This is a clean protocol change because the feature has not launched. No data
migration or legacy card rendering compatibility is required.
