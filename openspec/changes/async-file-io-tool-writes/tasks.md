## 1. File Tool Write Regression Coverage

- [x] 1.1 Update or add focused tests proving `write_file` and `append_file`
  keep unrelated event-loop work running during slow writes.
- [x] 1.2 Preserve cancellation regression coverage for both overwrite and
  append flows so cancelled writes leave the target file unchanged and clean up
  temp files.
- [x] 1.3 Keep diagnostics-focused tests covering write metadata logging
  without leaking file content.

## 2. Conservative Write-Path Offload

- [x] 2.1 Update the shared temp-file write helper in
  `src/swe/agents/tools/file_io.py` to use `aiofiles` for the filesystem write
  phase.
- [x] 2.2 Keep the existing per-path lock, temp-file replacement, and cancel
  cleanup control flow intact while routing `write_file` through the new helper.
- [x] 2.3 Route `append_file` through the same non-blocking write helper while
  preserving its current read-modify-write behavior and encoding rules.

## 3. Verification

- [x] 3.1 Run the focused file I/O unit tests covering cancellation, workspace
  defaults, and watchdog diagnostics.
- [x] 3.2 Run the relevant broader unit-test subset for agent tool behavior and
  fix any regressions.
- [x] 3.3 Inspect the final OpenSpec change status and confirm the change is
  ready for `/opsx:apply`.
