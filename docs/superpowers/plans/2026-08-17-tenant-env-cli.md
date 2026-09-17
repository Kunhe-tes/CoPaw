# Tenant Runtime Environment CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `swe env` manage a required tenant/source scope through the existing local HTTP API.

**Architecture:** Keep `src/swe/app/routers/envs.py` unchanged and turn `src/swe/cli/env_cmd.py` into a narrow HTTP client. The CLI obtains the base URL from the root Click context, sends the selected scope as request headers, and renders API data without exposing values by default.

**Tech Stack:** Python, Click, httpx, pytest, unittest.mock.

---

### Task 1: Specify CLI HTTP behavior with tests

**Files:**
- Create: `tests/unit/cli/test_cli_env.py`
- Reference: `tests/unit/cli/test_cli_cron_tenant.py`

- [x] **Step 1: Write failing tests**

```python
def test_env_list_masks_values_and_passes_scope_headers():
    result = runner.invoke(
        env_group,
        ["list", "--tenant-id", "tenant-a", "--source-id", "source-a"],
    )
    assert result.exit_code == 0
    assert "secret" not in result.output
    assert headers == {"X-Tenant-Id": "tenant-a", "X-Source-Id": "source-a"}

def test_env_set_sends_patch_without_echoing_value():
    result = runner.invoke(
        env_group,
        ["set", "API_TOKEN", "secret", "--tenant-id", "tenant-a", "--source-id", "source-a"],
    )
    assert result.exit_code == 0
    assert payload == {"values": {"API_TOKEN": "secret"}}
    assert "secret" not in result.output
```

Add tests for `--show-values`, delete URL/header behavior, required tenant/source options, root `--host/--port` forwarding, and a 404 error becoming exit code 1.

- [x] **Step 2: Run the test file and verify it fails**

Run: `venv/bin/python -m pytest tests/unit/cli/test_cli_env.py -v`

Expected: FAIL because the current commands call the local environment store and do not define required scope options or HTTP calls.

### Task 2: Convert environment commands into API clients

**Files:**
- Modify: `src/swe/cli/env_cmd.py:1-65`
- Test: `tests/unit/cli/test_cli_env.py`

- [x] **Step 1: Add scoped request helpers**

```python
def _headers(tenant_id: str, source_id: str) -> dict[str, str]:
    return {"X-Tenant-Id": tenant_id, "X-Source-Id": source_id}

def _base_url(ctx: click.Context) -> str:
    return resolve_base_url(ctx, None)
```

Add a response-error helper that turns the API `detail` field into `click.ClickException` and preserves `httpx` failures for unexpected response bodies.

- [x] **Step 2: Implement commands with the existing API contract**

```python
GET    /envs                 # list
PATCH  /envs {"values": ...} # set
DELETE /envs/{encoded-key}  # delete
```

Apply required `--tenant-id` and `--source-id` options to every command. Add `--show-values` only to `list`, mask each non-empty value by default, and print key-only success messages for `set` and `delete`.

- [x] **Step 3: Run the focused test file**

Run: `venv/bin/python -m pytest tests/unit/cli/test_cli_env.py -v`

Expected: PASS.

### Task 3: Verify compatibility and scope

**Files:**
- Verify: `src/swe/cli/env_cmd.py`
- Verify: `tests/unit/cli/test_cli_env.py`

- [x] **Step 1: Run focused CLI regression tests**

Run: `venv/bin/python -m pytest tests/unit/cli/test_cli_env.py tests/unit/cli/test_cli_cron_tenant.py tests/unit/cli/test_cli_agents_scope.py -v`

Expected: PASS.

- [x] **Step 2: Inspect the diff**

Run: `git diff --check && git diff -- src/swe/cli/env_cmd.py tests/unit/cli/test_cli_env.py CONTEXT.md docs/superpowers/specs/2026-08-17-tenant-env-cli-design.md`

Expected: no whitespace errors and no change to `/api/envs` routes.
