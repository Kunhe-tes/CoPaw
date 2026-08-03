# -*- coding: utf-8 -*-
"""Contract tests for the W+ SOP structured interaction models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from swe.app.wplus_sop.models import (
    EventKind,
    OwnershipTuple,
    Question,
    QuestionBatch,
    QuestionOption,
    QuestionType,
    ResultObjectList,
    SessionProjection,
    SessionState,
    Stage,
    StageProposalPayload,
    StageQueue,
    StageQueueConfirmedPayload,
    StructuredInteractionEnvelope,
    TrialExecutionCompletedPayload,
    assert_legal_transition,
)


def _stages() -> list[Stage]:
    return [
        Stage(stage_id="stage_discovery", name="需求确认"),
        Stage(stage_id="stage_delivery", name="交付校验"),
    ]


def test_stage_proposal_requires_two_to_four_stable_unique_stages() -> None:
    proposal = StageProposalPayload(stages=_stages())
    envelope = StructuredInteractionEnvelope(
        event_id="evt_1",
        sop_session_id="sop_1",
        chat_id="chat_1",
        revision=1,
        round=0,
        state_version=2,
        kind=EventKind.STAGE_PROPOSAL,
        payload=proposal,
    )

    assert envelope.session_id == "sop_1"
    assert [stage.stage_id for stage in proposal.stages] == [
        "stage_discovery",
        "stage_delivery",
    ]

    with pytest.raises(ValidationError):
        StageQueue(stages=[Stage(stage_id="only", name="只有一个")])

    with pytest.raises(ValidationError):
        StageQueue(
            stages=[
                Stage(stage_id="same", name="环节一"),
                Stage(stage_id="same", name="环节二"),
            ],
        )

    with pytest.raises(ValidationError):
        StageQueue(
            stages=[
                Stage(stage_id="one", name="重复"),
                Stage(stage_id="two", name="重复"),
            ],
        )


def test_confirmed_stage_queue_accepts_five_stages() -> None:
    stages = [
        Stage(stage_id=f"stage-{index}", name=f"环节 {index}")
        for index in range(1, 6)
    ]

    persisted = StageQueue(stages=stages)
    confirmed = StageQueueConfirmedPayload(stages=stages)

    assert len(persisted.stages) == 5
    assert len(confirmed.stages) == 5
    assert "maxItems" not in StageQueue.model_json_schema()["properties"][
        "stages"
    ]


def test_confirmed_stage_queue_preserves_a_large_manual_queue() -> None:
    confirmed = StageQueueConfirmedPayload(
        stages=[
            Stage(stage_id=f"stage-{index}", name=f"环节 {index}")
            for index in range(1, 51)
        ],
    )

    assert [stage.stage_id for stage in confirmed.stages] == [
        f"stage-{index}" for index in range(1, 51)
    ]


def test_agent_stage_proposal_rejects_five_candidates() -> None:
    stages = [
        Stage(stage_id=f"stage-{index}", name=f"候选环节 {index}")
        for index in range(1, 6)
    ]

    with pytest.raises(ValidationError):
        StageProposalPayload(stages=stages)

    stages_schema = StageProposalPayload.model_json_schema()["properties"][
        "stages"
    ]
    assert stages_schema["minItems"] == 2
    assert stages_schema["maxItems"] == 4


def test_question_option_serializes_custom_input_requirement() -> None:
    ordinary = QuestionOption(option_id="fixed", label="固定选项")
    custom = QuestionOption(
        option_id="other",
        label="其他",
        requires_custom_input=True,
    )

    assert ordinary.model_dump(mode="json")["requires_custom_input"] is False
    assert custom.model_dump(mode="json")["requires_custom_input"] is True
    description = QuestionOption.model_json_schema()["properties"][
        "requires_custom_input"
    ]["description"]
    assert "custom" in description.casefold()


def test_question_batch_is_atomic_and_uses_stable_option_ids() -> None:
    batch = QuestionBatch(
        batch_id="batch_1",
        stage_id="stage_discovery",
        questions=[
            Question(
                question_id="q_channel",
                prompt="主要入口是什么？",
                type=QuestionType.SINGLE_SELECT,
                options=[
                    QuestionOption(option_id="chat", label="Chat"),
                    QuestionOption(option_id="api", label="API"),
                ],
            ),
            Question(
                question_id="q_note",
                prompt="还有哪些约束？",
                type=QuestionType.FREE_TEXT,
            ),
        ],
    )

    assert len(batch.questions) == 2

    with pytest.raises(ValidationError):
        Question(
            question_id="q_bad",
            prompt="请选择",
            type=QuestionType.MULTI_SELECT,
            options=[],
        )

    with pytest.raises(ValidationError):
        Question(
            question_id="q_bad_free",
            prompt="请说明",
            type=QuestionType.FREE_TEXT,
            options=[QuestionOption(option_id="unexpected", label="不应存在")],
        )


def test_object_list_results_preserve_nested_objects() -> None:
    result = ResultObjectList(
        list_id="trial_rows",
        label="预跑结果",
        rows=[
            {
                "name": "父项",
                "children": [
                    {"name": "子项", "metrics": {"count": 3, "ok": True}},
                ],
            },
        ],
    )

    dumped = result.model_dump(mode="json")
    assert dumped["rows"][0]["children"][0]["metrics"] == {
        "count": 3,
        "ok": True,
    }


def test_trial_summary_rejects_known_raw_customer_payload_keys() -> None:
    with pytest.raises(ValidationError, match="raw_response"):
        TrialExecutionCompletedPayload(
            run_id="run_1",
            summary="完成",
            result_lists=[
                ResultObjectList(
                    list_id="rows",
                    label="结果",
                    rows=[{"raw_response": {"customer_id": "secret"}}],
                ),
            ],
        )


@pytest.mark.parametrize(
    "field",
    [
        "CustomerEmail",
        "phone-number",
        "customer_identifier",
        "customers",
        "acctNo",
        "orderId",
        "contact",
        "shippingAddress",
        "objectId",
        "accessToken",
    ],
)
def test_trial_summary_rejects_normalized_sensitive_aliases_recursively(
    field: str,
) -> None:
    with pytest.raises(ValidationError, match=field):
        ResultObjectList(
            list_id="rows",
            label="结果",
            rows=[{"groups": [{"details": [{field: "secret"}]}]}],
        )


def test_trial_summary_allows_ordinary_aggregate_fields() -> None:
    result = ResultObjectList(
        list_id="summary",
        label="汇总",
        rows=[
            {
                "customer_count": 18,
                "order_total": 42,
                "account_status_distribution": {
                    "active": 12,
                    "paused": 6,
                },
                "email_delivery_rate": 0.97,
            },
        ],
    )

    assert result.rows[0]["customer_count"] == 18
    assert result.rows[0]["order_total"] == 42


def test_trial_summary_rejects_sensitive_column_aliases() -> None:
    with pytest.raises(ValidationError, match="CustomerEmail"):
        ResultObjectList(
            list_id="summary",
            label="汇总",
            columns=[
                {
                    "field": "CustomerEmail",
                    "label": "邮箱",
                    "type": "string",
                },
            ],
            rows=[],
        )


@pytest.mark.parametrize(
    "value",
    [
        "person@example.com",
        "13812345678",
        "+1 202 555 0147",
        "(415) 555-2671",
        "010-12345678",
    ],
)
def test_trial_summary_rejects_sensitive_contact_values_recursively(
    value: str,
) -> None:
    with pytest.raises(ValidationError, match="sensitive contact value"):
        ResultObjectList(
            list_id="summary",
            label="汇总",
            rows=[{"groups": [{"display_value": value}]}],
        )


def test_trial_summary_does_not_treat_dates_or_plain_numbers_as_phone_data() -> None:
    result = ResultObjectList(
        list_id="summary",
        label="汇总",
        rows=[
            {
                "period": "2026-07-29",
                "period_note": "Report date 2026-07-29",
                "reference": "12345678",
                "amount": 12345678,
            },
        ],
    )

    assert result.rows[0]["period"] == "2026-07-29"


def test_paused_session_holds_slot_without_locking_ordinary_chat_input() -> None:
    ownership = OwnershipTuple(
        tenant_id="tenant_1",
        source_id="console",
        user_id="user_1",
        agent_id="agent_1",
        chat_id="chat_1",
        logical_chat_session_id="logical_1",
    )
    active = SessionProjection(
        sop_session_id="sop_active",
        ownership=ownership,
        skill_snapshot_id="sha256:miner-v1",
        state=SessionState.AWAITING_ANSWER,
        state_version=1,
        title="Active",
    )
    paused = SessionProjection(
        sop_session_id="sop_paused",
        ownership=ownership,
        skill_snapshot_id="sha256:miner-v1",
        state=SessionState.PAUSED,
        state_version=1,
        title="Paused",
        resume_state=SessionState.AWAITING_ANSWER,
    )

    assert active.holds_chat_slot is True
    assert active.locks_chat_input is True
    assert paused.holds_chat_slot is True
    assert paused.locks_chat_input is False


def test_event_kind_must_match_typed_payload() -> None:
    with pytest.raises(ValidationError, match="payload"):
        StructuredInteractionEnvelope(
            event_id="evt_1",
            sop_session_id="sop_1",
            chat_id="chat_1",
            revision=1,
            round=0,
            state_version=2,
            kind=EventKind.QUESTION_BATCH,
            payload=StageProposalPayload(stages=_stages()),
        )


def test_state_machine_accepts_main_path_and_rejects_skips() -> None:
    assert_legal_transition(
        SessionState.GENERATING_STAGE_PROPOSAL,
        SessionState.AWAITING_QUEUE_CONFIRMATION,
    )
    assert_legal_transition(
        SessionState.AWAITING_STAGE_CONFIRMATION,
        SessionState.FINALIZING_OUTPUTS,
    )
    assert_legal_transition(
        SessionState.AWAITING_STAGE_CONFIRMATION,
        SessionState.GENERATING_TRIAL,
    )

    with pytest.raises(ValueError, match="Illegal W\\+ SOP state transition"):
        assert_legal_transition(
            SessionState.GENERATING_STAGE_PROPOSAL,
            SessionState.AWAITING_ANSWER,
        )

    with pytest.raises(ValueError, match="Illegal W\\+ SOP state transition"):
        assert_legal_transition(
            SessionState.COMPLETED,
            SessionState.GENERATING_TRIAL,
        )


@pytest.mark.parametrize(
    "state",
    [
        SessionState.GENERATING_STAGE_PROPOSAL,
        SessionState.GENERATING_QUESTIONS,
        SessionState.GENERATING_TRIAL,
        SessionState.EXECUTING_TRIAL,
        SessionState.FINALIZING_OUTPUTS,
    ],
)
def test_generating_states_allow_progress_events_without_state_change(
    state: SessionState,
) -> None:
    assert_legal_transition(state, state)


def test_pending_exit_may_complete_at_the_natural_run_boundary() -> None:
    assert_legal_transition(
        SessionState.PENDING_EXIT,
        SessionState.COMPLETED,
    )
