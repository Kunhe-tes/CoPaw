# -*- coding: utf-8 -*-
"""Application-service tests for the complete W+ SOP lifecycle."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from swe.app.wplus_sop import service as service_module
from swe.app.wplus_sop.models import (
    CommandReceipt,
    OwnershipTuple,
    RunAttempt,
    RunStatus,
    SessionProjection,
    SessionState,
)
from swe.app.wplus_sop.service import (
    WPlusCommandError,
    WPlusRuntimeStartError,
    WPlusSopService,
)
from swe.app.wplus_sop.store import StaleStateVersionError, WPlusSopStore


class FakeChatManager:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(
            id="chat-1",
            session_id="logical-1",
            user_id="user-1",
            channel="console",
            meta={},
        )
        self.updates = 0

    async def get_chat(self, chat_id: str):
        return self.chat if chat_id == self.chat.id else None

    async def update_chat(self, chat):
        self.chat = chat
        self.updates += 1
        return chat


class FakeTaskTracker:
    def __init__(self) -> None:
        self.stops = 0
        self.status = "idle"

    async def request_stop(self, _run_key: str) -> bool:
        self.stops += 1
        return True

    async def get_status(self, _run_key: str) -> str:
        return self.status

    async def call_if_idle(self, _run_key: str, callback):
        if self.status != "idle":
            return False, None
        return True, callback()


def _ownership() -> OwnershipTuple:
    return OwnershipTuple(
        tenant_id="tenant-1",
        source_id="console",
        user_id="user-1",
        agent_id="agent-1",
        chat_id="chat-1",
        logical_chat_session_id="logical-1",
    )


def _service(tmp_path: Path) -> WPlusSopService:
    workspace = SimpleNamespace(
        workspace_dir=tmp_path,
        chat_manager=FakeChatManager(),
        task_tracker=FakeTaskTracker(),
    )
    return WPlusSopService(
        workspace=workspace,
        ownership=_ownership(),
        store=WPlusSopStore(tmp_path / "wplus-sop.json"),
    )


def _create_generation_run(
    service: WPlusSopService,
    *,
    session_id: str,
    created_at: datetime,
    state: SessionState = SessionState.GENERATING_STAGE_PROPOSAL,
    status: RunStatus = RunStatus.CLAIMED,
) -> None:
    service.store.create_session(
        SessionProjection(
            sop_session_id=session_id,
            ownership=_ownership(),
            skill_snapshot_id="sha256:miner",
            state=state,
            state_version=1,
            title="SOP",
            current_run_id=f"run-{session_id}",
        ),
        command_receipt=CommandReceipt(
            command_request_id=f"cmd-{session_id}",
            command="confirm_entry",
            sop_session_id=session_id,
            resulting_state_version=1,
            starts_run=True,
            run_id=f"run-{session_id}",
            attempt_id=f"attempt-{session_id}",
        ),
        run_attempt=RunAttempt(
            run_id=f"run-{session_id}",
            attempt_id=f"attempt-{session_id}",
            command_request_id=f"cmd-{session_id}",
            command="propose_stage_queue",
            status=status,
            created_at=created_at,
        ),
    )


async def _send(
    service: WPlusSopService,
    session_id: str,
    command: str,
    payload: dict | None = None,
    *,
    request_id: str,
):
    record = service.get_session(session_id)
    return await service.execute_command(
        sop_session_id=session_id,
        command=command,
        command_request_id=request_id,
        expected_state_version=record.projection.state_version,
        payload=payload or {},
    )


def _question_payload(stage_id: str, suffix: str) -> dict:
    return {
        "batch_id": f"batch-{suffix}",
        "stage_id": stage_id,
        "questions": [
            {
                "question_id": f"q-{suffix}",
                "prompt": "请确认范围",
                "type": "single_select",
                "options": [
                    {"option_id": "yes", "label": "确认"},
                    {"option_id": "no", "label": "调整"},
                ],
            },
        ],
    }


def _trial_plan_payload(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "input_snapshot_id": f"input-{run_id}",
        "steps": [
            {
                "step_id": f"step-{run_id}",
                "label": "调用业务能力",
                "capability_id": "crm.query",
                "capability_version": "1",
            },
        ],
    }


def _trial_result_payload(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "summary": "预跑完成",
        "result_lists": [
            {
                "list_id": f"result-{run_id}",
                "label": "预跑对象列表",
                "columns": [
                    {
                        "field": "name",
                        "label": "名称",
                        "type": "string",
                    },
                    {
                        "field": "details",
                        "label": "详情",
                        "type": "object",
                    },
                ],
                "rows": [
                    {
                        "name": "示例记录",
                        "details": {
                            "status": "ready",
                            "children": [{"label": "子项"}],
                        },
                    },
                ],
            },
        ],
    }


@pytest.mark.asyncio
async def test_confirm_persists_session_before_starting_agent_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    proposal = service.create_entry_proposal(
        original_text="请帮我梳理客户经营 SOP",
        mode="explicit",
    )
    observed: dict[str, str] = {}

    async def fake_start(**kwargs):
        record = service.store.get_session(kwargs["sop_session_id"])
        assert record is not None
        assert record.projection.state is SessionState.GENERATING_STAGE_PROPOSAL
        observed["session_id"] = kwargs["sop_session_id"]
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    mutation = await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry",
        skill_snapshot_id="sha256:miner",
    )

    assert mutation.record.projection.sop_session_id == observed["session_id"]
    assert service.get_active_session() is not None

    projected = await service.flush_chat_projection_outbox()
    assert projected == 1
    assert service.workspace.chat_manager.chat.meta[
        "wplus_sop_session"
    ]["state"] == "GeneratingStageProposal"
    assert service.store.pending_outbox() == []


@pytest.mark.asyncio
async def test_complete_two_stage_flow_preserves_nested_object_lists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    starts: list[str] = []

    async def fake_start(**kwargs):
        starts.append(kwargs["command"])
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    proposal = service.create_entry_proposal(
        original_text="创建完整 SOP",
        mode="explicit",
    )
    confirmed = await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry",
        skill_snapshot_id="sha256:miner",
    )
    session_id = confirmed.record.projection.sop_session_id

    service.append_agent_event(
        kind="stage_proposal",
        payload={
            "stages": [
                {"stage_id": "stage-1", "name": "确认范围"},
                {"stage_id": "stage-2", "name": "创建任务"},
            ],
        },
        event_key="stage-proposal",
    )
    queue = await _send(
        service,
        session_id,
        "confirm_stage_queue",
        {
            "stages": [
                {"stage_id": "stage-1", "title": "确认范围"},
                {"stage_id": "stage-2", "title": "创建任务"},
            ],
        },
        request_id="cmd-queue",
    )
    duplicate = await service.execute_command(
        sop_session_id=session_id,
        command="confirm_stage_queue",
        command_request_id="cmd-queue",
        expected_state_version=queue.record.projection.state_version - 1,
        payload={"stages": []},
    )
    assert duplicate.duplicate is True
    assert duplicate.record.projection.state_version == (
        queue.record.projection.state_version
    )

    for index, stage_id in enumerate(("stage-1", "stage-2"), start=1):
        service.append_agent_event(
            kind="question_batch",
            payload=_question_payload(stage_id, str(index)),
            event_key=f"questions-{index}",
        )
        await _send(
            service,
            session_id,
            "submit_answers",
            {
                "batch_id": f"batch-{index}",
                "answers": {f"q-{index}": "yes"},
            },
            request_id=f"cmd-answers-{index}",
        )
        service.append_agent_event(
            kind="trial_plan",
            payload=_trial_plan_payload(f"trial-{index}"),
            event_key=f"trial-plan-{index}",
        )
        service.append_agent_event(
            kind="trial_execution_completed",
            payload=_trial_result_payload(f"trial-{index}"),
            event_key=f"trial-result-{index}",
        )
        await _send(
            service,
            session_id,
            "accept_trial",
            request_id=f"cmd-accept-{index}",
        )
        await _send(
            service,
            session_id,
            "confirm_stage",
            request_id=f"cmd-stage-{index}",
        )

    service.append_agent_event(
        kind="sop_result",
        payload={
            "result": {
                "sop_spec": {"name": "客户经营 SOP", "version": 1},
                "readable_sop": "# 客户经营 SOP",
                "html": "<h1>客户经营 SOP</h1>",
            },
        },
        event_key="final-result",
    )
    completed = service.append_agent_event(
        kind="memory_candidates",
        payload={"candidates": []},
        event_key="no-memory-candidates",
    )

    assert completed.record.projection.state is SessionState.COMPLETED
    nested = completed.record.projection.trial_result_lists[0].rows[0]
    assert nested["details"]["children"][0]["label"] == "子项"
    assert starts == [
        "propose_stage_queue",
        "confirm_stage_queue",
        "submit_answers",
        "confirm_stage",
        "submit_answers",
        "confirm_stage",
    ]
    assert await service.flush_chat_projection_outbox() > 0
    assert service.workspace.chat_manager.chat.meta[
        "wplus_sop_session"
    ]["state"] == "Completed"
    assert service.store.pending_outbox() == []


@pytest.mark.asyncio
async def test_pending_exit_settles_at_next_structured_event_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)

    async def fake_start(**kwargs):
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    confirmed = await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry",
        skill_snapshot_id="sha256:miner",
    )
    session_id = confirmed.record.projection.sop_session_id

    pending = await _send(
        service,
        session_id,
        "save_and_exit",
        request_id="cmd-exit",
    )
    assert pending.record.projection.state is SessionState.PENDING_EXIT

    paused = service.append_agent_event(
        kind="stage_proposal",
        payload={
            "stages": [
                {"stage_id": "stage-1", "name": "确认范围"},
                {"stage_id": "stage-2", "name": "创建任务"},
            ],
        },
        event_key="safe-boundary",
    )
    assert paused.record.projection.state is SessionState.PAUSED
    assert paused.record.projection.resume_state is (
        SessionState.AWAITING_QUEUE_CONFIRMATION
    )
    with pytest.raises(WPlusCommandError):
        service.append_agent_event(
            kind="question_batch",
            payload=_question_payload("stage-1", "late"),
            event_key="late-event-from-paused-run",
        )

    resumed = await _send(
        service,
        session_id,
        "resume",
        request_id="cmd-resume",
    )
    assert resumed.record.projection.state is (
        SessionState.AWAITING_QUEUE_CONFIRMATION
    )


@pytest.mark.asyncio
async def test_pending_exit_rejects_duplicate_exit_and_supports_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)

    async def fake_start(**kwargs):
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    confirmed = await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-controls",
        skill_snapshot_id="sha256:miner",
    )
    session_id = confirmed.record.projection.sop_session_id
    await _send(
        service,
        session_id,
        "save_and_exit",
        request_id="cmd-exit-controls",
    )

    with pytest.raises(WPlusCommandError, match="pending exit"):
        await _send(
            service,
            session_id,
            "save_and_exit",
            request_id="cmd-exit-again",
        )
    assert (
        service.get_session(session_id).projection.resume_state
        is SessionState.GENERATING_STAGE_PROPOSAL
    )

    waiting = await _send(
        service,
        session_id,
        "continue_waiting",
        request_id="cmd-wait",
    )
    assert waiting.record.projection.state is SessionState.PENDING_EXIT
    assert (
        waiting.record.projection.resume_state
        is SessionState.GENERATING_STAGE_PROPOSAL
    )

    paused = await _send(
        service,
        session_id,
        "cancel_run_and_pause",
        request_id="cmd-cancel-pause",
    )
    assert paused.record.projection.state is SessionState.PAUSED
    assert (
        paused.record.projection.resume_state
        is SessionState.GENERATING_STAGE_PROPOSAL
    )
    assert service.workspace.task_tracker.stops == 1
    assert service.get_session(session_id).runs[0].status.value == "cancelled"


def test_same_text_creates_a_new_proposal_after_resolution(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    first = service.create_entry_proposal(
        original_text="创建相同 SOP",
        mode="explicit",
    )
    service.reject_entry(
        proposal_id=first.proposal_id,
        command_request_id="cmd-reject-first",
    )

    second = service.create_entry_proposal(
        original_text="创建相同 SOP",
        mode="explicit",
    )
    duplicate_pending = service.create_entry_proposal(
        original_text="创建相同 SOP",
        mode="explicit",
    )

    assert second.proposal_id != first.proposal_id
    assert duplicate_pending.proposal_id == second.proposal_id
    assert duplicate_pending.status.value == "pending"


@pytest.mark.asyncio
async def test_agent_event_retry_is_idempotent_after_state_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)

    async def fake_start(**kwargs):
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-event-retry",
        skill_snapshot_id="sha256:miner",
    )
    payload = {
        "stages": [
            {"stage_id": "stage-1", "name": "确认范围"},
            {"stage_id": "stage-2", "name": "生成结果"},
        ],
    }

    first = service.append_agent_event(
        kind="stage_proposal",
        payload=payload,
        event_key="stable-stage-proposal",
    )
    duplicate = service.append_agent_event(
        kind="stage_proposal",
        payload=payload,
        event_key="stable-stage-proposal",
    )

    assert first.duplicate is False
    assert duplicate.duplicate is True
    assert len(duplicate.record.events) == len(first.record.events)


@pytest.mark.asyncio
async def test_stage_proposal_rejects_non_pending_stage_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)

    async def fake_start(**kwargs):
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    confirmed = await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-invalid-stage-status",
        skill_snapshot_id="sha256:miner",
    )
    before = confirmed.record.projection.state_version

    with pytest.raises(
        WPlusCommandError,
        match="stages must start as pending",
    ):
        service.append_agent_event(
            kind="stage_proposal",
            payload={
                "stages": [
                    {
                        "stage_id": "stage-1",
                        "name": "确认范围",
                        "status": "clarifying",
                    },
                    {
                        "stage_id": "stage-2",
                        "name": "生成结果",
                        "status": "pending",
                    },
                ],
            },
            event_key="invalid-stage-status",
        )

    record = service.get_session(
        confirmed.record.projection.sop_session_id,
    )
    assert record.projection.state_version == before
    assert record.projection.state is SessionState.GENERATING_STAGE_PROPOSAL


@pytest.mark.asyncio
async def test_concurrent_outbox_flush_keeps_the_complete_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)

    async def fake_start(**kwargs):
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-outbox",
        skill_snapshot_id="sha256:miner",
    )
    service.append_agent_event(
        kind="stage_proposal",
        payload={
            "stages": [
                {"stage_id": "stage-1", "name": "确认范围"},
                {"stage_id": "stage-2", "name": "生成结果"},
            ],
        },
        event_key="outbox-stage",
    )
    peer = WPlusSopService(
        workspace=service.workspace,
        ownership=_ownership(),
        store=WPlusSopStore(tmp_path / "wplus-sop.json"),
    )

    await asyncio.gather(
        service.flush_chat_projection_outbox(),
        peer.flush_chat_projection_outbox(),
    )

    audit = service.workspace.chat_manager.chat.meta["wplus_sop_audit"]
    assert len(audit) == 2
    assert len({item["projection_event_id"] for item in audit}) == 2
    assert service.store.pending_outbox() == []


@pytest.mark.asyncio
async def test_outbox_get_chat_failure_remains_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)

    async def fake_start(**kwargs):
        return SimpleNamespace(run_id=kwargs["run_id"])

    async def fail_get_chat(_chat_id: str):
        raise RuntimeError("temporary Chat storage failure")

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-outbox-failure",
        skill_snapshot_id="sha256:miner",
    )
    monkeypatch.setattr(
        service.workspace.chat_manager,
        "get_chat",
        fail_get_chat,
    )

    assert await service.flush_chat_projection_outbox() == 0
    assert len(service.store.pending_outbox()) == 1


@pytest.mark.asyncio
async def test_memory_candidates_require_final_sop_result(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    service.store.create_session(
        SessionProjection(
            sop_session_id="sop-finalizing",
            ownership=_ownership(),
            skill_snapshot_id="sha256:miner",
            state=SessionState.FINALIZING_OUTPUTS,
            state_version=1,
            title="SOP",
        ),
        command_receipt=CommandReceipt(
            command_request_id="cmd-finalizing",
            command="confirm_entry",
            sop_session_id="sop-finalizing",
            resulting_state_version=1,
        ),
    )

    with pytest.raises(WPlusCommandError):
        service.append_agent_event(
            kind="memory_candidates",
            payload={"candidates": []},
            event_key="misordered-memory",
        )

    assert (
        service.get_session("sop-finalizing").projection.state
        is SessionState.FINALIZING_OUTPUTS
    )


@pytest.mark.asyncio
async def test_revise_answer_invalidates_downstream_and_starts_new_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    starts: list[dict] = []

    async def fake_start(**kwargs):
        starts.append(kwargs)
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    confirmed = await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-revision",
        skill_snapshot_id="sha256:miner",
    )
    session_id = confirmed.record.projection.sop_session_id
    service.append_agent_event(
        kind="stage_proposal",
        payload={
            "stages": [
                {"stage_id": "stage-1", "name": "确认范围"},
                {"stage_id": "stage-2", "name": "生成结果"},
            ],
        },
        event_key="revision-stages",
    )
    await _send(
        service,
        session_id,
        "confirm_stage_queue",
        {
            "stages": [
                {"stage_id": "stage-1", "title": "确认范围"},
                {"stage_id": "stage-2", "title": "生成结果"},
            ],
        },
        request_id="cmd-revision-queue",
    )
    service.append_agent_event(
        kind="question_batch",
        payload=_question_payload("stage-1", "revision"),
        event_key="revision-questions",
    )
    await _send(
        service,
        session_id,
        "submit_answers",
        {
            "answers": {"q-revision": "yes"},
        },
        request_id="cmd-original-answer",
    )
    service.append_agent_event(
        kind="trial_plan",
        payload=_trial_plan_payload("trial-revision"),
        event_key="revision-plan",
    )
    service.append_agent_event(
        kind="trial_execution_completed",
        payload=_trial_result_payload("trial-revision"),
        event_key="revision-result",
    )

    revised = await _send(
        service,
        session_id,
        "revise_answer",
        {
            "revised_round": 1,
            "answers": {"q-revision": "no"},
            "reason": "范围发生变化",
        },
        request_id="cmd-revise-answer",
    )

    projection = revised.record.projection
    assert projection.state is SessionState.GENERATING_TRIAL
    assert projection.revision == 2
    assert projection.round == 1
    assert projection.answers[0].answers[0].selected_option_ids == ["no"]
    assert projection.trial_result_lists == []
    assert projection.invalidated_history[0]["revised_round"] == 1
    assert starts[-1]["command"] == "revise_answer"


@pytest.mark.asyncio
async def test_outbox_projects_every_audit_item_before_ack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)

    async def fake_start(**kwargs):
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-audit",
        skill_snapshot_id="sha256:miner",
    )
    service.append_agent_event(
        kind="stage_proposal",
        payload={
            "stages": [
                {"stage_id": "stage-1", "name": "确认范围"},
                {"stage_id": "stage-2", "name": "生成结果"},
            ],
        },
        event_key="audit-stage-proposal",
    )

    assert len(service.store.pending_outbox()) == 2
    assert await service.flush_chat_projection_outbox() == 2
    audit = service.workspace.chat_manager.chat.meta["wplus_sop_audit"]
    assert [item["kind"] for item in audit] == [
        "session_state_changed",
        "stage_proposal",
    ]
    assert service.store.pending_outbox() == []


@pytest.mark.asyncio
async def test_agent_completion_without_boundary_becomes_recoverable_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    captured: dict[str, object] = {}

    async def fake_start(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    confirmed = await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-no-event",
        skill_snapshot_id="sha256:miner",
    )

    await captured["on_complete"]()

    record = service.get_session(
        confirmed.record.projection.sop_session_id,
    )
    assert record.projection.state is SessionState.RECOVERABLE_FAILURE
    assert (
        record.projection.resume_state
        is SessionState.GENERATING_STAGE_PROPOSAL
    )
    assert record.projection.last_error.failed_run_id == captured["run_id"]
    assert record.runs[0].status.value == "failed"


@pytest.mark.asyncio
async def test_runtime_start_failure_can_retry_from_server_owned_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )

    async def fail_start(**_kwargs):
        raise RuntimeError("runtime unavailable")

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fail_start)
    with pytest.raises(WPlusRuntimeStartError, match="runtime unavailable"):
        await service.confirm_entry(
            proposal_id=proposal.proposal_id,
            command_request_id="cmd-entry-start-failure",
            skill_snapshot_id="sha256:miner",
        )

    failed = service.get_active_session()
    assert failed is not None
    assert failed.projection.state is SessionState.RECOVERABLE_FAILURE
    assert (
        failed.projection.resume_state
        is SessionState.GENERATING_STAGE_PROPOSAL
    )
    assert failed.runs[0].status is RunStatus.FAILED

    captured: dict[str, object] = {}

    async def succeed_start(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(
        service_module,
        "start_wplus_chat_turn",
        succeed_start,
    )
    retried = await _send(
        service,
        failed.projection.sop_session_id,
        "retry_current_turn",
        {
            "target_state": "FinalizingOutputs",
            "retry_of_run_id": "forged",
        },
        request_id="cmd-retry-start-failure",
    )

    assert (
        retried.record.projection.state
        is SessionState.GENERATING_STAGE_PROPOSAL
    )
    assert captured["payload"] == {
        "target_state": "GeneratingStageProposal",
        "retry_of_run_id": failed.runs[0].run_id,
    }


@pytest.mark.asyncio
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
@pytest.mark.parametrize(
    "status",
    [RunStatus.CLAIMED, RunStatus.RUNNING],
)
async def test_idle_orphaned_generation_run_becomes_retryable_once(
    tmp_path: Path,
    state: SessionState,
    status: RunStatus,
) -> None:
    service = _service(tmp_path)
    _create_generation_run(
        service,
        session_id="sop-orphan",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        state=state,
        status=status,
    )

    recovered = await service.recover_orphaned_generation_run("sop-orphan")
    duplicate = await service.recover_orphaned_generation_run("sop-orphan")

    assert recovered is not None
    assert duplicate is None
    record = service.get_session("sop-orphan")
    assert record.projection.state is SessionState.RECOVERABLE_FAILURE
    assert record.projection.resume_state is state
    assert record.projection.last_error.error_code == "orphaned_agent_run"
    assert record.projection.last_error.failed_run_id == "run-sop-orphan"
    assert record.runs[0].status is RunStatus.FAILED
    assert [event.kind.value for event in record.events] == [
        "session_state_changed",
        "recoverable_failure",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tracker_status", "is_fresh"),
    [
        ("running", False),
        ("idle", True),
    ],
)
async def test_active_or_fresh_generation_run_is_not_recovered(
    tmp_path: Path,
    tracker_status: str,
    is_fresh: bool,
) -> None:
    service = _service(tmp_path)
    service.workspace.task_tracker.status = tracker_status
    now = datetime.now(timezone.utc)
    _create_generation_run(
        service,
        session_id="sop-active-or-fresh",
        created_at=(
            now
            if is_fresh
            else now - timedelta(minutes=1)
        ),
    )

    recovered = await service.recover_orphaned_generation_run(
        "sop-active-or-fresh",
    )

    assert recovered is None
    record = service.get_session("sop-active-or-fresh")
    assert (
        record.projection.state
        is SessionState.GENERATING_STAGE_PROPOSAL
    )
    assert record.runs[0].status is RunStatus.CLAIMED


@pytest.mark.asyncio
async def test_pending_exit_orphan_pauses_into_retryable_failure(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    _create_generation_run(
        service,
        session_id="sop-pending-exit-orphan",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    pending = await _send(
        service,
        "sop-pending-exit-orphan",
        "save_and_exit",
        request_id="cmd-save-orphan",
    )
    assert pending.record.projection.state is SessionState.PENDING_EXIT

    recovered = await service.recover_orphaned_generation_run(
        "sop-pending-exit-orphan",
    )

    assert recovered is not None
    record = recovered.record
    assert record.projection.state is SessionState.PAUSED
    assert (
        record.projection.resume_state
        is SessionState.RECOVERABLE_FAILURE
    )
    assert record.projection.last_error.error_code == "orphaned_agent_run"
    assert record.projection.pending_exit_action is None
    assert record.runs[0].status is RunStatus.FAILED


@pytest.mark.asyncio
async def test_retry_uses_only_server_owned_target_and_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    captured: dict[str, object] = {}
    _create_generation_run(
        service,
        session_id="sop-server-owned-retry",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    await service.recover_orphaned_generation_run("sop-server-owned-retry")

    async def fake_start(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    retried = await _send(
        service,
        "sop-server-owned-retry",
        "retry_current_turn",
        {
            "target_state": "FinalizingOutputs",
            "retry_of_run_id": "run-forged",
        },
        request_id="cmd-server-owned-retry",
    )

    assert (
        retried.record.projection.state
        is SessionState.GENERATING_STAGE_PROPOSAL
    )
    assert captured["payload"] == {
        "target_state": "GeneratingStageProposal",
        "retry_of_run_id": "run-sop-server-owned-retry",
    }
    assert (
        service.get_session("sop-server-owned-retry")
        .runs[-1]
        .retry_of_run_id
        == "run-sop-server-owned-retry"
    )


@pytest.mark.asyncio
async def test_orphan_recovery_fails_closed_on_stale_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    _create_generation_run(
        service,
        session_id="sop-stale",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    def stale_commit(*_args, **_kwargs):
        raise StaleStateVersionError("settled concurrently")

    monkeypatch.setattr(service.store, "commit_event", stale_commit)

    assert (
        await service.recover_orphaned_generation_run("sop-stale")
        is None
    )
    record = service.get_session("sop-stale")
    assert (
        record.projection.state
        is SessionState.GENERATING_STAGE_PROPOSAL
    )
    assert record.runs[0].status is RunStatus.CLAIMED
