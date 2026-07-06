# Request Execution Load Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move first-pass responsiveness-critical runtime-state work off the event-loop thread while preserving current behavior and preparing for later worker isolation.

**Architecture:** Add a package-level runtime worker helper in `src/swe/runtime_workers.py`, then route chat metadata, session JSON, file read/edit, token usage, and provider local configuration boundaries through it. The helper initially delegates to `asyncio.to_thread`; it intentionally does not introduce a dedicated executor yet.

**Tech Stack:** Python 3.12, asyncio, pytest, pytest-asyncio, pydantic models, existing JSON file repositories.

---

## File Structure

- Create `src/swe/runtime_workers.py`
  - Owns the thin `run_runtime_state_work()` helper.
  - Preserves contextvars by delegating to `asyncio.to_thread`.
  - Must not import FastAPI app modules.

- Modify `src/swe/app/runner/repo/json_repo.py`
  - Move full chat repository load/save work into sync helper methods.
  - Add file signature snapshot and chat-id index, following `JsonJobRepository`.

- Modify `src/swe/app/runner/session.py`
  - Move full JSON session read/parse and serialize/write boundaries into runtime-state worker calls.
  - Keep existing path-level lock semantics.
  - Do not add session snapshot/cache.

- Modify `src/swe/agents/tools/file_io.py`
  - Keep argument parsing, tenant path validation, tool errors, and response assembly on the async path.
  - Move file read and data-size-dependent text processing for `read_file` and `edit_file` into runtime-state worker calls.

- Modify `src/swe/token_usage/manager.py`
  - Move token usage load/normalize and serialize/write boundaries into runtime-state worker calls.

- Modify `src/swe/providers/provider_manager.py`
  - Add async local config persistence wrappers for API/runtime paths.
  - Keep sync persistence helpers available for constructors, CLI, and storage initialization paths.

- Test files:
  - Create `tests/unit/test_runtime_workers.py`
  - Create or modify `tests/unit/app/test_chat_json_repo.py`
  - Modify `tests/unit/app/test_runner_session.py`
  - Modify or create `tests/unit/agents/test_file_io_runtime_workers.py`
  - Modify `tests/unit/token_usage/test_tenant_token_usage.py`
  - Modify `tests/unit/providers/test_provider_manager.py`

## Task 1: Add Runtime-State Worker Helper

**Files:**
- Create: `src/swe/runtime_workers.py`
- Create: `tests/unit/test_runtime_workers.py`

- [ ] **Step 1: Write failing tests for context propagation and invocation**

Add `tests/unit/test_runtime_workers.py`:

```python
# -*- coding: utf-8 -*-
"""Tests for runtime-state worker helpers."""

from __future__ import annotations

from contextvars import ContextVar

import pytest

from swe.runtime_workers import run_runtime_state_work


_scope = ContextVar("scope", default="")


@pytest.mark.asyncio
async def test_run_runtime_state_work_preserves_contextvars() -> None:
    _scope.set("tenant-a.source-b")

    def read_scope() -> str:
        return _scope.get()

    assert await run_runtime_state_work(read_scope) == "tenant-a.source-b"


@pytest.mark.asyncio
async def test_run_runtime_state_work_passes_args_and_kwargs() -> None:
    def combine(left: str, right: str, *, separator: str) -> str:
        return f"{left}{separator}{right}"

    result = await run_runtime_state_work(
        combine,
        "runtime",
        "state",
        separator="-",
    )

    assert result == "runtime-state"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/test_runtime_workers.py -q
```

Expected: import failure for `swe.runtime_workers`.

- [ ] **Step 3: Implement the helper**

Create `src/swe/runtime_workers.py`:

```python
# -*- coding: utf-8 -*-
"""Runtime worker boundaries for responsiveness-critical state work."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def run_runtime_state_work(
    func: Callable[..., T],
    /,
    *args,
    **kwargs,
) -> T:
    """Run responsiveness-critical runtime-state work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/test_runtime_workers.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit checkpoint**

Run:

```bash
git add src/swe/runtime_workers.py tests/unit/test_runtime_workers.py
git commit -m "feat(runtime): add runtime state worker helper"
```

## Task 2: Offload and Cache Chat JSON Repository

**Files:**
- Modify: `src/swe/app/runner/repo/json_repo.py`
- Create: `tests/unit/app/test_chat_json_repo.py`

- [ ] **Step 1: Write failing boundary and snapshot tests**

Add `tests/unit/app/test_chat_json_repo.py`:

```python
# -*- coding: utf-8 -*-
"""Tests for JSON chat repository runtime-state worker boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swe.app.runner.models import ChatSpec, ChatsFile
from swe.app.runner.repo.json_repo import JsonChatRepository


@pytest.mark.asyncio
async def test_chat_repo_load_uses_runtime_state_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "chats.json"
    path.write_text(
        json.dumps(
            ChatsFile(
                version=1,
                chats=[ChatSpec(session_id="s1", user_id="u1", channel="console")],
            ).model_dump(mode="json"),
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "swe.app.runner.repo.json_repo.run_runtime_state_work",
        fake_worker,
    )

    repo = JsonChatRepository(path)
    loaded = await repo.load()

    assert [chat.session_id for chat in loaded.chats] == ["s1"]
    assert calls == ["_load_sync"]


@pytest.mark.asyncio
async def test_chat_repo_save_uses_runtime_state_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "chats.json"
    calls: list[str] = []

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "swe.app.runner.repo.json_repo.run_runtime_state_work",
        fake_worker,
    )

    repo = JsonChatRepository(path)
    await repo.save(
        ChatsFile(
            version=1,
            chats=[ChatSpec(session_id="s1", user_id="u1", channel="console")],
        ),
    )

    assert calls == ["_save_sync"]
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["chats"][0]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_chat_repo_get_chat_reuses_valid_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = JsonChatRepository(tmp_path / "chats.json")
    chat = ChatSpec(session_id="s1", user_id="u1", channel="console")
    await repo.save(ChatsFile(version=1, chats=[chat]))

    async def fail_worker(func, /, *args, **kwargs):
        if func.__name__ == "_load_sync":
            raise AssertionError("snapshot should avoid full reload")
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "swe.app.runner.repo.json_repo.run_runtime_state_work",
        fail_worker,
    )

    loaded = await repo.get_chat(chat.id)

    assert loaded is not None
    assert loaded.session_id == "s1"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/app/test_chat_json_repo.py -q
```

Expected: import or attribute failure because `run_runtime_state_work`, `_load_sync`, `_save_sync`, or snapshot support is not present.

- [ ] **Step 3: Implement file signature, sync helpers, worker calls, and index**

Modify `src/swe/app/runner/repo/json_repo.py` to include:

```python
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from swe.runtime_workers import run_runtime_state_work


@dataclass(frozen=True)
class _FileSignature:
    exists: bool
    mtime_ns: int | None = None
    size: int | None = None
```

Inside `JsonChatRepository.__init__` add:

```python
self._snapshot_signature: _FileSignature | None = None
self._snapshot: ChatsFile | None = None
self._chat_index: dict[str, ChatSpec] = {}
```

Add methods:

```python
def _file_signature(self) -> _FileSignature:
    if not self._path.exists():
        return _FileSignature(exists=False)
    stat_result = self._path.stat()
    return _FileSignature(
        exists=True,
        mtime_ns=stat_result.st_mtime_ns,
        size=stat_result.st_size,
    )


def _load_sync(self) -> tuple[_FileSignature, ChatsFile]:
    if not self._path.exists():
        return self._file_signature(), ChatsFile(version=1, chats=[])
    data = json.loads(self._path.read_text(encoding="utf-8"))
    chats_file = ChatsFile.model_validate(data)
    return self._file_signature(), chats_file


def _save_sync(self, chats_file: ChatsFile) -> _FileSignature:
    self._path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
    payload = chats_file.model_dump(mode="json")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    shutil.move(str(tmp_path), str(self._path))
    return self._file_signature()


def _set_snapshot(
    self,
    signature: _FileSignature,
    chats_file: ChatsFile,
) -> None:
    self._snapshot_signature = signature
    self._snapshot = chats_file
    self._chat_index = {chat.id: chat for chat in chats_file.chats}
```

Replace `load`, `save`, and override `get_chat`:

```python
async def load(self) -> ChatsFile:
    signature, chats_file = await run_runtime_state_work(self._load_sync)
    self._set_snapshot(signature, chats_file)
    return chats_file


async def save(self, chats_file: ChatsFile) -> None:
    signature = await run_runtime_state_work(self._save_sync, chats_file)
    self._set_snapshot(signature, chats_file)


async def get_chat(self, chat_id: str) -> ChatSpec | None:
    signature = await run_runtime_state_work(self._file_signature)
    if self._snapshot is not None and self._snapshot_signature == signature:
        return self._chat_index.get(chat_id)
    await self.load()
    return self._chat_index.get(chat_id)
```

- [ ] **Step 4: Run targeted tests**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/app/test_chat_json_repo.py tests/unit/app/test_chat_pagination.py tests/unit/app/test_chat_manager_agent_metadata.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit checkpoint**

Run:

```bash
git add src/swe/app/runner/repo/json_repo.py tests/unit/app/test_chat_json_repo.py
git commit -m "perf(runtime): offload chat metadata repository work"
```

## Task 3: Offload Full Session JSON Boundaries

**Files:**
- Modify: `src/swe/app/runner/session.py`
- Modify: `tests/unit/app/test_runner_session.py`
- Modify: `tests/unit/app/test_session_state_merge_coordination.py`

- [ ] **Step 1: Write failing boundary tests**

Add tests to `tests/unit/app/test_runner_session.py`:

```python
@pytest.mark.asyncio
async def test_session_load_uses_runtime_state_worker(
    tmp_path,
    monkeypatch,
) -> None:
    from swe.app.runner.session import SafeJSONSession

    session = SafeJSONSession(save_dir=str(tmp_path))
    await session.save_merged_state("s1", user_id="u1", state={"memory": {"x": 1}})
    calls: list[str] = []

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr("swe.app.runner.session.run_runtime_state_work", fake_worker)

    loaded = await session.get_session_state_dict("s1", user_id="u1")

    assert loaded["memory"]["x"] == 1
    assert "_read_json_state_sync" in calls


@pytest.mark.asyncio
async def test_session_save_serializes_inside_runtime_state_worker(
    tmp_path,
    monkeypatch,
) -> None:
    from swe.app.runner.session import SafeJSONSession

    session = SafeJSONSession(save_dir=str(tmp_path))
    calls: list[str] = []

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr("swe.app.runner.session.run_runtime_state_work", fake_worker)

    await session.save_merged_state("s1", user_id="u1", state={"memory": {"x": 1}})

    assert "_write_json_state_sync" in calls
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/app/test_runner_session.py::test_session_load_uses_runtime_state_worker tests/unit/app/test_runner_session.py::test_session_save_serializes_inside_runtime_state_worker -q
```

Expected: missing helper or missing sync function failure.

- [ ] **Step 3: Implement sync JSON helpers and route session methods through them**

Modify `src/swe/app/runner/session.py` imports:

```python
from swe.runtime_workers import run_runtime_state_work
```

Add sync helpers near `_write_json_text`:

```python
def _read_json_state_sync(
    session_save_path: str,
    *,
    allow_not_exist: bool,
) -> tuple[bool, dict[str, Any]]:
    if not os.path.exists(session_save_path):
        if allow_not_exist:
            return False, {}
        raise ValueError(
            "Failed to load session state for file "
            f"{session_save_path} because it does not exist.",
        )
    with open(
        session_save_path,
        "r",
        encoding="utf-8",
        errors="surrogatepass",
    ) as file:
        content = file.read()
    states = json.loads(content) if content.strip() else {}
    if not isinstance(states, dict):
        raise ValueError(
            f"Session file {session_save_path} does not contain a JSON object.",
        )
    return True, states


def _read_existing_state_for_save_sync(session_save_path: str) -> dict[str, Any]:
    if not os.path.exists(session_save_path):
        return {}
    try:
        _, state = _read_json_state_sync(
            session_save_path,
            allow_not_exist=True,
        )
        return state
    except json.JSONDecodeError:
        logger.warning(
            "Failed to parse existing session state at %s; overwriting with current state.",
            session_save_path,
        )
        return {}


def _write_json_state_sync(session_save_path: str, state: dict[str, Any]) -> None:
    _write_json_text(session_save_path, json.dumps(state, ensure_ascii=False))
```

Update `_read_session_state_file`, `_read_existing_state_for_save`, `save_session_state`, `save_merged_state`, and `mutate_session_state` so that all `json.loads` and `json.dumps` for persisted session files occur inside these sync helpers via `run_runtime_state_work`.

- [ ] **Step 4: Run targeted session tests**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/app/test_runner_session.py tests/unit/app/test_session_state_merge_coordination.py tests/unit/app/test_cron_task_session_cleanup.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit checkpoint**

Run:

```bash
git add src/swe/app/runner/session.py tests/unit/app/test_runner_session.py
git commit -m "perf(runtime): offload session json state boundaries"
```

## Task 4: Offload File Read and Edit Data Processing

**Files:**
- Modify: `src/swe/agents/tools/file_io.py`
- Create: `tests/unit/agents/test_file_io_runtime_workers.py`
- Existing related tests: `tests/unit/test_file_tools_agent_workspace_default.py`, `tests/unit/agents/test_file_io_cancellation.py`

- [ ] **Step 1: Write failing boundary tests**

Create `tests/unit/agents/test_file_io_runtime_workers.py`:

```python
# -*- coding: utf-8 -*-
"""Tests for file tool runtime-state worker boundaries."""

from __future__ import annotations

import pytest

from swe.agents.tools import file_io


@pytest.mark.asyncio
async def test_read_file_uses_runtime_state_worker(tmp_path, monkeypatch) -> None:
    target = tmp_path / "note.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(file_io, "_resolve_file_path", lambda value: str(target))

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(file_io, "run_runtime_state_work", fake_worker)

    result = await file_io.read_file("note.txt")

    assert "alpha" in result.content[0].text
    assert "_read_file_selection_sync" in calls


@pytest.mark.asyncio
async def test_edit_file_uses_runtime_state_worker_for_text_replacement(
    tmp_path,
    monkeypatch,
) -> None:
    target = tmp_path / "note.txt"
    target.write_text("alpha beta", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(file_io, "_resolve_file_path", lambda value: str(target))

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(file_io, "run_runtime_state_work", fake_worker)

    await file_io.edit_file("note.txt", "beta", "gamma")

    assert "_replace_file_text_sync" in calls
    assert target.read_text(encoding="utf-8") == "alpha gamma"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/agents/test_file_io_runtime_workers.py -q
```

Expected: missing `run_runtime_state_work` import or missing sync helper failure.

- [ ] **Step 3: Implement sync selection and replacement helpers**

Modify `src/swe/agents/tools/file_io.py` imports:

```python
from swe.runtime_workers import run_runtime_state_work
```

Add helpers above `read_file`:

```python
def _read_file_selection_sync(
    file_path: str,
    *,
    start_line: int | None,
    end_line: int | None,
) -> tuple[str, int, int, int]:
    content = read_file_safe(file_path)
    all_lines = content.split("\n")
    total = len(all_lines)
    selected_start = max(1, start_line if start_line is not None else 1)
    selected_end = min(total, end_line if end_line is not None else total)
    if selected_start > total:
        raise ValueError(
            f"start_line {selected_start} exceeds file length ({total} lines).",
        )
    if selected_start > selected_end:
        raise ValueError(
            f"start_line ({selected_start}) > end_line ({selected_end}).",
        )
    return (
        "\n".join(all_lines[selected_start - 1 : selected_end]),
        selected_start,
        selected_end,
        total,
    )


def _replace_file_text_sync(
    file_path: str,
    old_text: str,
    new_text: str,
) -> str:
    content = read_file_safe(file_path)
    if old_text not in content:
        raise ValueError(f"text to replace was not found in {file_path}")
    return content.replace(old_text, new_text)
```

Update `read_file` to call:

```python
selected_content, s, e, total = await run_runtime_state_work(
    _read_file_selection_sync,
    file_path,
    start_line=start_line,
    end_line=end_line,
)
```

Update `edit_file` to call:

```python
new_content = await run_runtime_state_work(
    _replace_file_text_sync,
    resolved_path,
    old_text,
    new_text,
)
await write_file(file_path=resolved_path, content=new_content)
```

Map `ValueError` messages back to existing `ToolExecutionError` categories so user-facing behavior remains stable.

- [ ] **Step 4: Run file tool tests**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/agents/test_file_io_runtime_workers.py tests/unit/test_file_tools_agent_workspace_default.py tests/unit/agents/test_file_io_cancellation.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit checkpoint**

Run:

```bash
git add src/swe/agents/tools/file_io.py tests/unit/agents/test_file_io_runtime_workers.py
git commit -m "perf(tools): offload file read and edit processing"
```

## Task 5: Offload Token Usage Persistence

**Files:**
- Modify: `src/swe/token_usage/manager.py`
- Modify: `tests/unit/token_usage/test_tenant_token_usage.py`

- [ ] **Step 1: Write failing boundary test**

Add to `tests/unit/token_usage/test_tenant_token_usage.py`:

```python
def test_token_usage_record_uses_runtime_state_worker(
    tmp_path,
    monkeypatch,
) -> None:
    from swe.token_usage import manager as manager_module

    manager = manager_module.TokenUsageManager(path=tmp_path / "token_usage.json")
    calls: list[str] = []

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(manager_module, "run_runtime_state_work", fake_worker)

    import asyncio

    asyncio.run(
        manager.record(
            provider_id="openai",
            model_name="gpt-test",
            prompt_tokens=3,
            completion_tokens=5,
        ),
    )

    assert "_load_data_sync" in calls
    assert "_save_data_sync" in calls
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/token_usage/test_tenant_token_usage.py::test_token_usage_record_uses_runtime_state_worker -q
```

Expected: missing `run_runtime_state_work`, `_load_data_sync`, or `_save_data_sync`.

- [ ] **Step 3: Implement sync load/save helpers**

Modify `src/swe/token_usage/manager.py` imports:

```python
from swe.runtime_workers import run_runtime_state_work
```

Add methods:

```python
def _load_data_sync(self) -> dict:
    if not self._path.exists():
        return {}
    try:
        raw = self._path.read_text(encoding="utf-8")
        return self._normalize_data(json.loads(raw) if raw.strip() else {})
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read token usage file %s: %s", self._path, e)
        return {}


def _save_data_sync(self, data: dict) -> None:
    try:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning("Failed to write token usage to %s: %s", self._path, e)
```

Replace async `_load_data` and `_save_data` bodies:

```python
async def _load_data(self) -> dict:
    return await run_runtime_state_work(self._load_data_sync)


async def _save_data(self, data: dict) -> None:
    await run_runtime_state_work(self._save_data_sync, data)
```

- [ ] **Step 4: Run token usage tests**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/token_usage/test_tenant_token_usage.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit checkpoint**

Run:

```bash
git add src/swe/token_usage/manager.py tests/unit/token_usage/test_tenant_token_usage.py
git commit -m "perf(runtime): offload token usage persistence"
```

## Task 6: Add Async Provider Local Config Persistence Wrappers

**Files:**
- Modify: `src/swe/providers/provider_manager.py`
- Modify: `tests/unit/providers/test_provider_manager.py`

- [ ] **Step 1: Write failing boundary tests for async API paths**

Add to `tests/unit/providers/test_provider_manager.py` near provider persistence tests:

```python
@pytest.mark.asyncio
async def test_add_custom_provider_uses_runtime_state_worker_for_local_save(
    tmp_path,
    monkeypatch,
) -> None:
    from swe.providers import provider_manager as manager_module
    from swe.providers.models import ProviderInfo

    manager = manager_module.ProviderManager(root_path=tmp_path / "providers")
    calls: list[str] = []

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(manager_module, "run_runtime_state_work", fake_worker)

    provider = ProviderInfo(
        id="custom-openai",
        name="Custom OpenAI",
        chat_model="OpenAIChatModel",
        api_key="sk-test",
        base_url="https://example.test/v1",
        models=[],
        extra_models=[],
        is_custom=True,
    )

    await manager.add_custom_provider(provider)

    assert "_save_provider" in calls
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/providers/test_provider_manager.py::test_add_custom_provider_uses_runtime_state_worker_for_local_save -q
```

Expected: sync `_save_provider` is called directly, so `calls` is empty.

- [ ] **Step 3: Add async wrappers and route async methods through them**

Modify imports:

```python
from swe.runtime_workers import run_runtime_state_work
```

Add methods near `_save_provider`:

```python
async def _save_provider_async(
    self,
    provider: Provider,
    is_builtin: bool = False,
    skip_if_exists: bool = False,
) -> None:
    await run_runtime_state_work(
        self._save_provider,
        provider,
        is_builtin=is_builtin,
        skip_if_exists=skip_if_exists,
    )


async def _save_active_model_async(
    self,
    active_model: ModelSlotConfig,
) -> None:
    await run_runtime_state_work(self.save_active_model, active_model)
```

Update async runtime methods only:

```python
async def fetch_provider_models(...):
    ...
    await self._save_provider_async(
        provider,
        is_builtin=provider_id in self.builtin_providers,
    )

async def add_custom_provider(...):
    ...
    await self._save_provider_async(provider, is_builtin=False)

async def activate_model(...):
    ...
    await self._save_active_model_async(self.active_model)

async def add_model_to_provider(...):
    ...
    await self._save_provider_async(...)

async def delete_model_from_provider(...):
    ...
    await self._save_provider_async(...)

async def probe_model_multimodal(...):
    ...
    await self._save_provider_async(...)
```

Keep sync methods such as `_init_from_storage`, CLI helpers, `overwrite_provider_payload`, and `update_provider` sync unless their call sites are intentionally migrated in a later task.

- [ ] **Step 4: Run provider tests**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/providers/test_provider_manager.py tests/integration/test_provider_api_tenant.py -q
```

Expected: selected provider tests pass.

- [ ] **Step 5: Commit checkpoint**

Run:

```bash
git add src/swe/providers/provider_manager.py tests/unit/providers/test_provider_manager.py
git commit -m "perf(providers): offload async provider config writes"
```

## Task 7: Full First-Pass Verification

**Files:**
- No production files expected.
- Verify docs changed earlier remain staged or committed separately: `CONTEXT.md`, `docs/adr/0011-request-execution-load-avoids-event-loop-blocking-work.md`.

- [ ] **Step 1: Run first-pass focused suite**

Run:

```bash
../../venv/bin/python -m pytest \
  tests/unit/test_runtime_workers.py \
  tests/unit/app/test_chat_json_repo.py \
  tests/unit/app/test_chat_pagination.py \
  tests/unit/app/test_chat_manager_agent_metadata.py \
  tests/unit/app/test_runner_session.py \
  tests/unit/app/test_session_state_merge_coordination.py \
  tests/unit/app/test_cron_task_session_cleanup.py \
  tests/unit/agents/test_file_io_runtime_workers.py \
  tests/unit/test_file_tools_agent_workspace_default.py \
  tests/unit/agents/test_file_io_cancellation.py \
  tests/unit/token_usage/test_tenant_token_usage.py \
  tests/unit/providers/test_provider_manager.py \
  tests/integration/test_provider_api_tenant.py
```

Expected: all selected tests pass.

- [ ] **Step 2: Run app startup smoke tests**

Run:

```bash
../../venv/bin/python -m pytest tests/integrated/test_app_startup.py tests/unit/cli/test_app_cmd.py -q
```

Expected: startup and uvloop CLI tests pass.

- [ ] **Step 3: Inspect diff for helper misuse**

Run:

```bash
git diff -- src/swe/runtime_workers.py src/swe/app/runner/repo/json_repo.py src/swe/app/runner/session.py src/swe/agents/tools/file_io.py src/swe/token_usage/manager.py src/swe/providers/provider_manager.py
```

Expected:
- `run_runtime_state_work` appears only in first-pass runtime-state paths.
- Archive, backup, search, provider cold-start, and transcription paths do not use `run_runtime_state_work`.
- Session state has no new snapshot/cache.

- [ ] **Step 4: Commit verification/doc checkpoint**

Run:

```bash
git add CONTEXT.md docs/adr/0011-request-execution-load-avoids-event-loop-blocking-work.md docs/superpowers/plans/2026-07-03-request-execution-load-cleanup.md
git commit -m "docs(runtime): define request execution load cleanup plan"
```

## Self-Review

- Spec coverage: The plan covers first-pass scope from ADR 0011: chat repo, session JSON, file read/edit, token usage, provider local config writes, runtime-state helper, and worker-boundary tests.
- Out of scope: archive, backup, search, provider cold-start, workspace zip, and transcription worker isolation. These remain second-stage work.
- Type consistency: The helper is consistently named `run_runtime_state_work`; planned sync helper names are module-local and explicit.
- Test consistency: Every implementation task includes a failing boundary test and a targeted passing command.
