from __future__ import annotations

from swe.app.goals.router import CreateGoalRequest, EditGoalRequest


def _contract() -> dict:
    return {
        "objective": "Ship the Goal Runtime",
        "completion_criteria": [{
            "requirement": "Goal API exists",
            "observable_assertion": "route is registered",
            "verification_method": "inspect OpenAPI",
            "expected_outcome": "route is listed",
        }],
        "constraints": {"must_preserve": [], "must_not_do": []},
        "autonomy_boundary": "No deployment",
    }


def test_create_and_edit_requests_require_a_complete_contract() -> None:
    created = CreateGoalRequest(chat_id="chat-1", contract=_contract())
    edited = EditGoalRequest(contract=_contract())

    assert created.contract.objective == "Ship the Goal Runtime"
    assert edited.contract.completion_criteria[0].expected_outcome == "route is listed"
