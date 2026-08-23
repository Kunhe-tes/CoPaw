# -*- coding: utf-8 -*-
"""Bounded Completion Judge protocol helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from agentscope.message import Msg

from .models import GoalSnapshot
from .runtime import CompletionReviewResult

_MALFORMED_OUTPUT_REASON = "completion review output is malformed"
_MISMATCHED_CRITERIA_REASON = "completion review output does not match criteria"


def parse_completion_review(
    content: str,
    criterion_ids: set[str],
) -> dict[str, CompletionReviewResult]:
    """Parse Judge JSON, rejecting every requested Criterion on any mismatch."""
    try:
        payload = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return _reject_all(criterion_ids, _MALFORMED_OUTPUT_REASON)
    reviews = payload.get("reviews") if isinstance(payload, dict) else None
    if not isinstance(reviews, list):
        return _reject_all(criterion_ids, _MALFORMED_OUTPUT_REASON)

    parsed: dict[str, CompletionReviewResult] = {}
    for item in reviews:
        if not isinstance(item, dict):
            return _reject_all(criterion_ids, _MALFORMED_OUTPUT_REASON)
        criterion_id = item.get("criterion_id")
        decision = item.get("decision")
        reason = item.get("reason")
        evidence_refs = item.get("evidence_refs")
        if (
            not isinstance(criterion_id, str)
            or decision not in {"accept", "reject"}
            or not isinstance(reason, str)
            or not isinstance(evidence_refs, list)
            or not all(isinstance(ref, str) for ref in evidence_refs)
        ):
            return _reject_all(criterion_ids, _MALFORMED_OUTPUT_REASON)
        if criterion_id not in criterion_ids or criterion_id in parsed:
            return _reject_all(criterion_ids, _MISMATCHED_CRITERIA_REASON)
        parsed[criterion_id] = (
            decision == "accept",
            _evidence_or_reason(evidence_refs, reason),
        )
    if set(parsed) != criterion_ids:
        return _reject_all(criterion_ids, _MISMATCHED_CRITERIA_REASON)
    return parsed


def build_completion_review_input(
    goal: GoalSnapshot,
    *,
    completion_proposal: str | None,
    evidence_refs: Iterable[str],
    tool_observations: Iterable[dict[str, Any]],
) -> Msg:
    """Build the bounded host-authored context for one Judge invocation."""
    payload = {
        "goal_id": goal.goal_id,
        "revision": goal.revision,
        "contract": goal.contract.model_dump(mode="json"),
        "criteria": [
            {
                "criterion_id": item.criterion_id,
                "criterion": item.criterion.model_dump(mode="json"),
                "accepted": item.verified,
            }
            for item in goal.criteria
        ],
        "completion_proposal": completion_proposal or "",
        "evidence_refs": list(evidence_refs),
        "tool_observations": list(tool_observations),
    }
    return Msg(
        name="system",
        role="user",
        content=(
            "Authoritative bounded Completion Review Package. "
            "Review only the supplied criteria and return the required JSON.\n"
            + json.dumps(payload, ensure_ascii=False)
        ),
    )


def _reject_all(
    criterion_ids: set[str],
    reason: str,
) -> dict[str, CompletionReviewResult]:
    return {criterion_id: (False, reason) for criterion_id in criterion_ids}


def _evidence_or_reason(evidence_refs: list[str], reason: str) -> str:
    evidence = "; ".join(ref.strip() for ref in evidence_refs if ref.strip())
    return evidence or reason.strip() or "completion review supplied no evidence"
