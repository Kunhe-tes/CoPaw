# Plan Interaction Cards Visual Design

## Goal

Restyle `PlanInteractionCards` as a restrained, light tool interface. The
surface uses white and very light blue-gray, blue is reserved for primary
interaction and explicit state, and muted blue-gray carries supporting
information.

The work changes presentation only. Card selection, form navigation, keyboard
handling, submission payloads, dismissal, and composer replacement behavior
remain unchanged.

## Direction

Use the approved "balanced workspace" direction:

- White cards on a very light blue-gray surrounding surface.
- 8px card and control corners, 1px cool-gray borders, and a subtle cool
  shadow.
- Wide horizontal option rows with a distinct selected state.
- Blue appears on required labels, primary buttons, focus rings, selected
  option borders, selected option backgrounds, and checkmarks.
- Supporting copy, page indicators, keyboard hints, and secondary actions use
  neutral blue-gray.

## Tokens

The component stylesheet defines shared card-level custom properties so the
clarification and review cards stay visually aligned.

| Role | Light value | Usage |
| --- | --- | --- |
| Card surface | `#FFFFFF` | Main card background |
| Soft surface | `#F5F9FF` | Review summary and restrained contextual backgrounds |
| Border | `#DCE6F2` | Cards, choices, and inputs at rest |
| Primary blue | `#1677FF` | Primary actions and selected state |
| Selected surface | `#F0F7FF` | Selected option row |
| Main text | `#1C395B` | Headings and selected copy |
| Secondary text | `#72839A` | Help, page number, shortcuts, and secondary actions |

The existing dark-mode selectors receive equivalent blue-gray tokens while
preserving their existing contrast and component structure.

## Clarification Card

The header keeps the current single-line hierarchy: question, required tag,
and page controls. Required is a compact blue-on-soft-blue label. Page controls
and their disabled state remain low priority in cool gray.

Every option remains a full-width button. Resting rows are white with a
cool-gray border and blue-gray copy. A selected row has all three state cues:

1. `#1677FF` border.
2. `#F0F7FF` background.
3. Blue circular checkmark at the right edge.

Hover may lightly tint the row. Keyboard focus uses an outer blue focus ring,
separate from the selected treatment. Inputs keep a white surface, cool-gray
border, and a blue border plus soft blue focus ring.

The footer keeps its current semantic hierarchy: shortcut help and exit are
muted; the continuation action is a solid blue 6px-radius button. Mobile keeps
the current vertical footer layout and adequate control height.

## Plan Review Card

The review card shares the same card, border, typography, focus, and button
tokens. Its summary becomes a soft-blue information panel with a 3px blue left
rule. Plan details remain quiet white sections with cool-gray borders so blue
continues to identify priority rather than decoration.

The primary review decision uses the same solid blue button as clarification.
The secondary decision remains text-only blue-gray and gains a visible blue
focus ring for keyboard access.

## Scope And Verification

Implementation is limited to
`console/src/pages/Chat/components/PlanInteractionCards.module.less` unless a
small semantic hook is required for an existing visual state. No response data,
event, state, or submission behavior changes are expected.

Verification covers the existing interaction test suite plus visual inspection
at desktop and mobile widths. The acceptance criteria are:

- Light mode contains no residual olive or green interaction color.
- Selected rows present border, fill, and checkmark together.
- Required, primary buttons, and keyboard focus use the shared blue accent.
- Supporting information remains visually subordinate to question and action.
- Existing submission, dismissal, pagination, custom response, and review
  decisions retain their current behavior.
