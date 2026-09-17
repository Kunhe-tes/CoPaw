# Context reference mention repair

## Scope

Repair five regressions in the chat `@` context-reference interaction without
changing its discovery API, grouping order, token formats, or keyboard model.

## Behaviour

1. Every menu row uses the same left-aligned icon/content column. Its text
   container consumes the remaining row width and truncates the title and
   secondary description to one line.
2. Selecting a reference replaces exactly the active `@…` trigger range. It
   must not create punctuation before the inserted token.
3. A successful selection clears the active trigger range and query state.
   Subsequent ordinary input must not reopen or search the menu until the user
   types another `@` trigger.
4. Request loading keeps the menu mounted and preserves its content geometry;
   stale responses remain ignored. This removes visible open/close flashing.
5. The no-results state is a centered, compact empty treatment with an icon and
   helper copy rather than an unstyled inline string.

## Implementation boundaries

- Limit production changes to `SkillMentions` and its token editor/hook.
- Keep 200ms debounce, fixed group order, vertical-only scrolling, existing
  key bindings, and structured context-reference submissions.
- Add regression tests for punctuation-free replacement, post-selection input,
  stable loading rendering, row alignment/truncation, and the empty state.

## Verification

- Run the focused SkillMentions, token-editor, sender, welcome, and chat tests.
- Run Prettier for changed TypeScript/TSX files.
- Run the existing focused backend context-reference tests.
