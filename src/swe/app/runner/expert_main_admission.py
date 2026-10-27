# -*- coding: utf-8 -*-
"""Trusted ordinary-chat admission, performed before publishing a user turn."""

from __future__ import annotations

import asyncio

from fastapi import HTTPException

from swe.runtime_workers import run_runtime_state_work
from .expert_binding import (
    ExpertBindingConflict,
    binding_view,
    is_ordinary_chat,
    read_expert_binding,
    reconcile_binding,
    resolve_bound_expert,
)


async def _source_enabled(workspace, source_id: str) -> bool:
    from ..source_system_config.registry import is_expert_as_main_enabled
    from ..source_system_config.runtime import get_current_source_system_config

    service = getattr(workspace, "_source_system_config_service", None)
    config = get_current_source_system_config()
    if service is not None and source_id:
        config = await service.resolve_config(source_id, force_refresh=True)
    return is_expert_as_main_enabled(config)


def _prepare(workspace, chat, binding, definition):
    from pathlib import Path
    from swe.constant import QUERY_TIMEOUT_SECONDS
    from ...agents.tools.subagent_background import _parent_policy_from_config
    from ...providers import ProviderManager
    from .expert_main import (
        ExpertMainPreparationContext,
        prepare_expert_main_execution,
    )

    config = workspace.config
    parent = _parent_policy_from_config(config)
    model = ProviderManager.get_instance(
        workspace.tenant_id,
    ).get_active_model()
    return prepare_expert_main_execution(
        definition=definition,
        context=ExpertMainPreparationContext(
            workspace_dir=Path(workspace.workspace_dir),
            chat_id=chat.id,
            binding_revision=binding.revision,
            tenant_id=workspace.tenant_id,
        ),
        parent_agent_config=config,
        parent_policy=parent,
        workspace_policy=parent,
        chat_model_slot=model,
        main_budget=definition.budget.model_copy(
            update={"timeout_ms": int(QUERY_TIMEOUT_SECONDS * 1000)},
        ),
    )


async def _reject(workspace, chat, enabled, code, *, reason=None):
    view = await binding_view(workspace, chat, enabled=enabled)
    if reason is not None:
        view = view.model_copy(update={"reason": reason})
    raise HTTPException(
        status_code=409,
        detail={
            "code": code,
            "expert_binding": view.model_dump(),
        },
    )


def _message_text(payload):
    return "\n".join(
        (
            str(part.get("text", ""))
            if isinstance(part, dict)
            else str(getattr(part, "text", ""))
        )
        for part in payload.get("content_parts", [])
    ).strip()


async def admit_expert_main(workspace, chat, payload, msgid):
    """Register trusted execution before publishing a user turn."""
    meta = payload["meta"]
    meta.pop("_expert_main_execution_token", None)
    meta.pop("execution_identity", None)
    meta.pop("_expert_main_reset", None)
    source_id = meta.get("source_id", "")
    enabled = await _source_enabled(workspace, source_id)
    current = read_expert_binding(chat)
    expected = meta.get("expert_binding_revision")
    if not enabled:
        await _discard_pending(workspace, chat, source_id)
        chat = await _reconcile_disabled_binding(workspace, chat)
        if current.expert_id or (
            expected is not None
            and expected != read_expert_binding(chat).revision
        ):
            await _reject(workspace, chat, False, "expert_main_disabled")
        return None
    # Approval continuations resolve an original frozen execution, not the new
    # selector state. Only the runner can produce or recognize these tokens.
    text = _message_text(payload)
    token = await _resume_approval(workspace, chat, text, source_id, msgid)
    if token:
        meta["_expert_main_execution_token"] = token
        return token
    if await _release_for_mode_or_reset(workspace, chat, meta, text, current):
        return None
    if type(expected) is not int or expected != current.revision:
        # Legacy clients can start a default, never-bound Chat unchanged.
        if (
            current.revision
            or current.expert_id
            or meta.get("selected_expert_id")
            or expected is not None
        ):
            await _reject(workspace, chat, enabled, "expert_binding_changed")
    if current.expert_id is None:
        return None
    definition = await run_runtime_state_work(
        resolve_bound_expert,
        workspace,
        current.expert_id,
    )
    if definition is None:
        await _reject(workspace, chat, enabled, "expert_unavailable")
    try:
        prepared = await _prepare_owned(workspace, chat, current, definition)
    except (RuntimeError, ValueError, OSError):
        await _reject(workspace, chat, enabled, "expert_unavailable")
    registered = False
    try:
        if not await _source_enabled(workspace, source_id):
            await _discard_pending(workspace, chat, source_id)
            chat = await _reconcile_disabled_binding(workspace, chat)
            await _reject(workspace, chat, False, "expert_main_disabled")
        latest = await workspace.chat_manager.get_chat(chat.id)
        if (
            latest is None
            or read_expert_binding(latest) != current
            or not is_ordinary_chat(latest)
        ):
            if latest is None:
                raise HTTPException(status_code=404, detail="Chat not found")
            await _reject(workspace, latest, enabled, "expert_binding_changed")
        token = workspace.runner.register_expert_main_execution(
            prepared,
            chat_id=chat.id,
            user_id=chat.user_id,
            source_id=source_id,
            turn_id=msgid,
        )
        registered = True
        meta["_expert_main_execution_token"] = token
        return token
    finally:
        if not registered:
            await _cleanup_prepared(prepared)


async def _release_for_mode_or_reset(workspace, chat, meta, text, current):
    source_id = meta.get("source_id", "")
    enabled = True
    if (
        not is_ordinary_chat(chat)
        or meta.get("mode") == "plan"
        or meta.get("goal_mode_enabled")
        or meta.get("goal_id")
    ):
        await _discard_pending(workspace, chat, source_id)
        if current.expert_id:
            try:
                await workspace.chat_manager.compare_and_set_expert_binding(
                    chat.id,
                    current.revision,
                    None,
                )
            except ExpertBindingConflict:
                chat = await workspace.chat_manager.get_chat(chat.id)
                await _reject(
                    workspace,
                    chat,
                    enabled,
                    "expert_binding_changed",
                )
            except KeyError as exc:
                raise HTTPException(
                    status_code=404,
                    detail="Chat not found",
                ) from exc
            meta["expert_binding_notice"] = "专家绑定已解除，已切换会话模式"
        return True
    if text.split(maxsplit=1)[:1] in (["/new"], ["/clear"]):
        await _discard_pending(workspace, chat, source_id)
        if current.expert_id:
            try:
                await workspace.chat_manager.compare_and_set_expert_binding(
                    chat.id,
                    current.revision,
                    None,
                )
            except ExpertBindingConflict:
                latest = await workspace.chat_manager.get_chat(chat.id)
                if latest is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Chat not found",
                    )
                await _reject(
                    workspace,
                    latest,
                    enabled,
                    "expert_binding_changed",
                )
            except KeyError as exc:
                raise HTTPException(
                    status_code=404,
                    detail="Chat not found",
                ) from exc
            meta["expert_binding_notice"] = "专家绑定已解除，已回到默认 Agent"
            meta["_expert_main_reset"] = True
        return True
    return False


async def _await_owned_task(task):
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    return task.result(), cancelled


async def _prepare_owned(*args):
    task = asyncio.create_task(run_runtime_state_work(_prepare, *args))
    prepared, cancelled = await _await_owned_task(task)
    if cancelled:
        await _cleanup_prepared(prepared)
        raise asyncio.CancelledError
    return prepared


async def _cleanup_prepared(prepared):
    task = asyncio.create_task(run_runtime_state_work(prepared.cleanup))
    _, cancelled = await _await_owned_task(task)
    if cancelled:
        raise asyncio.CancelledError


async def _reconcile_disabled_binding(workspace, chat):
    try:
        latest = await reconcile_binding(workspace, chat, enabled=False)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Chat not found") from exc
    if latest is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return latest


async def _discard_pending(workspace, chat, source_id):
    discard = getattr(
        getattr(workspace, "runner", None),
        "discard_expert_main_pending",
        None,
    )
    if discard is not None:
        await discard(
            chat_id=chat.id,
            user_id=chat.user_id,
            source_id=source_id,
        )


async def _resume_approval(workspace, chat, text, source_id, msgid):
    from ..approvals import get_approval_service
    from .runner import (
        _approval_request_id,
        _denial_request_id,
        _is_approval,
        _is_denial,
        _select_pending_approval,
    )

    if not (_is_approval(text) or _is_denial(text)):
        return None
    approval_id = _approval_request_id(text) or _denial_request_id(text)
    pending = await _select_pending_approval(
        get_approval_service(),
        session_id=chat.session_id,
        request_id=approval_id,
    )
    if pending is not None:
        approval_id = pending.request_id
    resume = getattr(
        getattr(workspace, "runner", None),
        "resume_expert_main_execution",
        None,
    )
    token = (
        resume(
            chat_id=chat.id,
            user_id=chat.user_id,
            source_id=source_id,
            approval_id=approval_id,
            turn_id=msgid,
        )
        if approval_id and resume is not None
        else None
    )
    if token:
        return token
    identity = (getattr(pending, "extra", None) or {}).get(
        "execution_identity",
    )
    if isinstance(identity, dict) and identity.get("kind") == "expert_main":
        await _reject(
            workspace,
            chat,
            True,
            "expert_unavailable",
            reason="expert_execution_unavailable",
        )
    return None
