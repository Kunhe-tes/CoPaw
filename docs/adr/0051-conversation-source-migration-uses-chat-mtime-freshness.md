---
status: accepted
---

# Conversation Source Migration Uses Chat Registry Mtime Freshness

For new source-isolated two-stage migration jobs, `prepare` discovers the
service/tenant/source/Agent/workspace mapping, validates the conversation
inputs once, and freezes each workspace's `chats.json` nanosecond modification
time. It does not compute per-input content digests or repeat discovery during
manifest freezing. Conversation inputs and identity evidence for unpublished
sources must remain read-only and unchanged from prepare through publication.

`migrate --apply` reads source publication state from SQL before touching old
source files and prunes already-published sources. It processes unpublished
sources serially in the SQL owner task, parses each workspace once into the
existing bounded transient records consumed by the importer and target
verifier, and compares `chats.json` mtime before import and again before
publication. It does not automatically
rediscover mappings, review failed source evidence, hash inputs, or re-inventory
the complete source after import. The mtime check does not detect edits to
session/dialog/configuration evidence; immutability of those inputs is an
operational prerequisite.

Deployments must guarantee one migration process per application schema across
all hosts and entry points. New-protocol jobs therefore do not acquire the
schema-wide MySQL named lock and do not require SQL queries to retain a fixed
connection ID. Transactions remain pinned to a single pooled connection; every
physical connection is checked against the job's server UUID and schema when
leased. A database identity mismatch stops the job globally.

The freshness protocol is explicitly versioned in the manifest. Existing
manifests retain their established digest, review, lock, and retry behavior and
must not be converted by editing the manifest or clearing SQL state. A failed
new-protocol source remains closed on retry if its frozen mtime no longer
matches; accepting corrected input requires a separately audited revision and
is not performed by ordinary migrate.

## Consequences

- Prepare avoids repeated semantic discovery and input hashing; migrate avoids
  automatic source review and a full post-import source inventory pass.
- Migrate still reads source records to construct bounded transient importer
  input; it does not persist parsed bodies or run a second source inventory
  after import.
- Reproducibility depends on the deployment's read-only guarantee for inputs
  other than `chats.json` and the global single-migration-process guarantee.
- Removing the database named lock makes external singleton enforcement a hard
  deployment prerequisite rather than a convenience.
