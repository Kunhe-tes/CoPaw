# W+ SOP question layout and multi-select plan

## Problem and scope

Long question prompts can collide with the required marker because the legend
renders the number, prompt, and metadata as unstructured flex text. The W+ SOP
contract already supports `multi_select`, but the workspace does not visibly
identify the question type.

This change is limited to the question header layout and visible type metadata.
It preserves the existing question schema, answer payload, validation, API
routes, and state-machine behavior.

## Implementation units

### 1. Resilient question heading

Files:

- `console/src/pages/WPlusSopWorkspace/index.tsx`
- `console/src/pages/WPlusSopWorkspace/index.module.less`
- `console/src/pages/WPlusSopWorkspace/index.test.tsx`

Decisions:

- Give the question prompt its own shrinkable, wrapping element.
- Keep the question number and metadata compact and non-shrinking.
- Allow the metadata group to wrap below the prompt in narrow containers
  without causing horizontal page overflow.

Test scenarios:

- A long Chinese prompt is rendered in a dedicated wrapping element.
- Required and question-type metadata remain independently addressable.

### 2. Explicit multi-select affordance

Files:

- `console/src/pages/WPlusSopWorkspace/index.tsx`
- `console/src/pages/WPlusSopWorkspace/index.module.less`
- `console/src/pages/WPlusSopWorkspace/index.test.tsx`

Decisions:

- Show `多选` for `multi_select` and `单选` for `single_select` in the
  question heading; free-text questions need no redundant type label.
- Continue using `Checkbox.Group` and the existing array/structured answer
  payload for multi-select questions.
- Render option descriptions consistently for both radio and checkbox options.

Test scenarios:

- Multi-select questions expose checkboxes, allow multiple checked options,
  show `多选`, and submit every selected option ID.
- Single-select questions show `单选` and remain radio-based.
- Custom-input multi-select answers retain their existing structured payload.

## Verification

- Run the focused W+ workspace test file.
- Run ESLint and Prettier checks for the changed files.
- Run the Console TypeScript/Vite test build.
- Run GitNexus `detect-changes` and inspect the final diff.
