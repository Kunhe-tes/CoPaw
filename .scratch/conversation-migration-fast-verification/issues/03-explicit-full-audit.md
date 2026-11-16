# 03: Keep Full Semantic Verification as an Explicit Audit

Status: open
Type: task
Parent: 01 Make Fast Verification the Migration Default
Blocked by: 02 Default to Fast Structural Verification
Triage: ready-for-agent
Priority: P1

**What to build:** Operators can explicitly run the existing full body-level semantic audit when they need stronger evidence than the fast publication check, and its result is clearly distinct from fast verification.

**Blocked by:** 02 Default to Fast Structural Verification.

- [x] The verification CLI exposes an explicit full-audit selection while keeping fast verification as its default.
- [x] Full audit retains the current semantic comparisons between persisted conversation content and frozen input, including messages, archives, checkpoints, artifacts, and runtime read behavior.
- [x] Full-audit reports and durable evidence record `full` independently from prior or later `fast` results.
- [x] A fast pass is never rendered or stored as a full-audit pass; a full-audit failure does not retroactively erase the fact that fast structural verification passed.
- [x] Full audit remains optional for routine source publication and uses existing source isolation and globally fatal shared-failure handling.
- [ ] End-to-end tests demonstrate that a body-content mismatch is not claimed by fast mode and is detected by full audit.

## Answer

Use `swe conversation-storage verify --manifest ...` for fast verification, or add `--full-audit` for the optional body-level semantic audit. `migrate --apply` remains fast-only and the full audit does not authorize publication. Passing results are stored under separate `verification_results.fast` and `verification_results.full` records; the top-level level remains `fast` once a fast pass exists. The existing verifier retains all semantic checks for full mode.

The database-backed same-fixture mismatch comparison remains pending because this environment has no configured migration test database; unit coverage verifies CLI selection, evidence separation, and existing full-verifier behavior.

## Comments

2026-11-16: Approved ticket breakdown from the fast-verification spec. Parent issue 01 is retained unchanged.
