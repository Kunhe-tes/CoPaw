# Chat List Recency Ordering Design

## Goal

Make every `GET /api/chats` list mode return Chat Records in descending order of Chat Record Last Updated Time, rather than creation time or storage order.

## Scope

- The unpaginated legacy array response is ordered by `(updated_at, id)` descending.
- Page-number pagination keeps its response shape and uses the same ordering.
- Cursor pagination encodes and compares `(updated_at, id)` while keeping its opaque cursor format and existing filter behavior.
- Equal update timestamps use descending chat ID as a deterministic tiebreaker.

## Cursor Semantics

Cursor pagination is live and best-effort rather than snapshot-consistent. A Chat Record changed between page requests can move across the cursor boundary, so a later page can omit a newly updated record or repeat a previously returned record. Clients that need a current complete list restart at the first page.

## Design

Keep the recency sort key in the chat repository and reuse it from both pagination paths. The manager applies that same key to the unpaginated filtered result. Filtering, statuses, response models, validation, and cursor encoding remain otherwise unchanged.

## Verification

Tests use Chat Records whose creation and update times intentionally disagree. They cover unpaginated, page-number, and cursor responses, plus deterministic ordering for equal update timestamps. The former cursor-stability test is replaced with the documented live best-effort behavior.
