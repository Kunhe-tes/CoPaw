"""In-process wake signals for the single-instance Goal Runtime phase."""

from __future__ import annotations

import asyncio

_events: dict[str, asyncio.Event] = {}


def notify_goal_wake(goal_id: str) -> None:
    """Wake the sticky request currently waiting for this Goal, if any."""
    _events.setdefault(goal_id, asyncio.Event()).set()


async def wait_for_goal_wake(goal_id: str) -> None:
    """Block without polling until a Goal control path emits an event."""
    event = _events.setdefault(goal_id, asyncio.Event())
    await event.wait()
    event.clear()
