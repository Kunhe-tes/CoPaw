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

The output includes `/proc/<pid>/fdinfo` inotify counts, native thread name
counts, and opt-in `watchfiles.watch`/`awatch` creation stacks.
