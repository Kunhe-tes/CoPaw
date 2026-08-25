# Submit Proposed Plan Flat Contract Design

## Goal

Make `submit_proposed_plan` expose and enforce the same shallow Goal Contract
shape used after user confirmation, so Goal Mode agents can construct valid
drafts without relying on hidden field names.

## Scope

The tool keeps four top-level arguments:

- `objective`: non-empty string.
- `completion_criteria`: a non-empty list of shallow objects.
- `constraints`: one shallow object.
- `autonomy_boundary`: non-empty string.

Each completion-criterion object has exactly four non-empty strings:
`requirement`, `observable_assertion`, `verification_method`, and
`expected_outcome`. The constraint object has exactly two string arrays:
`must_preserve` and `must_not_do`.

There is no additional request wrapper, no deeply nested type, and no
automatic conversion of legacy `criterion` or `verification` keys. Those keys
cannot provide all four required acceptance fields without inventing data.

## Design

`GoalProposal` will use the existing `CompletionCriterion` and
`GoalConstraints` domain models. This makes the proposal card and the
user-confirmed `GoalContract` share the same validation rules and produces an
accurate tool JSON schema. The existing manual dictionary-key validator will
be removed.

The tool preserves its optional JSON-text input path for compatibility, then
validates decoded input through `GoalProposal`. The tool signature will expose
the concrete shallow item and constraint types to schema consumers.

Goal Mode instructions will state the exact keys and a compact one-item
template. It will explicitly prohibit legacy aliases and arrays in string
fields.

## Error Handling

Pydantic will report failures at their field paths, such as a missing
`completion_criteria.0.expected_outcome` or an unexpected
`completion_criteria.0.verification_command`. No values are inferred or
silently discarded.

## Verification

- A valid four-field criterion and two-key constraint draft is accepted.
- The generated tool JSON schema exposes concrete criterion and constraint
  properties rather than arbitrary string dictionaries.
- Missing, extra, blank, and non-string criterion fields fail at their precise
  paths.
- JSON-text criteria and constraints remain accepted when they decode to the
  same valid shallow shape.
- The focused planning-tool test suite remains green.
