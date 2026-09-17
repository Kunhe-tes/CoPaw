# Market Disabled Skill Package Move Design

## Goal

Disabling a skill from Market "My Skills" must move its registered package from
`skills/<skill_name>` to `.disabled_skills/<skill_name>` before recording the
disabled state in the shared Workspace v2 manifest.

## Scope

`MarketplaceService.disable_skill()` remains the single entry point for the
single-skill UI endpoint and its existing batch and recall callers. This change
does not alter the enable path, change the manifest schema, or introduce a
workspace backup or rollback mechanism.

## Design

The existing `mutate_user_skill_manifest()` callback will resolve the package
for the registered manifest entry. An active package is moved with
`shutil.move()` into the sibling `.disabled_skills` root. A package already in
the disabled root is treated as a resumable partial operation and needs no
second move.

The callback writes `enabled: false` and the timestamp only after the package
is at the disabled location. If the package cannot be resolved, moving raises
an `OSError`, or both roots contain a package, the callback reports no update:
the manifest remains enabled and the service does not reload the agent or
update the registry. The implementation never deletes or overwrites an
existing destination package.

If the process stops after a successful move but before the manifest is
persisted, a later disable attempt resolves the disabled package as the
fallback and completes the manifest update. This provides restart recovery
without duplicating the package or consuming backup storage.

## Tests

Service unit tests will verify that a source- and agent-scoped active package
is moved to its matching disabled root, its manifest is changed only after the
move, and reload/registry updates run on success. A failing move test will
verify the manifest remains enabled and no reload or registry update is made.
