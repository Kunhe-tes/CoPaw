## ADDED Requirements

### Requirement: Content-only Conversation Workspace presentation variant

The Console design authority SHALL define a focused content-only Conversation Workspace presentation variant. The variant SHALL preserve the existing Conversation Workspace typography, title behavior, message presentation, message actions, and fixed `#3769FC` emphasis while omitting only the requested surrounding navigation and question-entry surfaces.

#### Scenario: Content-only variant is documented

- **WHEN** chat content-only presentation is introduced
- **THEN** `console/DESIGN.md` documents the durable visual contract for retained title/content/actions, omitted surrounding surfaces, and layout continuity without implementation-specific activation or test details

#### Scenario: Focused content hierarchy renders

- **WHEN** the content-only variant displays a chat
- **THEN** the existing title and conversation content are visually primary
- **AND** no global navigation, chat sidebar, generated-files entry/list, model selector, composer, or upload surface competes with the content
- **AND** no empty rail or shell-colored gap is reserved for a suppressed surface

#### Scenario: Existing message controls remain accessible

- **WHEN** normal chat rules expose approval, feedback, retry, suggestion, copy, download, preview, disclosure, or quick-navigation controls
- **THEN** the content-only variant preserves their accessible names, focus treatment, and existing behavior

#### Scenario: Required viewport verification

- **WHEN** the content-only variant is reviewed at `1280x720`, `1440x900`, and `1920x1080`, embedded and top-level where applicable
- **THEN** the title, messages, message actions, previews, and stream updates remain usable without clipping, overlap, empty shell gaps, or horizontal page overflow
