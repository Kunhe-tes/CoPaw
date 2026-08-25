# -*- coding: utf-8 -*-
"""Bounded Completion Judge protocol helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, cast

from agentscope.message import Msg

from .models import GoalSnapshot
from .runtime import CompletionReviewResult

_MALFORMED_OUTPUT_REASON = "completion review output is malformed"
_MISMATCHED_CRITERIA_REASON = (
    "completion review output does not match criteria"
)
_MAX_COMPLETION_PROPOSAL_LENGTH = 8000
_MAX_EVIDENCE_REFS = 8
_MAX_EVIDENCE_REF_LENGTH = 500
_MAX_TOOL_OBSERVATIONS = 20
_MAX_TOOL_FIELD_LENGTH = 4000


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
        if not _is_valid_review_item(
            criterion_id,
            decision,
            reason,
            evidence_refs,
        ):
            return _reject_all(criterion_ids, _MALFORMED_OUTPUT_REASON)
        review_reason = cast(str, reason)
        review_evidence_refs = cast(list[str], evidence_refs)
        if criterion_id not in criterion_ids or criterion_id in parsed:
            return _reject_all(criterion_ids, _MISMATCHED_CRITERIA_REASON)
        parsed[criterion_id] = (
            (
                True,
                _evidence_or_reason(review_evidence_refs, review_reason),
            )
            if decision == "accept"
            else (False, review_reason.strip())
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
        "completion_proposal": (completion_proposal or "")[
            :_MAX_COMPLETION_PROPOSAL_LENGTH
        ],
        "evidence_refs": _bounded_evidence_refs(evidence_refs),
        "tool_observations": _bounded_tool_observations(tool_observations),
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


def _is_valid_review_item(
    criterion_id: object,
    decision: object,
    reason: object,
    evidence_refs: object,
) -> bool:
    return (
        isinstance(criterion_id, str)
        and decision in {"accept", "reject"}
        and isinstance(reason, str)
        and bool(reason.strip())
        and isinstance(evidence_refs, list)
        and len(evidence_refs) <= _MAX_EVIDENCE_REFS
        and all(
            isinstance(ref, str) and len(ref) <= _MAX_EVIDENCE_REF_LENGTH
            for ref in evidence_refs
        )
    )


def _evidence_or_reason(evidence_refs: list[str], reason: str) -> str:
    evidence = "; ".join(ref.strip() for ref in evidence_refs if ref.strip())
    return (
        evidence or reason.strip() or "completion review supplied no evidence"
    )


def _bounded_evidence_refs(evidence_refs: Iterable[str]) -> list[str]:
    return [str(ref)[:_MAX_EVIDENCE_REF_LENGTH] for ref in evidence_refs][
        :_MAX_EVIDENCE_REFS
    ]


def _bounded_tool_observations(
    tool_observations: Iterable[dict[str, Any]],
) -> list[dict[str, str]]:
    observations: list[dict[str, str]] = []
    for observation in tool_observations:
        if not isinstance(observation, dict):
            continue
        observations.append(
            {
                "tool_call_id": str(observation.get("tool_call_id") or "")[
                    :_MAX_TOOL_FIELD_LENGTH
                ],
                "tool_name": str(observation.get("tool_name") or "")[
                    :_MAX_TOOL_FIELD_LENGTH
                ],
                "output": str(observation.get("output") or "")[
                    :_MAX_TOOL_FIELD_LENGTH
                ],
            },
        )
        if len(observations) == _MAX_TOOL_OBSERVATIONS:
            break
    return observations
