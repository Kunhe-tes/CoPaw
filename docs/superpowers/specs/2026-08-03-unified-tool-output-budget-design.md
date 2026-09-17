# Unified Tool Output Budget and Recoverable Reference

## Goal

Use `running.tool_result_compact` as the sole configuration source for
textual tool-output compression. Every textual tool result must follow one
bounded, recoverable protocol before it enters the next model context.

This replaces the independent `file_read_truncation` system-feature setting.

## Configuration contract

`tool_result_compact` remains the only output-budget configuration:

- `enabled`: enables both immediate and historical textual-result compaction.
- `recent_max_bytes`: strict byte budget for a newly completed textual tool
  result and for results in the recent history window.
- `old_max_bytes`: strict byte budget for textual results outside the recent
  history window.
- `recent_n`: minimum number of trailing tool-result messages using the recent
  budget during historical compaction.
- `retention_days`: retention period for recoverable full-output artifacts.

The old `file_read_truncation` registry entries, runtime resolver, API payload,
console controls, and tests are removed. A disabled `tool_result_compact`
configuration leaves textual outputs unmodified and creates no artifacts.

## Canonical output protocol

The application owns one text compactor, used for all textual tool-result
shapes: string outputs, text blocks in `content`, and nested text-bearing
content. Image, audio, file, and other non-text blocks are preserved without
byte slicing.

When textual output exceeds its budget, the compactor:

1. Writes the complete original text atomically to
   `<tenant-workspace>/tool_result/<opaque-id>.txt`.
2. Returns a UTF-8-safe, line-aware excerpt whose complete returned text,
   including the notice, does not exceed the configured budget.
3. Appends one `<<<TRUNCATED>>>` notice containing the original and retained
   byte counts, the artifact path, and a `read_file` continuation instruction.

The notice is the sole signal that a result has been compacted. A later
historical compaction must retain the original artifact reference, update only
the displayed excerpt and continuation position, and never write an already
truncated excerpt as though it were the full output.

For a single line larger than the available excerpt budget, the result still
contains a truncation notice and a valid `read_file` reference; it must not
silently return an unmarked partial line.

## Execution flow

```text
tool response
  -> canonical text compactor (recent_max_bytes, artifact write)
  -> tool_result stored in memory and emitted to the client
  -> before later model turns: historical compactor
       recent window: recent_max_bytes
       older output: old_max_bytes
       preserve artifact reference
  -> retention cleanup deletes expired artifacts
```

The canonical compactor is applied at the shared tool-result boundary, rather
than in individual tools. This covers built-in, shell, and MCP textual results.
The existing shell-specific terminal-output truncator is removed.

Live shell frames are presentation-only. Their server-provided budget derives
from the same `recent_max_bytes` value and the client consumes that budget; the
front end must not maintain a separate hard-coded 64 KiB output budget. Live
stream limits do not replace the terminal-result compactor.

## Historical compaction integration

The memory-compaction hook continues to run before reasoning and continues to
select recent versus old messages with `recent_n`. Its implementation is
adapted so the ReMe delegation cannot reintroduce a second truncation format,
a byte-limit slack, a Markdown-only exemption, or a duplicate artifact.

Artifact cleanup uses `retention_days`. Expired artifacts are recoverable only
until the configured retention limit; the truncation notice remains readable
after cleanup and identifies the path that expired.

## Error handling and safety

- Artifact-write failure must leave the original output intact rather than
  claim it can be recovered.
- Artifact paths remain inside the tenant workspace and use opaque generated
  file names.
- Byte accounting uses UTF-8 with replacement-safe encoding.
- The compactor must bound output during capture/normalization, avoiding a
  second unbounded shell-specific terminal buffer where feasible.

## Tests

- Immediate built-in, shell, and MCP text results use `recent_max_bytes`.
- A compacted result is strictly within budget and can be recovered with the
  path and continuation described by its notice.
- A later old-message compaction uses `old_max_bytes` while keeping the same
  artifact reference.
- Source-level `tool_result_compact` overrides apply to both immediate and
  historical behavior; disabling it bypasses both.
- Very long single lines, invalid UTF-8 replacement, multi-block output, and
  artifact-write failure retain truthful protocol semantics.
- Live shell output and its final result use the same configured byte budget;
  no independent client-side 64 KiB threshold remains.
- Configuration/API/console regression tests prove that
  `file_read_truncation` no longer exists.

## Out of scope

- Compressing or transforming binary/media payloads.
- Changing the model provider's own context-window enforcement.
- Retaining artifacts beyond the configured `retention_days`.
