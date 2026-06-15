## 1. Backend Resource Filter Contract

- [x] 1.1 Add and validate the optional discriminated resource filter parameters on the tracing sessions router for model, skill, and MCP tool identities.
- [x] 1.2 Extend the tracing query service session WHERE construction so resource constraints apply to both count and paginated data queries while preserving source, user, branch, date, session, and error constraints.
- [x] 1.3 Add backend tests for exact model matching, exact skill matching, composite MCP server/tool matching, combined error filtering, pagination totals, invalid filter inputs, and source isolation.

## 2. Console Filter State And API Integration

- [x] 2.1 Add typed resource filter identity and session request parameters to the Console tracing API client without changing existing callers.
- [x] 2.2 Add single-select resource filter state to the user detail modal, including replace, toggle-clear, close-reset, first-page reset, selected-session reset, and reporting-period date propagation.
- [x] 2.3 Preserve the active resource selection when the error-session filter changes and combine both filters in session requests.
- [x] 2.4 Keep `UserStatsHeader` on user-level usage data while a resource filter is active, while preserving existing session-level summary behavior when no resource filter is active.

## 3. Interactive Usage Tags

- [x] 3.1 Pass structured model, skill, and MCP tool identities through usage-tag callbacks without parsing display labels.
- [x] 3.2 Make usage tags keyboard-operable filter controls with semantic pressed or selected state and accessible labels.
- [x] 3.3 Add persistent selected-tag styling using the applicable Console design tokens or established local patterns, with distinct border, background, text emphasis, hover, and focus-visible states.
- [x] 3.4 Preserve tag wrapping and long-label readability for selected and unselected tags.

## 4. Automated Verification

- [x] 4.1 Add or update `UserStatsHeader` tests for model, skill, and MCP selection, selected styling semantics, replacement, and clearing.
- [x] 4.2 Update user detail modal tests for filtered API requests, date propagation, pagination reset, session reset, error-filter combination, stable user-level summary, and close reset.
- [x] 4.3 Run focused backend tracing tests and focused Console component tests.
- [x] 4.4 Run Console lint, type/build checks, and the relevant broader backend test suite.

## 5. UI Review

- [x] 5.1 Read and apply `console/DESIGN.md` before changing the visible interaction; if the required file is still absent, stop and resolve the missing design authority before UI implementation. (Repository owner explicitly authorized this change to proceed while the file is temporarily uncommitted.)
- [ ] 5.2 Verify default, hover, focus-visible, selected, replacement, cleared, loading, empty-result, error-only, and combined-filter states.
- [ ] 5.3 Verify the modal at 1280x720, 1440x900, and 1920x1080, plus `hideMenu=true` embedded mode when supported, checking tag wrapping, selected-state clarity, clipping, overflow, pagination, and operation discoverability.
- [x] 5.4 Confirm no unrelated Console pages, API contracts, routes, permissions, iframe messages, or business outcomes changed.
