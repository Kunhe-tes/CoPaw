## MODIFIED Requirements

### Requirement: Centered input box card
The input box SHALL be displayed as a white card (background #FFFFFF, border-radius 12px, width 800px max) centered in the welcome layout. It SHALL contain a placeholder description text, an attachment button, optional active mode controls, and a send button (background #3769FC, size 32x32). When Plan Mode is active for the current chat, the optional active mode controls SHALL include the same visible `计划模式` disable button used by the standard bottom composer.

#### Scenario: Empty input state
- **WHEN** the input box is displayed with no text
- **THEN** the placeholder "告诉我你要做什么，我将召唤相应专家，为你执行…" is shown in color #808191

#### Scenario: Filling input from featured case
- **WHEN** a user clicks a featured case card or the "做同款" button
- **THEN** the case text is filled into the input box without auto-sending

#### Scenario: User types and sends
- **WHEN** the user types text in the input box and presses Enter or clicks the send button
- **THEN** the message is submitted via the existing chat submission flow

#### Scenario: Welcome composer shows active Plan Mode
- **WHEN** the welcome input card is displayed for a chat with Plan Mode enabled
- **THEN** the card action row shows the `计划模式` active button next to the quick menu controls

#### Scenario: Welcome composer disables active Plan Mode
- **WHEN** the user clicks the `计划模式` active button in the welcome input card
- **THEN** Plan Mode is disabled for the current chat through the same persistence flow as the standard bottom composer
