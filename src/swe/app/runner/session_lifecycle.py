# -*- coding: utf-8 -*-
# flake8: noqa: E704
"""Session state and skill-snapshot lifecycle collaboration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol

from ...agents.react_agent import SWEAgent
from ...agents.skills_manager import resolve_effective_skill_dir
from ...constant import WORKING_DIR
from .query_contracts import _QueryRuntime

logger = logging.getLogger(__name__)


class SessionLifecycleOwner(Protocol):
    """Small runner surface required for session lifecycle operations."""

    session: Any
    workspace_dir: Path | None

    async def _save_cron_session_state(
        self,
        agent: SWEAgent,
        session_id: Any,
        user_id: str | None,
        hook_overlay: Any = None,
    ) -> None: ...

    async def _save_regular_session_state(
        self,
        agent: SWEAgent,
        session_id: Any,
        user_id: str | None,
        hook_overlay: Any = None,
    ) -> None: ...

    def _normalize_session_skill_snapshot(
        self,
        value: Any,
    ) -> dict[str, dict[str, Any]]: ...

    def _supports_session_skill_freshness_refresh(
        self,
        *,
        runtime: _QueryRuntime,
    ) -> bool: ...

    def _refresh_session_skill_snapshot_entries(
        self,
        snapshot: dict[str, dict[str, Any]],
        *,
        stored_snapshot: dict[str, dict[str, Any]],
        effective_skill_dirs: dict[str, Path],
    ) -> list[Any]: ...

    def _skill_freshness_notice_text(self, changes: list[Any]) -> str: ...

    def _can_restore_confirmed_session_skill_context(
        self,
        *,
        runtime: _QueryRuntime,
        detector: Any,
    ) -> bool: ...

    def _select_restorable_session_skill(
        self,
        snapshot: dict[str, dict[str, Any]],
        *,
        enabled_skills: list[str],
    ) -> str | None: ...


async def get_state_loaded(
    owner: SessionLifecycleOwner,
    agent: SWEAgent,
    session_id: str | None,
    session_state_loaded: bool,
    skip_history: bool | Any,
    user_id: str | None,
    *,
    coerce_session_id: Any,
    coerce_user_id: Any,
) -> bool:
    """Restore state once, retaining cron and schema-mismatch behavior."""
    storage_session_id = coerce_session_id(session_id)
    storage_user_id = coerce_user_id(user_id)
    if skip_history:
        logger.info(
            "Cron task: skipping session state load (session_id=%s)",
            session_id,
        )
        return True
    try:
        await owner.session.load_session_state(
            session_id=storage_session_id,
            user_id=storage_user_id,
            agent=agent,
        )
    except KeyError as exc:
        logger.warning(
            "load_session_state skipped (state schema mismatch): %s; "
            "will save fresh state on completion to recover file",
            exc,
        )
    return True


async def save_job_session_state(
    owner: SessionLifecycleOwner,
    agent: SWEAgent,
    session_id: Any,
    skip_history: bool | Any,
    user_id: str | None,
    hook_overlay: Any = None,
) -> None:
    """Persist cron or regular session state through runner-owned writers."""
    if skip_history:
        await owner._save_cron_session_state(
            agent,
            session_id,
            user_id,
            hook_overlay,
        )
        return
    await owner._save_regular_session_state(
        agent,
        session_id,
        user_id,
        hook_overlay,
    )


async def refresh_session_skill_freshness(
    owner: SessionLifecycleOwner,
    *,
    runtime: _QueryRuntime,
    refresh_result_type: type[Any],
) -> Any:
    """Refresh persisted skills and report context that must be injected."""
    if not owner._supports_session_skill_freshness_refresh(runtime=runtime):
        return refresh_result_type()
    stored_snapshot = owner._normalize_session_skill_snapshot(
        await owner.session.get_session_skill_snapshot(
            session_id=runtime.session_id,
            user_id=runtime.user_id,
            allow_not_exist=True,
        ),
    )
    if not stored_snapshot:
        return refresh_result_type(stored_snapshot={}, refreshed_snapshot={})
    workspace_dir = Path(owner.workspace_dir or WORKING_DIR)
    effective_skill_dirs = {
        skill_name: resolved
        for skill_name in runtime.agent.get_effective_skills()
        if (resolved := resolve_effective_skill_dir(workspace_dir, skill_name))
        is not None
    }
    next_snapshot = owner._normalize_session_skill_snapshot(stored_snapshot)
    changes = owner._refresh_session_skill_snapshot_entries(
        next_snapshot,
        stored_snapshot=stored_snapshot,
        effective_skill_dirs=effective_skill_dirs,
    )
    return refresh_result_type(
        notice_text=(
            owner._skill_freshness_notice_text(changes) if changes else None
        ),
        stored_snapshot=stored_snapshot,
        refreshed_snapshot=next_snapshot,
    )


async def build_skill_snapshot_to_persist(
    owner: SessionLifecycleOwner,
    *,
    runtime: _QueryRuntime,
    refresh_result: Any,
) -> dict[str, dict[str, Any]] | None:
    """Merge confirmed skill entries into a changed persisted snapshot."""
    if (
        runtime.skip_history
        or owner.session is None
        or not runtime.session_id
        or refresh_result.stored_snapshot is None
        or refresh_result.refreshed_snapshot is None
    ):
        return None
    next_snapshot = owner._normalize_session_skill_snapshot(
        refresh_result.refreshed_snapshot,
    )
    if runtime.pending_confirmed_skill_snapshots:
        next_snapshot.update(
            owner._normalize_session_skill_snapshot(
                runtime.pending_confirmed_skill_snapshots,
            ),
        )
    return (
        next_snapshot
        if next_snapshot != refresh_result.stored_snapshot
        else None
    )


async def restore_confirmed_session_skill_context(
    owner: SessionLifecycleOwner,
    *,
    runtime: _QueryRuntime,
) -> None:
    """Restore a one-shot continuation from the persisted skill snapshot."""
    detector = getattr(runtime, "session_skill_detector", None)
    if runtime.skip_history or owner.session is None:
        return
    if not owner._can_restore_confirmed_session_skill_context(
        runtime=runtime,
        detector=detector,
    ):
        return
    stored_snapshot = owner._normalize_session_skill_snapshot(
        await owner.session.get_session_skill_snapshot(
            session_id=runtime.session_id,
            user_id=runtime.user_id,
            allow_not_exist=True,
        ),
    )
    skills = (
        runtime.agent.get_runtime_skills()
        if hasattr(runtime.agent, "get_runtime_skills")
        else runtime.agent.get_effective_skills()
    )
    skill_name = owner._select_restorable_session_skill(
        stored_snapshot,
        enabled_skills=skills,
    )
    if skill_name:
        detector.restore_confirmed_skill(
            skill_name,
            allow_one_shot_continuation=True,
        )
