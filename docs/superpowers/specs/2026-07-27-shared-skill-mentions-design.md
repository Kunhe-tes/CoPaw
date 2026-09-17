# Shared Console Skill Mentions Design

## Goal

Make the Console welcome composer and the established conversation composer provide the same trusted `@skill` selection experience without duplicating interaction logic.

## Scope

- Preserve the current server contract: the browser submits only `selected_skill_names`; the server continues to resolve and validate skills.
- Support the existing trigger grammar: a trailing `@keyword` at input start or after whitespace.
- Support effective-skill loading, case-insensitive name filtering, click/Enter selection, Escape dismissal, removable labels, and a five-selection maximum in both composers.
- Preserve the welcome page's existing attachment upload and Enter-to-send behavior.

## Architecture

Create a focused shared skill-mention controller in `console/src/components/agentscope-chat/` that owns only composer-local interaction state: open state, query extraction, filtered candidates, and text replacement after a selection. It receives the parent-owned `skillMentions` data contract and reports new text plus selected names through callbacks.

`Sender` consumes that controller instead of owning an independent regex/menu/keyboard implementation. `WelcomeCenterLayout` consumes the same controller while retaining its own input card, upload list, and submit callback. `Chat/index.tsx` remains the single owner of effective-skill loading and selected names, passing one `skillMentions` contract and the existing submission preflight to both render paths.

## Data Flow

1. A composer change is evaluated by the shared controller.
2. A valid trailing mention opens the local menu and invokes `skillMentions.onOpen()` only when the menu transitions from closed to open.
3. Selecting a skill removes the trailing mention text, appends the selected name through `skillMentions.onChange`, and closes the menu.
4. `Chat/index.tsx` limits selections to five and, before submission from either composer, copies them to `pendingSelectedSkillNamesRef` through the existing submission preflight.
5. `/console/chat` receives only names; its existing server-side validation and trusted directive injection remain unchanged.

## Interaction And Accessibility

The shared menu uses the existing Chinese `aria-label="可用技能"`, keeps selection operable by mouse and keyboard, and presents loading and empty-filter states without altering surrounding composer layout. Selected labels stay removable. No visual redesign, API-route, authorization, or backend behavior changes are in scope.

## Error Handling

The existing effective-skill request failure behavior remains: the parent clears candidates and the composer remains usable. A zero-candidate filter leaves the menu open with an explicit empty state; Enter then follows normal message submission behavior rather than selecting a nonexistent skill.

## Tests

- Unit-test the shared trigger and selection behavior, including valid/invalid mention boundaries and selection limit delegation.
- Add a welcome-composer regression test proving `@keyword` loads and displays candidates, then click/Enter creates a removable label and removes the raw mention text.
- Retain the existing conversation-composer behavior through targeted `Sender` tests.

## Non-Goals

- Changing the backend trusted-selection protocol.
- Changing skills returned by `/skills/effective`.
- Unifying the entire welcome and bottom composer layouts.
