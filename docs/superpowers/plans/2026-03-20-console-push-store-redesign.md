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
| `src/copaw/app/routers/console.py` | Console router with updated documentation |
| `tests/test_console_push_store.py` | Unit tests for all storage operations |
| `tests/test_console_user_isolation_integration.py` | Integration tests for consume-once behavior |

---

## Task 0.5: Update Console Router Documentation

**Files:**
- Modify: `src/copaw/app/routers/console.py:15-19`

### Step 0.5.1: Update docstring

Change:
```python
    """
    Return pending push messages. With user_id only: returns recent messages
    for that user (not consumed). With user_id and session_id: returns messages
    for that user's session (consumed).
    """
```

To:
```python
    """
    Return pending push messages. All read operations consume messages.
    With user_id only: returns and removes recent messages for that user.
    With user_id and session_id: returns and removes messages for that user's session.
    """
```

### Step 0.5.2: Commit

```bash
git add src/copaw/app/routers/console.py
git commit -m "docs: update console router for consume-on-read semantics

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

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
        # Messages outside time window to be dropped (expired)
        to_drop = [m for m in user_messages if m["ts"] < cutoff]

        # Remove all messages (either returned to caller or expired)
        if to_return or to_drop:
            _store[uid] = []

        return _strip_ts(to_return)
```

**Run:** `pytest tests/test_console_push_store.py::test_get_recent_consumes_messages -v`

**Expected:** PASS

### Step 1.3: Delete old non-consuming test

In `tests/test_console_push_store.py`, delete the test `test_get_recent_non_consuming` at lines 66-79. This test assumed non-consuming behavior which is no longer correct. The new test `test_get_recent_consumes_messages` from Step 1.1 replaces it.

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

## Task 2.5: Update Integration Test for Consume-Once Behavior

**Files:**
- Modify: `tests/test_console_user_isolation_integration.py:129-150`

### Step 2.5.1: Update test to verify consume-once semantics

Replace:
```python
@pytest.mark.asyncio
async def test_api_router_with_user_id_header():
    """测试 API 路由正确处理 x-user-id header"""
    from copaw.app.console_push_store import append, get_recent

    # Add messages for different users
    await append("alice", "session_1", "Alice's message")
    await append("bob", "session_1", "Bob's message")

    # Simulate API call with alice's user_id
    alice_messages = await get_recent("alice")
    assert len(alice_messages) == 1
    assert alice_messages[0]["text"] == "Alice's message"

    # Simulate API call with bob's user_id
    bob_messages = await get_recent("bob")
    assert len(bob_messages) == 1
    assert bob_messages[0]["text"] == "Bob's message"

    # Simulate API call with default user_id
    default_messages = await get_recent("default")
    assert len(default_messages) == 0  # No messages for default user
```

With:
```python
@pytest.mark.asyncio
async def test_api_router_with_user_id_header():
    """测试 API 路由正确处理 x-user-id header 及消费语义"""
    from copaw.app.console_push_store import append, get_recent

    # Add messages for different users
    await append("alice", "session_1", "Alice's message")
    await append("bob", "session_1", "Bob's message")

    # First call for alice - should return and consume message
    alice_messages = await get_recent("alice")
    assert len(alice_messages) == 1
    assert alice_messages[0]["text"] == "Alice's message"

    # Second call for alice - should return empty (message consumed)
    alice_messages_2 = await get_recent("alice")
    assert len(alice_messages_2) == 0

    # First call for bob - should return and consume message
    bob_messages = await get_recent("bob")
    assert len(bob_messages) == 1
    assert bob_messages[0]["text"] == "Bob's message"

    # Simulate API call with default user_id
    default_messages = await get_recent("default")
    assert len(default_messages) == 0  # No messages for default user
```

**Run:** `pytest tests/test_console_user_isolation_integration.py::test_api_router_with_user_id_header -v`

**Expected:** PASS

### Step 2.5.2: Commit

```bash
git add tests/test_console_user_isolation_integration.py
git commit -m "test: update integration test for consume-once behavior

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
