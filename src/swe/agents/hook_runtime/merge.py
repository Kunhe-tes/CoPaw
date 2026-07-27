# -*- coding: utf-8 -*-
"""合并多个 hook handler 的执行结果。"""

from __future__ import annotations

from typing import Any, Iterable

from .models import (
    AdditionalContext,
    EffectiveHookPlan,
    HookDecision,
    HookHandlerResult,
    HookPermissionDecision,
    MergedHookResult,
)

_DECISION_PRIORITY = {
    HookDecision.NONE: 0,
    HookDecision.ALLOW: 1,
    HookDecision.ASK: 2,
    HookDecision.DENY: 3,
    HookDecision.BLOCK: 3,
    HookDecision.STOP: 4,
}
_PERMISSION_DECISIONS = {"allow", "ask", "deny"}
_UpdatedInputs = list[tuple[str, dict[str, Any]]]


def _stronger(left: HookDecision, right: HookDecision) -> HookDecision:
    if _DECISION_PRIORITY[right] > _DECISION_PRIORITY[left]:
        return right
    return left


def _append_permission_decision(
    merged: MergedHookResult,
    result: HookHandlerResult,
    specific: dict[str, Any],
) -> None:
    permission_decision = specific.get("permissionDecision")
    if permission_decision not in _PERMISSION_DECISIONS:
        return

    merged.permission_decisions.append(
        HookPermissionDecision(
            handler_id=result.handler_id,
            decision=HookDecision(permission_decision),
            reason=str(
                specific.get("permissionDecisionReason")
                or result.reason
                or "",
            ),
        ),
    )


def _append_additional_context(
    merged: MergedHookResult,
    handler_id: str,
    specific: dict[str, Any],
) -> None:
    additional = specific.get("additionalContext")
    if not additional:
        return

    items = additional if isinstance(additional, list) else [additional]
    for item in items:
        merged.additional_context.append(
            AdditionalContext(
                handler_id=handler_id,
                context=str(item),
            ),
        )


def _collect_updated_input(
    updated_inputs: _UpdatedInputs,
    handler_id: str,
    specific: dict[str, Any],
) -> None:
    if specific.get("updatedInput") is None:
        return

    updated = specific["updatedInput"]
    if isinstance(updated, dict):
        updated_inputs.append((handler_id, updated))


def _merge_hook_specific_output(
    merged: MergedHookResult,
    result: HookHandlerResult,
    updated_inputs: _UpdatedInputs,
) -> None:
    specific = result.output.hook_specific_output or {}
    if not specific:
        return

    merged.hook_specific_outputs[result.handler_id] = dict(specific)
    _append_permission_decision(merged, result, specific)
    _append_additional_context(merged, result.handler_id, specific)
    _collect_updated_input(updated_inputs, result.handler_id, specific)

    session_title = specific.get("sessionTitle")
    if session_title and merged.session_title is None:
        merged.session_title = str(session_title)


def _merge_output_flags(
    merged: MergedHookResult,
    result: HookHandlerResult,
) -> None:
    if result.output.system_message:
        merged.system_messages.append(result.output.system_message)
    if result.output.suppress_output:
        merged.suppress_output = True


def _merge_decision(
    merged: MergedHookResult,
    result: HookHandlerResult,
) -> None:
    next_decision = _stronger(merged.decision, result.decision)
    if next_decision != merged.decision:
        merged.decision = next_decision
        merged.reason = result.reason
    elif not merged.reason and result.reason:
        merged.reason = result.reason


def _apply_updated_inputs(
    merged: MergedHookResult,
    updated_inputs: _UpdatedInputs,
) -> None:
    if merged.decision == HookDecision.STOP:
        merged.updated_input = None
        return

    if len(updated_inputs) == 1:
        merged.updated_input = updated_inputs[0][1]
        return

    if len(updated_inputs) > 1:
        merged.updated_input = None
        ids = ", ".join(handler_id for handler_id, _ in updated_inputs)
        merged.decision = HookDecision.BLOCK
        merged.reason = f"Multiple hooks returned updatedInput: {ids}"


def merge_hook_results(
    plan: EffectiveHookPlan,
    results: Iterable[HookHandlerResult],
) -> MergedHookResult:
    """按 handler 顺序合并 hook 结果并返回最终运行时决策。"""
    by_order = sorted(results, key=lambda item: item.order)
    merged = MergedHookResult()
    updated_inputs: _UpdatedInputs = []

    for result in by_order:
        _merge_hook_specific_output(merged, result, updated_inputs)
        _merge_output_flags(merged, result)
        _merge_decision(merged, result)

    _apply_updated_inputs(merged, updated_inputs)

    if not plan.handlers and merged.decision == HookDecision.NONE:
        merged.reason = ""
    return merged
