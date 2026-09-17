# Mention Menu Bridge Design

## Goal

Visually connect the Console `@` context-reference menu to the chat input while
keeping them distinct interactive surfaces.

## Design

The wrapper around the menu moves from `bottom: calc(100% + 12px)` to
`bottom: calc(100% + 3px)`. The menu shadow becomes shorter and softer than the
current wide drop shadow. A pseudo-element beneath the menu adds a low-opacity,
quickly fading shadow bridge toward the input field.

The menu retains its white background, rounded corners, z-index, full-width
alignment, and existing open/close behavior. The input keeps its own border and
shadow so the 3px separation remains legible rather than appearing as one
merged control.

The chat input's `:focus-within` state will retain the same border color and
shadow as its unfocused state. Keyboard focus remains available for editing and
assistive technology; only the blue visual emphasis is removed.

## Tests

Add DOM-level assertions for the menu wrapper's 3px bottom offset and the
sender's focus style using its neutral border color. Existing menu interaction
tests continue to cover keyboard selection and focus behavior.
