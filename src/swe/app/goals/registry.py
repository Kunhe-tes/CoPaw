# -*- coding: utf-8 -*-
"""Process-local access point for the application-owned Goal service."""

from __future__ import annotations

from typing import Any

from .service import GoalService
from .store import MySqlGoalStore

_service: GoalService | None = None


async def initialize_goal_service(db: Any | None) -> GoalService | None:
    """Install the MySQL-backed service after application DB startup."""
    global _service
    store = MySqlGoalStore(db)
    if not store.is_available:
        _service = None
        return None
    _service = GoalService(store)
    return _service


def get_goal_service() -> GoalService | None:
    """Return the process service used by API and Runner integration."""
    return _service
