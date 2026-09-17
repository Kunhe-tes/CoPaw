# Tenant Bootstrap Skill Readiness Design

## Goal

Tenant access-request initialization must not reject or recover a tenant solely
because skill manifests or skill directories are missing, malformed, or out of
sync.

## Decision

`inspect_bootstrap_readiness()` will exclude all skill-specific checks: it will
not read either `skill.json`, require the workspace `skills` or
`.disabled_skills` directories, or require `SKILL.md` files referenced by a
manifest. It will retain validation of every other bootstrap artifact.

## Error handling

Skill files continue to be validated by the components that consume them. A
skill problem therefore affects that skill's use rather than blocking the
tenant's entire access request.

## Tests

Add a readiness test for a tenant with valid non-skill bootstrap artifacts and
an absent or invalid skill manifest/directory. The tenant must be reported
ready. Existing tests for non-skill missing or malformed artifacts remain the
guard against weakening unrelated readiness checks.
