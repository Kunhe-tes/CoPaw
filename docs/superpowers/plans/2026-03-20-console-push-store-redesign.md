# Console Push Store Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `console_push_store.py` so that all read operations (`get_recent`, `take`, `take_all`) consume messages exactly once - returned messages are immediately removed from storage.

**Architecture:** Modify `get_recent()` to return AND remove messages (matching `take` behavior). Keep memory-only storage with asyncio.Lock for concurrency. Update tests to reflect new consume-on-read semantics.

**Tech Stack:** Python 3.9+, pytest, pytest-asyncio

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/copaw/app/console_push_store.py` | Core storage module with consume-on-read semantics |
| `tests/test_console_push_store.py` | Unit tests for all storage operations |

---

## Task 1: Update `get_recent()` to Consume Messages

**Files:**
- Modify: `src/copaw/app/console_push_store.py:75-93`
- Test: `tests/test_console_push_store.py:66-78`

### Step 1.1: Write failing test for consume-on-read behavior

```python
@pytest.mark.asyncio
async def test_get_recent_consumes_messages():
    """测试 get_recent 消费消息 - 返回后消息被删除"""
    from copaw.app.console_push_store import append, get_recent

    await append("alice", "session_1", "Recent message")

    # First call - should return and consume message
    messages1 = await get_recent("alice", max_age_seconds=60)
    assert len(messages1) == 1
    assert messages1[0]["text"] == "Recent message"

    # Second call - should return empty (message already consumed)
    messages2 = await get_recent("alice", max_age_seconds=60)
    assert len(messages2) == 0
```

**Run:** `pytest tests/test_console_push_store.py::test_get_recent_consumes_messages -v`

**Expected:** FAIL - second call returns 1 instead of 0

### Step 1.2: Modify `get_recent()` to remove returned messages

In `src/copaw/app/console_push_store.py`, replace lines 75-93:

```python
async def get_recent(
    user_id: str | None = None,
    max_age_seconds: int = _MAX_AGE_SECONDS,
) -> List[Dict[str, Any]]:
    """Return recent messages (not consumed) for the user."""
    uid = user_id or "default"
    now = time.time()
    cutoff = now - max_age_seconds

    async with _lock:
        # Clean up expired messages for this user
        user_messages = _store.get(uid, [])
        valid = [m for m in user_messages if m["ts"] >= cutoff]
        expired = [m for m in user_messages if m["ts"] < cutoff]

        if expired:
            _store[uid] = valid

        return _strip_ts(valid)
```

With:

```python
async def get_recent(
    user_id: str | None = None,
    max_age_seconds: int = _MAX_AGE_SECONDS,
) -> List[Dict[str, Any]]:
    """Return and remove recent messages for the user."""
    uid = user_id or "default"
    now = time.time()
    cutoff = now - max_age_seconds

    async with _lock:
        user_messages = _store.get(uid, [])
        # Messages within time window to be returned and removed
        to_return = [m for m in user_messages if m["ts"] >= cutoff]
        # Messages outside time window to be dropped
        to_expire = [m for m in user_messages if m["ts"] < cutoff]

        # Keep only messages that are neither returned nor expired
        remaining = [
            m for m in user_messages
            if m["ts"] < cutoff  # Will be removed (expired)
            and m not in to_expire  # Actually we want: not in to_return and not expired
        ]
        # Simpler: remaining = [m for m in user_messages if m["ts"] < cutoff]
        # Actually: remaining should be empty - all messages either returned or expired
        remaining = []  # All messages are either consumed or expired

        if to_return or to_expire:
            _store[uid] = remaining

        return _strip_ts(to_return)
```

Wait, that's wrong. Let me rewrite more carefully:

```python
async def get_recent(
    user_id: str | None = None,
    max_age_seconds: int = _MAX_AGE_SECONDS,
) -> List[Dict[str, Any]]:
    """Return and remove recent messages for the user."""
    uid = user_id or "default"
    now = time.time()
    cutoff = now - max_age_seconds

    async with _lock:
        user_messages = _store.get(uid, [])
        # Separate: messages to return (within window) vs messages to drop (expired)
        to_return = [m for m in user_messages if m["ts"] >= cutoff]
        to_drop = [m for m in user_messages if m["ts"] < cutoff]

        # Remove all messages (either returned to caller or expired)
        if to_return or to_drop:
            _store[uid] = []

        return _strip_ts(to_return)
```

**Run:** `pytest tests/test_console_push_store.py::test_get_recent_consumes_messages -v`

**Expected:** PASS

### Step 1.3: Update existing test that assumes non-consuming behavior

In `tests/test_console_push_store.py`, replace the test `test_get_recent_non_consuming` with `test_get_recent_consumes_messages` from step 1.1.

**Run:** `pytest tests/test_console_push_store.py::test_get_recent_consumes_messages -v`

**Expected:** PASS

### Step 1.4: Commit

```bash
git add src/copaw/app/console_push_store.py tests/test_console_push_store.py
git commit -m "feat: get_recent now consumes messages on read

Messages returned by get_recent are immediately removed from storage.
Each message is consumed exactly once.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Add Test for get_recent and take Interaction

**Files:**
- Modify: `tests/test_console_push_store.py`

### Step 2.1: Write test for consume-once semantics across methods

Add new test:

```python
@pytest.mark.asyncio
async def test_message_consumed_once_across_methods():
    """测试消息在任何方法中只消费一次"""
    from copaw.app.console_push_store import append, get_recent, take

    await append("alice", "session_1", "Message 1")

    # Consume via get_recent
    messages1 = await get_recent("alice", max_age_seconds=60)
    assert len(messages1) == 1

    # Should not appear in take
    messages2 = await take("alice", "session_1")
    assert len(messages2) == 0

    # Add another message
    await append("alice", "session_1", "Message 2")

    # Consume via take
    messages3 = await take("alice", "session_1")
    assert len(messages3) == 1

    # Should not appear in get_recent
    messages4 = await get_recent("alice", max_age_seconds=60)
    assert len(messages4) == 0
```

**Run:** `pytest tests/test_console_push_store.py::test_message_consumed_once_across_methods -v`

**Expected:** PASS

### Step 2.2: Commit

```bash
git add tests/test_console_push_store.py
git commit -m "test: verify consume-once semantics across methods

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Update get_recent Docstring

**Files:**
- Modify: `src/copaw/app/console_push_store.py:75-79`

### Step 3.1: Update docstring to reflect new behavior

Change:
```python
"""Return recent messages (not consumed) for the user."""
```

To:
```python
"""Return and remove recent messages for the user.

Messages returned are immediately removed from storage and will not
be available for subsequent calls.
"""
```

### Step 3.2: Commit

```bash
git add src/copaw/app/console_push_store.py
git commit -m "docs: update get_recent docstring for consume-on-read

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Run Full Test Suite

### Step 4.1: Run all console_push_store tests

```bash
pytest tests/test_console_push_store.py -v
```

**Expected:** All 6 tests pass

### Step 4.2: Verify no regressions

```bash
pytest tests/ -v --tb=short
```

**Expected:** All tests in project pass (or at least no new failures)

---

## Summary

Changes made:
1. `get_recent()` now removes returned messages from storage
2. `take()` behavior unchanged (already removed messages)
3. `take_all()` behavior unchanged (already removed messages)
4. Tests updated to reflect consume-on-read semantics
5. Docstrings updated

The store now guarantees each message is consumed exactly once, regardless of which read method is used.
