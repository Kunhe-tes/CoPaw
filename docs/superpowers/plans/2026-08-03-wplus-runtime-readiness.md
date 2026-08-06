# W+ SOP runtime readiness implementation plan

## Problem

`question_batch` can move the durable SOP Session to `AwaitingAnswer` before
the producing Chat Agent task has released its TaskTracker slot. The workspace
therefore enables answer submission too early, and the command can exceed the
current ten-second cleanup wait and fail.

## Decisions

- Keep `AwaitingAnswer` as the business state; runtime readiness is an
  ephemeral, derived transport status.
- Include the current runtime status in Session HTTP snapshots and emit
  non-versioned `runtime_status` SSE control frames when it changes.
- Keep the backend idle check as the authority. A cleanup timeout uses a
  machine-readable 409 response instead of a generic validation error.
- Keep answer editing available while finalizing; only gate submission.

## Implementation units

### 1. Backend runtime status contract

Files:

- `src/swe/app/wplus_sop/service.py`
- `src/swe/app/wplus_sop/router.py`
- `tests/unit/app/wplus_sop/test_service.py`
- `tests/unit/app/wplus_sop/test_router.py`

Test scenarios:

- A running owning-Chat task serializes as `finalizing` and not ready.
- An idle task serializes as `ready` with no blocking run.
- SSE emits the initial runtime status and a second frame when it becomes
  ready without changing `state_version`.
- A command cleanup timeout maps to 409 with
  `code=owning_chat_finalizing` and does not mutate the Session.

### 2. Workspace readiness gate

Files:

- `console/src/api/types/wplusSop.ts`
- `console/src/pages/WPlusSopWorkspace/index.tsx`
- `console/src/pages/WPlusSopWorkspace/index.test.tsx`
- `console/src/api/modules/wplusSop.test.ts`

Test scenarios:

- A complete answer batch remains non-submittable while runtime readiness is
  false and displays the finalizing explanation.
- A `runtime_status` SSE frame updates readiness without requiring a business
  event or Session reload.
- Readiness true enables submission and preserves the existing answer payload.
- A finalizing 409 keeps the answer draft and shows a specific waiting notice.

### 3. Documentation and verification

Files:

- `docs/adr/0013-wplus-sop-uses-persisted-session-and-structured-envelope.md`

Verification:

- Targeted backend and frontend tests.
- Full W+ backend suite and focused console tests/typecheck.
- Python compile check, `git diff --check`, and GitNexus `detect-changes`.

