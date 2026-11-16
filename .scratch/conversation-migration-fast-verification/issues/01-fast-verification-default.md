# 01: Make Fast Verification the Migration Default

Status: open
Type: task
Blocked by: None
Triage: ready-for-agent
Priority: P1

**What to build:** Implement the approved fast-verification behavior in the existing `prepare -> migrate --apply` workflow, retain an explicit full-audit path, exclude historical share records from migration, and report verification level without weakening source freshness, source isolation, or global failure handling.

**Primary seam:** Existing top-level migration CLI workflow with isolated MySQL and filesystem-backed NAS fixtures.

- [ ] Make fast structural verification the default after import and before final source freshness check and source publication.
- [ ] Validate job/target/source bindings, committed publication ownership, required metadata rows/counts, bundle identity/length/index/block set, and locator containment with bounded SQL and I/O work.
- [ ] Batch verification metadata reads under the single SQL owner and deduplicate bundle-path inspection within one run, preserving memory, I/O, lock, and cancellation bounds.
- [ ] Preserve full body-level semantic audit as an explicit verification operation and distinguish its result from fast verification in reports and durable source evidence.
- [ ] Exclude historical share records from discovery, inventory, import, and verification, without changing runtime Permanent Share Link behavior.
- [ ] Preserve final frozen-source recheck, source-level failure isolation, retry behavior, and globally fatal shared infrastructure/unknown-commit failures.
- [ ] Add end-to-end tests for successful fast publication, structural failures, body mismatch distinction between fast/full modes, absent historical shares, source isolation, and global failure handling.
- [ ] Compare fast/full workflow timing, database query work, bundle opens/index parses, and bytes read on the same isolated MySQL fixture; report real NAS measurements separately when available.

## Comments

2026-11-16: Spec synthesized from the confirmed migration constraints and existing performance acceptance. The seam is the existing `migrate --apply` workflow; implementation has not started.
