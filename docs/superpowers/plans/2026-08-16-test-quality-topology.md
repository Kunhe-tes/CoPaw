# Test Quality Topology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Python 3.12 test and quality jobs fail closed, with Swe, subproject, and cross-project contract tests installed and reported independently.

**Architecture:** The root package owns only Swe tests and only exposes `src/` through its test bootstrap. Market, Monitor, and Scheduler test their own packages. The existing cron skill-ID and My MCP runtime tests are split at their Swe–Monitor and Swe–Market interfaces and run from explicit contract-test jobs.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, Ruff, GitHub Actions, editable setuptools packages.

---

## File map

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Root pytest scope and Ruff Python target. |
| `conftest.py` | Root test import path limited to Swe source. |
| `tests/unit/app/test_cron_skill_ids.py` | Swe-only `CronJobSpec` and MonitorSyncClient payload assertions. |
| `contract_tests/swe_monitor/test_cron_skill_ids_contract.py` | Monitor schema and SyncService contract assertions. |
| `contract_tests/swe_market/test_my_mcp_runtime_contract.py` | Shared scope-identity contract assertions. |
| `market/tests/unit/swe_compat/` | Moved Market-only tests now owned by Market. |
| `monitor/tests/swe_compat/` | Moved Monitor-only tests now owned by Monitor. |
| `scheduler/tests/swe_compat/` | Moved Scheduler-only tests now owned by Scheduler. |
| `.github/workflows/tests.yml` | Python 3.12 product, subproject, and contract jobs. |
| `.github/workflows/pre-commit.yml` | Fail-closed Python 3.12 static checks. |

### Task 1: Characterize the new root collection boundary

**Files:**
- Modify: `pyproject.toml:82-90`
- Modify: `conftest.py:10-25`

- [ ] **Step 1: Record the current collection failure.**

Run:

```bash
venv/bin/python -m pytest --collect-only -q
```

Expected: collection includes sibling-package tests and fails when their imports are unavailable.

- [ ] **Step 2: Narrow root pytest and its import bootstrap.**

Replace the root pytest configuration and source list with:

```toml
[tool.pytest.ini_options]
addopts = "--import-mode=importlib"
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

```python
_ROOT = Path(__file__).resolve().parent
_SOURCE_DIRS = [_ROOT / "src"]
```

Keep the stale-module cleanup, but only for `swe`; do not add a sibling source directory back through another test helper.

- [ ] **Step 3: Verify collection does not discover a sibling test path.**

Run:

```bash
venv/bin/python -m pytest --collect-only -q tests | rg 'tests/unit/(market|monitor|scheduler)'
```

Expected: exit status 1 from `rg` (no matching collected node IDs).

- [ ] **Step 4: Commit the isolated root-boundary change.**

```bash
git add pyproject.toml conftest.py
git diff --cached --check
git commit -m "test: limit root collection to swe"
```

### Task 2: Move pure sibling-package tests to their owners

**Files:**
- Move: eight Market-only files under `tests/unit/market/` to `market/tests/unit/swe_compat/`
- Move: all ten files under `tests/unit/monitor/` to `monitor/tests/swe_compat/`
- Move: all four files under `tests/unit/scheduler/` to `scheduler/tests/swe_compat/`

- [ ] **Step 1: Move tests without changing their assertions.**

Run these commands so history remains recognizable:

```bash
mkdir -p market/tests/unit/swe_compat monitor/tests/swe_compat scheduler/tests/swe_compat
git mv tests/unit/market/test_mcp_fs.py tests/unit/market/test_mcp_schemas.py tests/unit/market/test_mcp_service.py tests/unit/market/test_my_mcp.py tests/unit/market/test_runtime_config_store_models.py tests/unit/market/test_schemas.py tests/unit/market/test_skill_zip_download.py tests/unit/market/test_skills_browse.py market/tests/unit/swe_compat/
git mv tests/unit/monitor/*.py monitor/tests/swe_compat/
git mv tests/unit/scheduler/*.py scheduler/tests/swe_compat/
```

- [ ] **Step 2: Run each moved suite from its own project root.**

Run:

```bash
(cd market && ../venv/bin/python -m pytest tests/unit -q)
(cd monitor && ../venv/bin/python -m pytest tests -q)
(cd scheduler && ../venv/bin/python -m pytest tests -q)
```

Expected: each command imports only its installed project and its declared dependencies; no command relies on the root `conftest.py` source-path injection.

- [ ] **Step 3: Commit the test ownership moves.**

```bash
git add market/tests monitor/tests scheduler/tests tests/unit
git diff --cached --check
git commit -m "test: move subproject suites to their owners"
```

### Task 3: Make the Swe–Monitor cron contract explicit

**Files:**
- Modify: `tests/unit/app/test_cron_skill_ids.py:1-150`
- Create: `contract_tests/swe_monitor/test_cron_skill_ids_contract.py`

- [ ] **Step 1: Split the existing test by package ownership.**

Keep in `tests/unit/app/test_cron_skill_ids.py` only assertions against `CronJobSpec` and `MonitorSyncClient._build_job_sync_data`. It must import only `swe`.

Move the following Monitor-owned assertions, together with `_FakeDb` and `_sync_request`, to the contract file:

```python
async def test_monitor_sync_insert_sql_writes_skill_ids(monkeypatch):
    fake_db = _FakeDb(existing=None)
    monkeypatch.setattr(sync_service, "get_db_connection", lambda: fake_db)
    monkeypatch.setattr(sync_service, "_enrich_sync_request", _identity)

    await SyncService().sync_job(_sync_request())

    sql, params = fake_db.executed[0]
    assert "skill_ids" in sql
    assert "foo,bar" in params
```

Also move the corresponding update-SQL and schema-column assertions. The new file imports both `swe.app.crons` and `monitor.app` deliberately; add a module docstring naming it a Swe–Monitor contract test.

- [ ] **Step 2: Run the isolated Swe and contract suites.**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_cron_skill_ids.py -q
venv/bin/python -m pytest contract_tests/swe_monitor/test_cron_skill_ids_contract.py -q
```

Expected: the first command needs only Swe; the second fails clearly until both editable packages are installed.

- [ ] **Step 3: Commit the explicit contract boundary.**

```bash
git add tests/unit/app/test_cron_skill_ids.py contract_tests/swe_monitor
git diff --cached --check
git commit -m "test: isolate swe monitor cron contract"
```

### Task 4: Make the Swe–Market scope-identity contract explicit

**Files:**
- Move: `tests/unit/market/test_my_mcp_runtime.py` to `contract_tests/swe_market/test_my_mcp_runtime_contract.py`

- [ ] **Step 1: Move the test without weakening its cross-package assertion.**

```bash
mkdir -p contract_tests/swe_market
git mv tests/unit/market/test_my_mcp_runtime.py contract_tests/swe_market/test_my_mcp_runtime_contract.py
```

Keep the import of `swe.config.context.encode_scope_id`: it proves that
Market's `resolve_effective_tenant_id` preserves the same scope identity that
Swe encodes. Add a module docstring naming this a Swe–Market contract test.

- [ ] **Step 2: Verify both packages are required explicitly.**

```bash
venv/bin/python -m pip install -e ".[dev]" -e "./market[dev]"
venv/bin/python -m pytest contract_tests/swe_market/test_my_mcp_runtime_contract.py -q
```

Expected: PASS with both packages installed; Market-only CI does not collect
this test.

- [ ] **Step 3: Commit the contract move.**

```bash
git add contract_tests/swe_market tests/unit/market
git diff --cached --check
git commit -m "test: isolate swe market scope contract"
```

### Task 5: Make CI Python-3.12-only and package-aware

**Files:**
- Modify: `.github/workflows/tests.yml:1-330`
- Modify: `.github/workflows/pre-commit.yml:1-45`

- [ ] **Step 1: Replace the compatibility matrix with fixed Python 3.12 jobs.**

In `tests.yml`, remove 3.10/3.13 and multi-OS matrices. Keep `critical-path-tests`, then add these jobs after it:

```yaml
swe-tests:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: "3.12" }
    - run: python -m pip install --upgrade pip
    - run: pip install -e ".[dev,full]"
    - run: pytest tests -v

market-tests:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: "3.12" }
    - run: python -m pip install --upgrade pip
    - run: pip install -e "./market[dev]"
    - run: pytest market/tests -v
```

Create equivalent `monitor-tests` and `scheduler-tests` jobs using their own editable package and test directory. Create `swe-monitor-contract-tests` that installs `.[dev]` and `./monitor[dev]`, then runs `pytest contract_tests/swe_monitor -v`. Create `swe-market-contract-tests` that installs `.[dev]` and `./market[dev]`, then runs `pytest contract_tests/swe_market -v`. Update every `paths` list to include `market/**`, `monitor/**`, `scheduler/**`, `contract_tests/**`, root configuration, and the workflow itself. Add every new job to `test-summary` and fail for any non-success result.

- [ ] **Step 2: Make the static job fail closed on Python 3.12.**

Set `PYTHON: "3.12"` in `pre-commit.yml` and replace its masked command with:

```bash
pre-commit run --all-files
ruff check src/swe tests
```

Add this Ruff target to the root configuration:

```toml
[tool.ruff]
target-version = "py312"
```

- [ ] **Step 3: Validate workflow syntax and the changed local commands.**

Run:

```bash
venv/bin/python -m pytest --collect-only -q tests
venv/bin/ruff check src/swe tests
pre-commit run --files pyproject.toml conftest.py .github/workflows/tests.yml .github/workflows/pre-commit.yml
```

Expected: all commands exit 0. Resolve every Ruff diagnostic rather than suppressing it; Python 3.12 f-string syntax is valid and must not be rewritten for 3.10.

- [ ] **Step 4: Commit the CI topology.**

```bash
git add .github/workflows/tests.yml .github/workflows/pre-commit.yml pyproject.toml
git diff --cached --check
git commit -m "ci: separate python test ownership"
```

### Task 6: Run the complete gate

**Files:**
- Verify only

- [ ] **Step 1: Install each package in a clean Python 3.12 environment or CI-equivalent virtual environment.**

```bash
venv/bin/python -m pip install -e ".[dev,full]"
venv/bin/python -m pip install -e "./market[dev]" -e "./monitor[dev]" -e "./scheduler[dev]"
```

- [ ] **Step 2: Run all ownership boundaries.**

```bash
venv/bin/python -m pytest tests -q
venv/bin/python -m pytest market/tests -q
venv/bin/python -m pytest monitor/tests -q
venv/bin/python -m pytest scheduler/tests -q
venv/bin/python -m pytest contract_tests/swe_monitor -q
venv/bin/python -m pytest contract_tests/swe_market -q
venv/bin/python scripts/run_critical_path_tests.py
venv/bin/ruff check src/swe tests
```

Expected: all eight commands exit 0 and no root test imports a sibling source tree implicitly.
