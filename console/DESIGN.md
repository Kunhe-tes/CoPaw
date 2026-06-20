# CoPaw Console Design System

This document is the single design source of truth for new and modified user-facing UI under `console/`. Git history and archived OpenSpec changes preserve prior decisions; do not create competing project design manuals or vendor third-party `DESIGN.md` files.

## Document Status

- Status: white-first embedded baseline under calibration.
- Reference implementation: global Header/navigation and `/models`.
- Ownership: update this document in the same OpenSpec change whenever an accepted UI change introduces or revises a reusable visual rule.
- Adoption: new and modified UI follows this document; untouched legacy UI migrates through separate changes.

## Scope And Adoption

- Apply these rules to every new Console surface and to the visible region of any existing surface being changed.
- Adopt the system incrementally. Do not globally restyle untouched legacy pages as a side effect of another change.
- UI work may reorganize layout, extract presentational components, consolidate tokens, and move local inline styles into Less/CSS Modules.
- UI work must not change API contracts, request parameters, route paths, permission checks, iframe messages, Zustand state meaning, event-handler outcomes, validation, error handling, or business operation semantics unless a separate approved requirement says so.
- The supported visual theme is light. Existing dark-theme code may remain, but new UI work does not need to add dark-theme styling.

## Reference Direction

CoPaw uses an adapted reference strategy:

- [Claude](https://github.com/VoltAgent/awesome-design-md/tree/main/design-md/claude) is a structural reference for restraint, gentle boundaries, spacing, radii, editorial rhythm, and quiet confidence. Its warm palette is not a project requirement.
- [Linear](https://github.com/VoltAgent/awesome-design-md/tree/main/design-md/linear.app) remains a secondary reference for compact information hierarchy and low-distraction interaction. Its dark-only palette is not copied.
- CoPaw uses its own white-first embedded palette, operational density, Chinese typography, configured logos, and Conversation Workspace identity.
- The Conversation Workspace keeps `#3769FC` as its fixed emphasis color unless a later approved chat-specific change revises it.

External references are inspiration only. When they conflict with this document, this document wins. The target is a white-first Chinese AI management console that integrates with white embedding hosts, not a visual clone of an external product.

## Product Character

The Console should feel integrated, calm, precise, and quietly capable. Management surfaces should use white-first embedding, near-white functional grouping, practical whitespace, readable hierarchy, and compact discoverable operations without creating a competing visual brand inside the host product.

Avoid decorative gradients, oversized cards, heavy shadows, excessive rounded containers, large saturated accent areas, and low-density marketing layouts.

## Theme Architecture

The visual system has three layers:

1. **Base foundation**: spacing, radii, elevation, motion, semantic status, and accessibility behavior shared where appropriate.
2. **Management Console theme**: white-first embedded canvas, white operational surfaces, near-white functional panels, blue actions, and multilingual management typography.
3. **Conversation Workspace theme**: existing blue emphasis, existing typography, and conversation-specific presentation.

Use semantic roles rather than page-specific literal colors. New non-chat pages must be able to adopt the Management Console theme without depending on `/models` classes. Do not replace the global `body` font or a single application-wide primary color in a way that leaks management styling into chat or untouched legacy pages.

The global Header and navigation use the Management Console theme even when displayed beside chat. The chat content region and independent conversation sidebar remain in the Conversation Workspace theme.

## Foundations

### Typography

The current baseline uses platform fonts so it works without downloading font assets or depending on a runtime font CDN.

```css
--console-font-ui: "Segoe UI", "Microsoft YaHei", "PingFang SC",
  "Helvetica Neue", sans-serif;

--console-font-editorial: Georgia, "Songti SC", "SimSun", serif;

--console-font-mono: SFMono-Regular, Consolas, "Liberation Mono", monospace;
```

- UI role: navigation, breadcrumbs, controls, forms, buttons, tables, cards, metadata, and operational section headings.
- Editorial role: limited to approved page-level titles, welcome content, featured guidance, or other content-led surfaces. Do not broadly apply serif typography to dense management workflows.
- Technical role: provider IDs, URLs, paths, code, logs, and machine-oriented values.
- Preferred UI weights: 400, 500, and 600. Preferred editorial weights: 500 and 600.
- A later typography-specific change may introduce locally hosted Poppins/Noto Sans SC and Lora/Noto Serif SC assets. Until then, do not add a font CDN or assume those families are present.
- Visible page title when needed: 18-22px / 26-30px, weight 600. A compact breadcrumb-only management header may omit a duplicate visible title while retaining a semantic heading.
- Section title: 16px / 24px, weight 600.
- Body: 14px / 22px, weight 400.
- Compact control or metadata: 12-13px / 18-20px, weight 500 when needed for Windows clarity.
- Avoid weights below 400 for Chinese UI and avoid relying on macOS-only thin-font rendering.

### Color Roles

| Role                     | Initial value | Usage                                              |
| ------------------------ | ------------- | -------------------------------------------------- |
| Management canvas        | `#FFFFFF`     | Embedded page background                           |
| Surface                  | `#FFFFFF`     | Cards, dialogs, and interactive panels             |
| Subtle surface           | `#F7F9FC`     | Secondary groups, controls, inactive regions       |
| Navigation surface       | `#FFFFFF`     | Low-distraction global navigation                  |
| Border                   | `#E5E7EB`     | Default separators and component borders           |
| Strong border            | `#D0D7E2`     | Focused group boundaries                           |
| Primary text             | `#111827`     | Titles and main content                            |
| Secondary text           | `#4B5563`     | Descriptions and labels                            |
| Muted text               | `#8A94A6`     | Supporting metadata and placeholders               |
| Management primary       | `#3769FC`     | Primary management actions and focused emphasis    |
| Management primary hover | `#2957DC`     | Hover/active management action state               |
| Primary soft             | `#EEF4FF`     | Selection and low-emphasis blue feedback           |
| Conversation primary     | `#3769FC`     | Chat selection, composer, and conversation actions |
| Success                  | `#2F7D5B`     | Available and successful states                    |
| Warning                  | `#A56A24`     | Partial and caution states                         |
| Error                    | `#B94A4F`     | Destructive and failed states                      |

Blue is shared as a product emphasis across management and conversation surfaces, but each theme retains separate semantic variables and component scopes. Saturated blue is reserved for primary actions, focus, and concise selection; large surfaces use white, with near-white gray-blue reserved for functional grouping.

`console/src/config/consoleDesignTokens.ts` is the normal palette-edit entry point. Change semantic token values there, keep role names stable, update this table, and verify affected surfaces. Do not tune the theme by scattering hexadecimal colors across page styles.

### Spacing

Use a 4px base rhythm. Preferred steps: `4, 8, 12, 16, 20, 24, 32, 40`.

- Dense control gaps: 8px.
- Related content groups: 12-16px.
- Section separation: 20-32px.
- Desktop page gutters: 20-32px, selected according to content density and available shell width.
- Do not add a card merely to create spacing.

### Radius, Borders, And Elevation

- Small controls: 6px.
- Inputs and buttons: 8px.
- Content cards and dialogs: 12px. Larger marquee or configuration panels may use 16px.
- Pill radius is reserved for badges and compact filters.
- Prefer neutral one-pixel borders and surface contrast over shadows.
- Default shadow: `0 1px 2px rgba(35, 31, 27, 0.04)`.
- Raised overlay shadow: `0 14px 36px rgba(35, 31, 27, 0.12)`.
- Hover must not move layout. Use border, background, color, or subtle shadow transitions of 150-220ms.

### Icons

- Keep AgentScope icons for AgentScope-specific concepts.
- Prefer `lucide-react` for new generic interface icons.
- Keep Ant Design icons where already coupled to an Ant Design workflow or where no suitable icon exists.
- Functional icons must not be emoji.
- Use consistent 16-18px navigation/control icons and align them to the text baseline.

### Interaction And Accessibility

- All clickable controls need hover, visible keyboard focus, disabled, and in-progress states.
- Do not hide primary actions behind hover-only UI.
- Labels must remain associated with form controls; placeholders are not labels.
- Dynamic loading, success, warning, and failure states must remain distinguishable without relying only on color.
- Use blue focus rings with sufficient contrast on Management Console surfaces; preserve conversation-specific focus behavior inside chat.
- Respect `prefers-reduced-motion` for newly introduced non-essential animation.

## Global Shell And Navigation

- The Header and global navigation use white, low-distraction surfaces with restrained text hierarchy, light boundaries, and blue reserved for concise interaction emphasis.
- The current page owns visual attention. Navigation uses pale blue hover and selection surfaces, moderate text weight, and restrained icon color.
- All first-level navigation entries, including expandable groups and direct root links, use the same UI font, 13px size, 600 weight, and 36px line box. Second-level entries also use 13px but rely on 400 weight, indentation, quieter color, and selection treatment to preserve hierarchy.
- Global navigation may appear beside the blue Conversation Workspace without changing either theme's identity.
- Preserve menu structure, ordering, labels, routes, permissions, expanded groups, and collapse behavior.
- Preserve the `hideMenu` contract: embedded hosts may remove both Header and global Sidebar.
- Preserve source-specific logo assets and dimensions. Only the layout around the logo may change.
- The navigation collapse control remains visible and discoverable without becoming a dominant accent.

## Conversation Workspace

The Conversation Workspace is intentionally outside the current management-theme migration. It keeps `#3769FC`, its existing typography, content surfaces, independent conversation sidebar, composer, and conversation-specific presentation.

Visual priority for future chat work remains:

1. Conversation, generated content, and current-task execution content.
2. Composer, send state, attachments, and model context.
3. My Tasks and History lists used for switching context.
4. Tool-call details, progress details, and generated files.
5. Featured cases and onboarding guidance.
6. Global navigation.

- Preserve the existing conversation sidebar width until a later approved chat migration changes it.
- Preserve its collapse behavior.
- Future chat redesigns may reuse base accessibility and spacing roles while evolving its visual theme independently from management pages.
- Future chat redesigns must work both with and without the global navigation.

## Management Console

Management pages use medium-high information density with white-first host integration, near-white functional grouping, and white operational surfaces. Prefer compact controls, efficient use of desktop width, clear section hierarchy, practical whitespace, and blue primary actions.

Choose one of three page patterns:

1. **Standard management page**: compact breadcrumb or page heading, optional description, filter/action bar, table or compact card grid.
2. **List-detail page**: stable left list and flexible right detail panel.
3. **Dashboard page**: filter bar, concise metrics, charts, and supporting tables.

Shared rules:

- Use one compact page-level breadcrumb with a small contextual icon, followed by clear section headings. Do not duplicate the current page title.
- Keep primary actions near the page or section title; group low-frequency actions in a visible more-actions menu.
- Use the available desktop width with moderate gutters. Bound prose and form fields locally rather than centering the entire page inside a narrow container.
- Cards should communicate a distinct item, status, or action group. Avoid wrapping every section in a decorative card.
- Let the white page canvas integrate with the host and connect related sections. Reserve near-white subtle surfaces for functional grouping and white surfaces for actual interactive panels, dialogs, and distinct item cards; do not stack a white page container, white section container, and white child card around the same content.
- Use the UI font for operational interfaces and reserve the editorial font for content-led moments.
- Empty, loading, error, disabled, unavailable, and in-progress states use consistent spacing, icon scale, title, explanation, and recovery-action placement.
- Select, dropdown, and menu overlays on Management Console surfaces use white elevated panels, near-white hover states, and `Primary soft` selected states instead of neutral gray selection fills.

## Model Management Reference Pattern

The `/models` page is the first complete white-first embedded Management Console reference.

- Default LLM configuration is a compact, clearly labelled 16px-radius panel using the near-white subtle surface and a neutral hairline border.
- The page uses open canvas-level sections separated by spacing or a quiet rule rather than enclosing both major sections in large white cards.
- Provider results use a wrapping equal-width card row. Cards share the available row width, add columns when their practical minimum width fits, and wrap only when needed; an incomplete final row expands to avoid a conspicuous empty column.
- Each provider card retains icon, name, ID, status, Base URL or equivalent connection summary, model count, and operations.
- Provider cards use a compact identity header, one continuous aligned summary list, a white surface with a neutral hairline boundary, a standard 12px content-card radius, and a quiet unfilled action row.
- Model and Settings actions remain directly visible as equal-height, low-emphasis icon-and-text actions. Destructive or low-frequency actions may use an icon-only more-actions menu aligned with them.
- Primary page actions use `#3769FC`. Secondary and card-level actions remain visually quieter.
- Breadcrumbs, controls, cards, and section titles use the UI font; Provider IDs and URLs use the technical font.
- Dialogs use consistent header, body spacing, field rhythm, notices, list rows, and footer alignment.
- Provider and model operations keep their current handlers, validation, confirmation, and result semantics.

## Verification

For major desktop migrations, inspect:

- Embedded host containers corresponding to `1280x720`, `1440x900`, and `1920x1080` viewport sizes.
- `hideMenu=true` with the page filling the host content region and no shell-colored gaps.
- Windows Chrome and Edge using the declared platform font stack; retain readable macOS fallbacks.
- No external font-network requests.
- No unintended clipping, overlap, inaccessible actions, or horizontal page overflow.
- Normal, hover, focus, loading, empty, error, disabled, unavailable, and in-progress states.
- A representative chat route for unchanged blue emphasis, typography, conversation sidebar, and layout.
- Representative untouched legacy pages after shared-token changes when the global shell is visible during development.
- Existing build, lint, tests, and core business interaction paths.

Update this document and the implementation together after visual feedback before treating a revised rule as stable.

## Deferred Migration Backlog

Legacy adoption remains intentionally incremental. Each area below requires its own future OpenSpec change:

1. Remaining system-setting and operational pages: selected-case management, environment variables, security policy, channels, runtime configuration, scheduled tasks, and heartbeat.
2. Creation and resource pages: files, skills, built-in tools, MCP, and application-market surfaces.
3. Insight and quality pages: operations dashboards, Claw analytics, user messages, and continuous governance.
4. Conversation Workspace: conversation content, My Tasks, composer/send states, history, tool calls, progress, generated files, featured cases, and embedded presentation. This is a separate design migration and must not be implied by management-theme work.
5. Cleanup work: remove dormant dark-theme switching only through a separate approved change.
6. Optional typography assets: evaluate locally hosted multilingual UI/editorial fonts, licensing, payload, and cross-platform rendering in a separate change before replacing the platform font baseline.

Untouched legacy pages are not considered violations until their visible region is changed. When a migration starts, use the project's exploration, documented discussion, OpenSpec planning, implementation, verification, and archive workflow.
