## MODIFIED Requirements

### Requirement: Light low-distraction global navigation

The global navigation SHALL use the CoPaw Management Console theme with a white-first, light, low-distraction treatment that uses white canvas roles, restrained blue emphasis, subtle boundaries, and compact management typography without relying on large saturated accent areas.

#### Scenario: Navigation is displayed in standalone mode

- **WHEN** `hideMenu` is false
- **THEN** menu groups, active items, icons, labels, separators, Header, and the content boundary SHALL present a clear but visually subordinate hierarchy relative to the current page

#### Scenario: Navigation is displayed beside chat

- **WHEN** the global navigation appears beside the unchanged Conversation Workspace
- **THEN** navigation SHALL retain the Management theme and SHALL NOT replace the chat region's `#3769FC` emphasis or conversation typography
