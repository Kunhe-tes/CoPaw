## 1. Session Snapshot Foundations

- [x] 1.1 Define the top-level session skill snapshot schema and add load/save helpers in the runner/session layer.
- [x] 1.2 Add a recursive skill-directory freshness-token helper based on the latest tracked-tree `mtime`.
- [x] 1.3 Add snapshot entry creation/update/removal helpers for `skill_name`, `resolved_skill_dir`, and `freshness_token`.

## 2. Runtime Freshness Flow

- [x] 2.1 Persist a snapshot entry immediately when a skill reaches confirmed association during a turn.
- [x] 2.2 Insert next-turn freshness checking into the runner lifecycle after `load_session_state()` and before `rebuild_sys_prompt()`.
- [x] 2.3 Detect same-directory token changes, associated skill directory switches, effective skill withdrawals, and missing-skill cleanup against the stored snapshot.
- [x] 2.4 Rebuild prompt state and inject one aggregated model-only freshness notice for changed skills in the current turn.
- [x] 2.5 Persist the applied snapshot immediately after refresh handling so the same change does not re-trigger on later turns.

## 3. Verification

- [x] 3.1 Add unit tests for snapshot persistence, immediate confirmed-association capture, and top-level session-state storage.
- [x] 3.2 Add runner lifecycle tests for no-change turns, directory freshness-token changes, directory switches, and effective skill withdrawals.
- [x] 3.3 Add notice tests covering one-turn scope, aggregated formatting, cautious “detected skill-directory change” wording, and `old -> new` directory switch paths.
- [x] 3.4 Add regression tests proving missing associated skills are silently removed without triggering refresh or notice.
