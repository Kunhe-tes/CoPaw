# High Frequency Question Scheduled Submit API - Proposal

## Summary

Add a scheduler-facing high-frequency question task submission API that does not
depend on request headers and always creates a new workflow task for the latest
seven-day window.

## Motivation

The in-bank scheduler can run HTTP jobs every two hours but cannot send custom
headers. The existing interactive task API resolves `source_id` primarily from
`X-Source-Id` and may reuse a recent 24-hour result unless forced. A dedicated
scheduler endpoint keeps the interactive contract unchanged while providing a
minimal body-only API for scheduled runs.

## Scope

- Add a request body containing required `source_id` and optional `bbk_id`.
- Add a new POST endpoint for scheduler-driven task submission.
- Server-side calculate `end_time = now` and `start_time = now - 7 days`.
- Submit through the existing high-frequency question task flow with force
  enabled so each scheduler call creates a new `batch_id`.
- Preserve current `/tasks`, `/prewarm`, result lookup, workflow dispatch, and
  cache behavior.

## Out of Scope

- Changing the external AI workflow payload shape.
- Changing Console behavior.
- Changing async task polling, result writing, or prewarm behavior.
