# Unified Stop Hook Design

**Status:** Approved

## Goal

Replace `BeforeStop` and the observation-only `Stop` event with one blockable `Stop` completion hook. A Stop handler records its own side effects when it runs, and its merged `allow` or `block` decision determines whether the candidate assistant response completes the request.

## Lifecycle

1. A normal agent turn produces a candidate assistant response.
2. The runner emits `Stop` once, passing that candidate response to every matched handler.
3. Handlers may independently audit, notify, or perform other external side effects. Their merged decision is the completion gate; any `block` vetoes the candidate response.
4. An explicit `block` schedules a bounded automatic follow-up turn. The next candidate response emits Stop again, so handlers retain an audit record for both the rejected and approved attempts.
5. A final `allow` completes the request. If the explicit-block retry budget is exhausted, the runner ends the request incomplete using the established completion-block message.

Stop does not run for a turn without a candidate assistant response or for a terminal tool-hook stop path.

## Decisions and failures

- Stop accepts only `allow` and `block`; `deny`, `stop`, `continue: false`, output rewriting, permission output, and other non-gate effects are rejected for Stop configuration or handler output.
- A handler execution failure with `failPolicy: allow` remains diagnostic and does not prevent completion.
- A handler execution failure with `failPolicy: block` ends the request incomplete with its failure reason. It does not schedule an automatic follow-up.
- Existing merge priority remains conservative: any explicit `block` wins over all `allow` results.

## Migration

`BeforeStop` is removed from the event enum, resolver, output validation, runner lifecycle, documentation, wiki examples, and tests. All repository configuration and examples use `Stop`. Residual `BeforeStop` configuration is invalid; there is no compatibility alias or runtime translation.

The old `Stop` observation-only behavior is removed. A Stop handler now receives and returns the completion-gate result while retaining its own side effects.

## Verification

- Unit-test Stop validation: only `allow` and `block` are accepted.
- Unit-test merged decision behavior: a single or any multiple-handler `block` vetoes completion.
- Runner-test explicit Stop `block` schedules a bounded follow-up, and that every candidate response emits Stop.
- Runner-test retry exhaustion becomes an incomplete request.
- Unit-test `failPolicy: allow` completes and `failPolicy: block` ends incomplete without an automatic follow-up.
- Retain terminal tool-hook-stop tests proving Stop is skipped.
- Update hook management fixtures and wiki examples to reject or omit BeforeStop.
