## 1. Theme Configuration Foundation

- [x] 1.1 Replace the Management Console token values with the approved neutral blue-gray palette and `#3769FC` primary roles.
- [x] 1.2 Add a root-level runtime bridge that maps the typed management tokens to stable CSS custom properties.
- [x] 1.3 Remove duplicated CSS palette declarations and document `consoleDesignTokens.ts` as the normal palette-edit entry point.

## 2. Calibrated Surface Migration

- [x] 2.1 Recalibrate global Header/navigation canvas, text, icons, selection, hover, focus, and collapse-control colors through semantic management roles.
- [x] 2.2 Recalibrate `/models` canvas, default LLM panel, provider cards, inputs, primary actions, status, and focus presentation to the blue-gray theme without changing layout.
- [x] 2.3 Recalibrate model-management dialogs, notices, disabled states, progress, and supporting surfaces without changing their triggers or behavior.
- [x] 2.4 Audit calibrated files and remove remaining warm cream/coral presentation literals that conflict with the new semantic palette.

## 3. Design Authority

- [x] 3.1 Rewrite the relevant reference, product-character, theme, color, interaction, navigation, management, model-reference, and verification sections of `console/DESIGN.md` for the embedding-first blue-gray direction.
- [x] 3.2 Preserve existing typography, spacing, density, radii, adaptive card, embedded layout, conversation isolation, and UI-only behavior rules.
- [x] 3.3 Document how future palette changes should be performed through semantic token values rather than page-level CSS edits.

## 4. Verification

- [x] 4.1 Run formatting, type checks, relevant tests, and the production build.
- [x] 4.2 Validate the OpenSpec change strictly and audit the calibrated source for obsolete warm/coral theme literals.
- [x] 4.3 Verify `/models` at the agreed desktop sizes and embedded layout for background continuity, card contrast, action hierarchy, clipping, and horizontal overflow.
- [x] 4.4 Verify a representative chat route retains its existing layout, behavior, and `#3769FC` Conversation Workspace identity.
