# Scripts

Run from **repo root**.

## Build wheel (with latest console)

```bash
bash scripts/wheel_build.sh
```

- Builds the console frontend (`console/`), copies `console/dist` to `src/copaw/console/dist`, then builds the wheel. Output: `dist/*.whl`.

## Build website

```bash
bash scripts/website_build.sh
```

- Installs dependencies (pnpm or npm) and runs the Vite build. Output: `website/dist/`.

## Build Docker image

```bash
bash scripts/docker_build.sh [IMAGE_TAG] [EXTRA_ARGS...]
```

- Default tag: `copaw:latest`. Uses `deploy/Dockerfile` (multi-stage: builds console then Python app).
- Example: `bash scripts/docker_build.sh myreg/copaw:v1 --no-cache`.

## Run Test

```bash
# Run all tests
python scripts/run_tests.py

# Run all unit tests
python scripts/run_tests.py -u

# Run unit tests for a specific module
python scripts/run_tests.py -u providers

# Run integration tests
python scripts/run_tests.py -i

# Run all tests and generate a coverage report
python scripts/run_tests.py -a -c

# Run tests in parallel (requires pytest-xdist)
python scripts/run_tests.py -p

# Show help
python scripts/run_tests.py -h
```

## Probe inotify watcher ownership

Enable the runtime watchfiles stack probe before starting the backend:

```bash
export SWE_WATCHFILES_STACK_PROBE_ENABLED=1
export SWE_RUNTIME_DIAGNOSTIC_TOKEN='<secret>'
```

After each matrix step (empty runtime, N workspaces, N MCP clients, N queries),
capture a labeled snapshot:

```bash
python scripts/inotify_matrix_probe.py \
  --pid 1 \
  --label empty \
  --runtime-url 'http://127.0.0.1:8080/api/runtime/inotify-diagnostic?include_fdinfo=true'
```

To drive an interactive matrix in one command, repeat `--label` and add
`--prompt-between-labels`; the probe will pause before each snapshot so you can
perform the corresponding external step:

```bash
python scripts/inotify_matrix_probe.py \
  --pid 1 \
  --runtime-url 'http://127.0.0.1:8080/api/runtime/inotify-diagnostic?include_fdinfo=true' \
  --label empty \
  --label workspaces \
  --label mcp-clients \
  --label queries \
  --prompt-between-labels
```

If each matrix step is captured as a separate JSON file, merge them later and
recompute cross-step deltas:

```bash
python scripts/inotify_matrix_probe.py \
  --from-json /tmp/inotify-empty.json \
  --from-json /tmp/inotify-workspaces.json \
  --from-json /tmp/inotify-mcp-clients.json \
  --from-json /tmp/inotify-queries.json
```

The output includes `/proc/<pid>/fdinfo` inotify counts, bounded fdinfo watch
samples (`wd`, `ino`, `sdev`, `mask`, raw line), native thread name counts,
opt-in `watchfiles.watch`/`awatch` creation stacks, and a
`watchfiles_stack_summary` with function counts, likely owner counts, path
samples, and representative owner stack frames. Linux fdinfo does not include
path names directly; use the inode/device samples together with the runtime
stack summary and matrix deltas to attribute owners.

When multiple `--label` values are provided without `--prompt-between-labels`,
the labels are sampled consecutively without pausing for external matrix
actions. With `--prompt-between-labels`, each label becomes an operator-gated
matrix step. With `--from-json`, each loaded file contributes its captured
snapshots in argument order. The top-level `summary.steps` section reports
per-label totals and `consecutive_delta` values for inotify fd count, inotify
watch count, and native `notify-rs*` thread count.
