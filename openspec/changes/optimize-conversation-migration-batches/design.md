## Context

The approved local performance spec and tickets are the authoritative detailed scope. ADR 0049 refines ADR 0046: new jobs isolate and publish service/tenant/source units.

## Goals / Non-Goals

Goals: reduce SQL/transaction and IO amplification with bounded batches, maintain old-job recovery, demonstrate equivalent results and source isolation. Non-goals: multiple SQL owners, cross-source transactions, reduced validation/fsync, new formats or production rollout.

## Decisions

Use existing prepared inserts and highest existing CLI orchestration test seams. Query actual allocated IDs; never infer contiguous auto-increment values. Keep publication atomicity and post-commit mirrors. Read multiple extents through one safe file lifecycle. Reuse analyses only while their immutable evidence remains valid. Each ticket lands independently with tests and code review.

## Risks / Trade-offs

Batches must preserve order, relation checks, missing-row lock semantics and packet budgets. Metrics distinguish logical calls from physical SQL and cumulative IO from wall time. Real MySQL tests complement mocks; local directories do not prove real NAS performance.

## Migration Plan

No schema or public CLI migration. Existing manifests and tickets resume with their identities unchanged. Integrate small commits on the dedicated performance branch and validate fault recovery before declaring completion.
