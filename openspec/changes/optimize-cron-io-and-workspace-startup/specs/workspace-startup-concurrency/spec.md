## ADDED Requirements

### Requirement: Workspace startup is isolated per cache key

The multi-agent manager SHALL allow different tenant/agent cache keys to start workspaces concurrently while preserving the existing cache hit behavior.

#### Scenario: Different cache keys start concurrently
- **WHEN** concurrent `get_agent()` calls request different tenant/agent cache keys that are not yet cached
- **THEN** one slow workspace startup MUST NOT hold the global manager lock in a way that blocks startup for the other cache key

#### Scenario: Cache hit remains immediate
- **WHEN** `get_agent()` is called for a tenant/agent cache key that already has a cached workspace
- **THEN** the manager MUST return the cached workspace without creating a new startup task

### Requirement: Concurrent startup for the same cache key is deduplicated

The multi-agent manager SHALL ensure concurrent `get_agent()` calls for the same tenant/agent cache key share one inflight startup and resolve to one workspace instance.

#### Scenario: Same cache key starts once
- **WHEN** multiple concurrent `get_agent()` calls request the same uncached tenant/agent cache key
- **THEN** the manager MUST start exactly one workspace instance for that cache key
- **THEN** all callers MUST receive the same cached workspace instance after startup succeeds

#### Scenario: Startup failure is shared and retryable
- **WHEN** the inflight startup for a cache key fails
- **THEN** all callers waiting on that startup MUST receive the failure
- **THEN** the manager MUST clear the inflight startup state so a later `get_agent()` call can retry

#### Scenario: Race with existing cached workspace is resolved safely
- **WHEN** a startup finishes but another operation has already populated the same cache key
- **THEN** the manager MUST keep one cached workspace instance and MUST clean up any duplicate newly-created instance before returning
