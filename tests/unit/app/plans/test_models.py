# -*- coding: utf-8 -*-
"""校验计划领域模型的必填字段和受控枚举。"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from swe.app.plans import (
    PlanClarificationCard,
    PlanReviewDecision,
    ProposedPlan,
    ProposedPlanCreate,
)


def _plan_payload() -> dict:
    return {
        "title": "Investigate failing tests",
        "summary": "Find the smallest failing backend scope.",
        "steps": ["Inspect logs", "Add regression test"],
        "risks": ["May need frontend follow-up"],
        "verification": ["Run targeted pytest"],
    }


def test_proposed_plan_create_forbids_frontend_plan_id() -> None:
    with pytest.raises(ValidationError):
        ProposedPlanCreate.model_validate(
            {
                **_plan_payload(),
                "plan_id": "plan-from-client",
            },
        )


def test_proposed_plan_generates_backend_plan_id() -> None:
    plan = ProposedPlan.new(
        chat_id="chat-1",
        session_id="session-1",
        turn_id="turn-1",
        created_by="main-agent",
        payload=ProposedPlanCreate.model_validate(_plan_payload()),
    )

    assert plan.plan_id.startswith("plan-")
    assert plan.chat_id == "chat-1"
    assert plan.status == "proposed"
    assert plan.title == "Investigate failing tests"


@pytest.mark.parametrize(
    "missing_field",
    [
        "title",
        "summary",
        "steps",
        "risks",
        "verification",
    ],
)
def test_proposed_plan_requires_review_fields(missing_field: str) -> None:
    payload = _plan_payload()
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        ProposedPlanCreate.model_validate(payload)


@pytest.mark.parametrize("removed_field", ["open_questions", "confidence"])
def test_proposed_plan_rejects_removed_review_fields(
    removed_field: str,
) -> None:
    payload = _plan_payload()
    payload[removed_field] = [] if removed_field == "open_questions" else 0.8

    with pytest.raises(ValidationError):
        ProposedPlanCreate.model_validate(payload)


def test_plan_clarification_card_supports_allowed_kinds() -> None:
    card = PlanClarificationCard(
        prompt="Choose scope",
        kind="single_choice",
        options=[
            {"id": "backend", "label": "Backend"},
            {"id": "frontend", "label": "Frontend"},
        ],
    )

    assert card.card_type == "plan_clarification"
    assert card.kind == "single_choice"


def test_plan_clarification_card_supports_form_fields() -> None:
    card = PlanClarificationCard(
        prompt="Collect planning context",
        kind="form",
        form_id="customer_plan_clarification",
        fields=[
            {
                "id": "industry",
                "label": "所在行业",
                "type": "select",
                "options": [
                    {"id": "retail", "label": "零售/电商"},
                    {"id": "saas", "label": "SaaS/软件服务"},
                ],
                "required": True,
            },
            {
                "id": "current_challenges",
                "label": "当前主要挑战",
                "type": "textarea",
                "placeholder": "请补充",
            },
        ],
    )

    assert card.kind == "form"
    assert card.form_id == "customer_plan_clarification"
    assert card.fields[0].type == "select"
    assert card.fields[1].placeholder == "请补充"


def test_plan_review_decision_rejects_unknown_decision() -> None:
    with pytest.raises(ValidationError):
        PlanReviewDecision(
            plan_id="plan-123",
            chat_id="chat-1",
            decision="approve",
        )
