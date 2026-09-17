# -*- coding: utf-8 -*-
"""Completion Judge protocol tests."""

import pytest
from pydantic import ValidationError

from swe.app.goals.models import (
    CompletionCriterion,
    GoalContract,
    GoalCriterionStatus,
    GoalScope,
    GoalSnapshot,
)
from swe.app.goals.review import (
    build_completion_review_input,
    parse_completion_review,
)


def _goal() -> GoalSnapshot:
    criterion = CompletionCriterion(
        requirement="Tests pass",
        observable_assertion="pytest succeeds",
        verification_method="Run pytest",
        expected_outcome="The test command exits successfully",
    )
    return GoalSnapshot(
        scope=GoalScope(
            tenant_id="tenant",
            source_id="source",
            agent_profile_id="agent",
            chat_id="chat",
            effective_model="model",
        ),
        contract=GoalContract(
            objective="Finish the change",
            completion_criteria=[criterion],
            constraints={"must_preserve": [], "must_not_do": []},
            autonomy_boundary="No deployment",
        ),
        criteria=[
            GoalCriterionStatus(
                criterion_id="criterion-1",
                criterion=criterion,
            ),
        ],
        turn_budget=12,
    )


def test_parse_completion_review_returns_acceptance_and_evidence() -> None:
    parsed = parse_completion_review(
        (
            '{"reviews":[{"criterion_id":"criterion-1",'
            '"decision":"accept","reason":"Observed output",'
            '"evidence_refs":["tool-1"]}]}'
        ),
        {"criterion-1"},
    )

    assert parsed == {"criterion-1": (True, "tool-1")}


def test_parse_completion_review_rejects_a_blank_judge_reason() -> None:
    parsed = parse_completion_review(
        (
            '{"reviews":[{"criterion_id":"criterion-1",'
            '"decision":"accept","reason":"   ",'
            '"evidence_refs":[]}]}'
        ),
        {"criterion-1"},
    )

    assert parsed == {
        "criterion-1": (False, "completion review output is malformed"),
    }


def test_parse_completion_review_rejects_oversized_evidence() -> None:
    parsed = parse_completion_review(
        (
            '{"reviews":[{"criterion_id":"criterion-1",'
            '"decision":"accept","reason":"Observed output",'
            '"evidence_refs":["' + "e" * 501 + '"]}]}'
        ),
        {"criterion-1"},
    )

    assert parsed == {
        "criterion-1": (False, "completion review output is malformed"),
    }


def test_parse_completion_review_rejects_all_criteria_on_invalid_output() -> (
    None
):
    requested = {"criterion-1", "criterion-2"}

    parsed = parse_completion_review("not json", requested)

    assert parsed == {
        "criterion-1": (False, "completion review output is malformed"),
        "criterion-2": (False, "completion review output is malformed"),
    }


def test_parse_completion_review_rejects_all_on_duplicate_unknown_or_missing_ids() -> (
    None
):
    requested = {"criterion-1", "criterion-2"}
    payload = (
        '{"reviews":['
        '{"criterion_id":"criterion-1","decision":"accept",'
        '"reason":"done","evidence_refs":[]},'
        '{"criterion_id":"criterion-1","decision":"reject",'
        '"reason":"duplicate","evidence_refs":[]},'
        '{"criterion_id":"unknown","decision":"accept",'
        '"reason":"unknown","evidence_refs":[]}'
        "]}"
    )

    parsed = parse_completion_review(payload, requested)

    assert parsed == {
        "criterion-1": (
            False,
            "completion review output does not match criteria",
        ),
        "criterion-2": (
            False,
            "completion review output does not match criteria",
        ),
    }


def test_parse_completion_review_keeps_a_rejection_reason_with_evidence() -> (
    None
):
    parsed = parse_completion_review(
        (
            '{"reviews":[{"criterion_id":"criterion-1",'
            '"decision":"reject","reason":"Missing test output",'
            '"evidence_refs":["tool-1"]}]}'
        ),
        {"criterion-1"},
    )

    assert parsed == {"criterion-1": (False, "Missing test output")}


def test_completion_review_package_clips_untrusted_turn_payload() -> None:
    message = build_completion_review_input(
        _goal(),
        completion_proposal="p" * 10000,
        evidence_refs=["e" * 1000] * 20,
        tool_observations=[
            {"tool_name": "read_file", "output": "o" * 10000},
        ]
        * 30,
    )

    assert len(str(message.content)) < 100000
    assert "p" * 8001 not in str(message.content)


def test_goal_contract_limits_completion_criteria_in_judge_package() -> None:
    criterion = CompletionCriterion(
        requirement="Tests pass",
        observable_assertion="pytest succeeds",
        verification_method="Run pytest",
        expected_outcome="The test command exits successfully",
    )

    with pytest.raises(ValidationError, match="at most 16"):
        GoalContract(
            objective="Finish the change",
            completion_criteria=[criterion] * 17,
            constraints={"must_preserve": [], "must_not_do": []},
            autonomy_boundary="No deployment",
        )
