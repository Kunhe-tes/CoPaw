# Default Agent Hook Console Frontend Design

## Scope

Add a Console page at **运行中心 → Hook 管理** for the current tenant's
`default` Agent Profile. The page has no Agent selector and does not add a
separate permission model.

The page is a client for the dedicated Hook-management API introduced by the
existing backend work. It does not alter Hook execution semantics, tenant
resolution, Agent reload behaviour, or the API contract.

## Existing Backend Contract

The page uses these tenant-scoped endpoints:

- `GET /hook-management/configuration` returns `hooks` and its `revision`.
- `PUT /hook-management/configuration` submits the complete `hooks` draft with
  an `If-Match` revision. A successful response contains the new revision and
  schedules the existing asynchronous reload for the default Agent.
- `GET /hook-management/scripts` lists the controlled script library.
- `POST /hook-management/scripts` uploads a batch and returns per-file
  accepted, warned, and failed results. Replacements are explicitly selected
  in the multipart `overwrite` field.
- `POST /hook-management/manual-test` executes one draft Handler only after
  `confirmRealExecution: true`, returning a redacted bounded summary.

The interface must retain the backend's restrictions: only supported script
extensions may be uploaded, scripts are owned under `hooks/scripts/`, and a
script reference in command `argv` must use that owned path. Other command
arguments, including executable paths and ordinary flags, stay free-form.

## Information Architecture

The page is a standard, white-first Management Console surface under Run
Center. Its header identifies the fixed target as `Default Agent · 当前租户` and
keeps the named primary action, **保存并激活**, visible.

The page has two peer views:

1. **配置** is a master-detail workbench. The left tree represents
   `event → matcher group → handler`; the right pane edits the selected root,
   group, or Handler.
2. **脚本库** is a separate view for scripts owned by the default profile. It
   is deliberately not mixed into the configuration tree.

This separation preserves three distinct states: an unsaved configuration
draft, immediately persisted script assets, and the active Agent state after a
successful save and asynchronous reload.

## Configuration Workbench

The configuration root exposes the global enabled switch. The tree supports
adding and removing events, matcher groups, and Handlers in the browser draft.
Matcher-group and Handler IDs are generated initially, editable, and validated
as globally unique before save.

The right pane directly exposes common Handler fields. It renders the proper
form for `command`, `http`, and `prompt` Handlers, including a visually ordered
`argv` editor for commands. Advanced settings are progressively disclosed for
condition expressions, timeouts, failure policy, one-time behaviour,
conversation snapshots, status messages, working directory and environment,
and HTTP authentication.

Handler type and event combinations that the existing Hook model rejects are
not presented as valid choices. The client keeps complete API responses in its
draft so unsupported or future-compatible fields are not discarded.

The selected Handler provides **执行人工测试**. The test modal collects an
event-appropriate example `HookContext`, requires a dedicated real-execution
confirmation, and sends only that Handler's current draft. It never saves the
draft, reloads the Agent, or executes the entire matcher group.

## Script Library

The script-library table shows name, technical path or digest where useful,
size, and scan outcome. It supports a batch file-picker upload with per-file
results; one failed file never hides successful files in the same batch.

For a conflicting filename, the client names each target and requests explicit
replacement confirmation before including it in `overwrite`. Deletion is out
of scope. Upload feedback clearly says that a newly uploaded script becomes
available to later saved configurations but does not itself activate an
unsaved configuration draft.

## State, Failure, And Accessibility Behaviour

- Loading uses stable skeletons for the tree, detail pane, and script table.
- `422` validation failures appear at the relevant field or action while
  retaining the user's draft.
- `409` configuration conflicts open a recovery prompt to reload the latest
  server configuration instead of silently overwriting it.
- Missing default profile, unavailable API, empty configuration, upload
  failures, scan warnings, permission errors, and manual-test failures use
  explicit, recoverable states.
- The manual-test confirmation states that it can run a real command, HTTP
  request, or model invocation. Returned output is displayed only as the
  backend-provided redacted summary.
- Inputs retain visible labels; icon controls have accessible names; focus,
  disabled, in-progress, success, warning, and destructive states are not
  conveyed by colour alone.

## Implementation Boundaries

Create an API adapter and TypeScript domain types local to the Console's Hook
management feature. Add the Run Center sidebar item and route, then build a
focused page component with presentational subcomponents for the tree, editor,
script library, upload feedback, and manual-test modal.

The work reuses established Console routing, request, Ant Design, message, and
token patterns. It must preserve `hideMenu=true`, long CJK/English identifiers,
and narrow embedded containers.

## Verification

Use test-first development for the new feature. Cover form/draft conversion,
tree selection and mutation, request headers and payloads, `409` recovery,
field validation rendering, per-file upload outcomes and overwrite
confirmation, and manual-test confirmation and redacted-summary display.

Run the relevant Console type check, test suite, lint, formatting, and build.
Review the visible page using realistic long names, paths, empty data, failed
requests, warning results, and a narrow embedded container.
