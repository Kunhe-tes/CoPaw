# 01: Make Fast Verification the Migration Default

Status: resolved
Type: task
Blocked by: None
Triage: ready-for-agent
Priority: P1

**What to build:** Implement the approved fast-verification behavior in the existing `prepare -> migrate --apply` workflow, retain an explicit full-audit path, exclude historical share records from migration, and report verification level without weakening source freshness, source isolation, or global failure handling.

**Primary seam:** Existing top-level migration CLI workflow with isolated MySQL and filesystem-backed NAS fixtures.

- [x] Make fast structural verification the default after import and before final source freshness check and source publication.
- [x] Validate job/target/source bindings, committed publication ownership, required metadata rows/counts, bundle identity/length/index/block set, and locator containment with bounded SQL and I/O work.
- [x] Batch verification metadata reads under the single SQL owner and deduplicate bundle-path inspection within one run, preserving memory, I/O, lock, and cancellation bounds.
- [x] Preserve full body-level semantic audit as an explicit verification operation and distinguish its result from fast verification in reports and durable source evidence.
- [x] Exclude historical share records from discovery, inventory, import, and verification, without changing runtime Permanent Share Link behavior.
- [x] Preserve final frozen-source recheck, source-level failure isolation, retry behavior, and globally fatal shared infrastructure/unknown-commit failures.
- [x] Add end-to-end tests for successful fast publication, structural failures, body mismatch distinction between fast/full modes, absent historical shares, source isolation, and global failure handling.
- [x] Compare fast/full workflow timing, database query work, bundle opens/index parses, and bytes read on the same isolated MySQL fixture; report real NAS measurements separately when available.

## Answer

Fast structural verification is the default release check in the existing `prepare -> migrate --apply` workflow. It runs after import and before final source freshness checking and publication. Full semantic verification remains available with `verify --full-audit`, and its evidence is stored separately. Historical shares are excluded from migration inputs; runtime share behavior is unchanged.

Validation used an isolated MySQL schema with local input/NAS directories. The representative fixture exercised healthy migration, a rejected running Turn followed by repair/retry, source-level fast-verification failure with healthy sibling publication and retry, and a same-input body mutation that passes fast verification but fails full audit. Global failure handling was separately exercised by unit tests for database/lock loss, unknown commits, cancellation drain, and shared I/O errors. No real-NAS measurement was available; bundle-read counters are not represented as total NAS traffic.

## Comments

2026-11-16: Spec synthesized from the confirmed migration constraints and existing performance acceptance. The seam is the existing `migrate --apply` workflow; implementation has not started.

2026-11-17: Implementation and isolated-MySQL acceptance completed; see issues 02-05 for per-requirement evidence and the remaining real-NAS limitation.
