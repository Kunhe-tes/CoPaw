# Conversation Quick Nav Rail Design

## Goal

Prevent the conversation quick-navigation dots from covering chat messages while preserving question navigation, current-question highlighting, accessibility, and the existing compact Conversation Workspace visual language.

## Confirmed Direction

Use a fixed, dedicated right-side navigation rail.

The rendered chat viewport is a two-column layout:

```text
| message viewport: minmax(0, 1fr) | quick-nav rail: 48px |
```

The message viewport owns all readable message width. `ConversationQuickNav` renders inside the 48px rail instead of being absolutely positioned over the message viewport.

## Scope

- Apply the rail to the primary chat page.
- Apply the same rail pattern to the read-only session-chat modal, which also renders `ConversationQuickNav`.
- Preserve the existing question extraction, current-question detection, click/keyboard navigation, overflow paging, and hover/focus tooltip behavior.
- Preserve the current compact light conversation styling. The rail uses a subtle neutral boundary and does not introduce cards, gradients, or persistent floating panels.

## Layout And Interaction

1. The chat content host becomes the layout owner for a message column and a fixed navigation rail.
2. The AgentScope message UI is constrained to the message column (`min-width: 0`) so long content wraps rather than expanding beneath the rail.
3. The quick-navigation component exposes an embedded/rail layout mode. In this mode it is a normal-height child of the rail, not an absolute layer with `z-index` above content.
4. The rail remains 48px wide across normal and narrow desktop/embedded containers. It provides enough separation for the current 14–28px dot affordances and accessible hit targets.
5. Tooltips continue to be transient hover/focus feedback; no navigation element persistently overlays message content.
6. The rail stays visually quiet: existing dot colors and active state are retained, with a single neutral divider between message content and navigation.

## Edge Cases

- No eligible question messages: `ConversationQuickNav` returns `null`; the layout must not leave a visible divider or empty rail.
- Many questions: the existing internal quick-nav scroll area and top/bottom paging hints remain reachable within the rail.
- Long Chinese or English content: the message column remains the only text layout region and wraps without being obscured.
- Read-only modal: the message list retains its own scroll root and passes it to quick navigation exactly as it does today.
- Keyboard use: each dot remains focusable, Enter/Space activate its existing scroll-to-message behavior, and focus treatment remains visible.

## Implementation Boundaries

- Do not change chat message APIs, pagination, compaction state, session routes, or message ordering.
- Do not change the semantics of `scrollRootRef` or the question-navigation hooks.
- Do not globally restyle AgentScope bubble lists.
- Keep layout styling locally scoped to the chat-page and read-only-chat hosts, plus the quick-nav rail variant.

## Verification

- Unit test the embedded rail class/variant while retaining existing question-jump behavior.
- Run the existing `ConversationQuickNav` tests and the read-only session-chat test.
- Run Console lint and a production/test build for the changed frontend surface.
- Perform a browser check in the primary chat page and read-only modal: dots and overflow controls sit in the rail, message text is not covered, and a selected dot scrolls to its question.

## Acceptance Criteria

1. Persistent quick-nav dots and overflow controls never overlap chat message content.
2. The primary chat page and read-only session-chat modal behave consistently.
3. Existing quick-navigation interactions and keyboard access remain functional.
4. No empty rail or divider is visible when quick navigation is absent.
