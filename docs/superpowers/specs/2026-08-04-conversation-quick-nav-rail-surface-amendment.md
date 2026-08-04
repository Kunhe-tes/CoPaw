# Conversation Quick Nav Rail Surface Amendment

## Decision

The dedicated quick-navigation rail remains a 48px layout reservation outside the message viewport, but it is not a visual panel.

## Visual Rules

- Remove the rail's left divider.
- Keep the rail background transparent so it shows the owning chat surface: the primary Chat gradient and the read-only modal's white message surface.
- Keep dot, focus, overflow, and keyboard behavior unchanged.
- Do not add a fixed rail color, card, shadow, or replacement separator.

## Acceptance Criteria

1. The rail occupies space outside message content and does not cover it.
2. No persistent line separates the rail from the messages.
3. The rail visually blends into the current chat window in both primary and read-only views.
