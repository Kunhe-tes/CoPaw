## Why

Skill scanner alerts are currently appended to and loaded from one unbounded JSON array. Opening the Security page therefore transfers and renders the entire history, while every write and delete rewrites the whole file; sufficiently large histories can freeze the Console and make storage operations progressively more expensive.

## What Changes

- Make the configured MySQL-compatible application database the only authoritative store for skill scanner alert history.
- Stop reading, writing, migrating, or falling back to `skill_scanner_blocked.json`; existing JSON history is intentionally discarded from the product view.
- Persist new blocked and warned scan records with a stable database identifier while preserving scan enforcement if audit persistence fails.
- Add true server-side pagination with bounded page sizes, stable newest-first ordering, and an accurate total count.
- Replace index-based single-record deletion with stable identifier deletion, and retain clear-all behavior against the database table.
- Surface database/store unavailability explicitly instead of returning a misleading empty history.
- **BREAKING**: change the blocked-history list response from a top-level array to a paginated object and change the single-delete path parameter from an array index to a stable record ID.

## Capabilities

### New Capabilities

- `skill-scan-history`: Defines database-only skill scan alert persistence, paginated history retrieval, stable record identity, deletion behavior, and storage-failure semantics.

### Modified Capabilities

None.

## Impact

- SWE skill scanner history recording and its application-lifecycle database integration.
- Security configuration API contracts for listing, deleting, and clearing scan history.
- Console Security page request types, pagination state, and record deletion calls; presentation remains otherwise unchanged.
- A new MySQL-compatible table and indexes managed through the repository's existing database initialization pattern.
- Focused backend store/router/scanner tests and frontend request/component tests.
- No legacy JSON migration, compatibility read, or JSON fallback is included.
