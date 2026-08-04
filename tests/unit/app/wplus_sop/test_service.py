# -*- coding: utf-8 -*-
"""Application-service tests for the complete W+ SOP lifecycle."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from swe.app.wplus_sop import service as service_module
from swe.app.wplus_sop.models import (
    CommandReceipt,
    FinalSopResult,
    OwnershipTuple,
    Question,
    QuestionBatch,
    QuestionOption,
    QuestionType,
    RecoverableFailurePayload,
    RunAttempt,
    RunStatus,
    SessionProjection,
    SessionState,
    Stage,
)
from swe.app.wplus_sop.runtime import WPlusChatRunBusyError
from swe.app.wplus_sop.service import (
    WPlusCommandError,
    WPlusOwningChatFinalizingError,
    WPlusOwnershipError,
    WPlusRuntimeStartError,
    WPlusSopService,
    serialize_session,
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
        self.status_reads = 0
        self.idle_after_reads: int | None = None

    async def request_stop(self, _run_key: str) -> bool:
        self.stops += 1
        return True

    async def get_status(self, _run_key: str) -> str:
        self.status_reads += 1
        if (
            self.idle_after_reads is not None
            and self.status_reads >= self.idle_after_reads
        ):
            self.status = "idle"
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


def _create_question_generation_run(
    service: WPlusSopService,
    *,
    session_id: str,
) -> None:
    service.store.create_session(
        SessionProjection(
            sop_session_id=session_id,
            ownership=_ownership(),
            skill_snapshot_id="sha256:miner",
            state=SessionState.GENERATING_QUESTIONS,
            state_version=1,
            title="SOP",
            stages=[
                Stage(
                    stage_id="stage-1",
                    name="确认范围",
                    status="clarifying",
                ),
                Stage(stage_id="stage-2", name="生成结果"),
            ],
            current_stage_id="stage-1",
            current_run_id=f"run-{session_id}",
        ),
        command_receipt=CommandReceipt(
            command_request_id=f"cmd-{session_id}",
            command="confirm_stage_queue",
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
            command="confirm_stage_queue",
            status=RunStatus.CLAIMED,
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


def _create_structured_answer_session(service: WPlusSopService) -> str:
    session_id = "sop-structured-answers"
    stage = Stage(stage_id="stage-1", name="确认范围")
    question_batch = QuestionBatch(
        batch_id="batch-structured",
        stage_id=stage.stage_id,
        questions=[
            Question(
                question_id="q-single",
                prompt="选择主要入口",
                type=QuestionType.SINGLE_SELECT,
                options=[
                    QuestionOption(option_id="fixed", label="固定入口"),
                    QuestionOption(
                        option_id="other",
                        label="其他入口",
                        requires_custom_input=True,
                    ),
                ],
            ),
            Question(
                question_id="q-multi",
                prompt="选择辅助入口",
                type=QuestionType.MULTI_SELECT,
                options=[
                    QuestionOption(option_id="chat", label="Chat"),
                    QuestionOption(option_id="api", label="API"),
                ],
            ),
            Question(
                question_id="q-note",
                prompt="补充约束",
                type=QuestionType.FREE_TEXT,
            ),
        ],
    )
    service.store.create_session(
        SessionProjection(
            sop_session_id=session_id,
            ownership=_ownership(),
            skill_snapshot_id="sha256:miner",
            state=SessionState.AWAITING_ANSWER,
            state_version=1,
            title="SOP",
            stages=[stage],
            current_stage_id=stage.stage_id,
            current_question_batch=question_batch,
        ),
        command_receipt=CommandReceipt(
            command_request_id="cmd-create-structured-answers",
            command="test_setup",
            sop_session_id=session_id,
            resulting_state_version=1,
        ),
    )
    return session_id


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
async def test_completed_trial_snapshot_restores_results_and_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    session_id = "sop-trial-evidence"
    _create_question_generation_run(service, session_id=session_id)

    async def fake_start(**kwargs):
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    service.append_agent_event(
        kind="question_batch",
        payload=_question_payload("stage-1", "trial-evidence"),
        event_key="trial-evidence-questions",
    )
    await _send(
        service,
        session_id,
        "submit_answers",
        {"answers": {"q-trial-evidence": "yes"}},
        request_id="cmd-trial-evidence-answers",
    )
    run_id = service.get_session(session_id).projection.current_run_id
    assert run_id is not None
    service.append_agent_event(
        kind="trial_plan",
        payload=_trial_plan_payload(run_id),
        event_key="trial-evidence-plan",
    )
    service.append_agent_event(
        kind="trial_execution_started",
        payload={
            "run_id": run_id,
            "attempt_id": "attempt-trial-evidence",
            "started_at": "2026-08-03T08:00:00Z",
        },
        event_key="trial-evidence-started",
    )
    service.append_agent_event(
        kind="trial_execution_progress",
        payload={
            "run_id": run_id,
            "step_id": f"step-{run_id}",
            "status": "completed",
            "summary": "查询完成，共 1 条脱敏记录",
            "elapsed_ms": 1200,
        },
        event_key="trial-evidence-progress",
    )
    completed_payload = _trial_result_payload(run_id)
    completed_payload.update(
        {
            "warnings": ["结果仅包含脱敏字段"],
            "confirmed_facts": ["统计范围为未来 30 天"],
            "unknowns": ["是否排除已冻结账户"],
            "completed_at": "2026-08-03T08:00:02Z",
        },
    )
    service.append_agent_event(
        kind="trial_execution_completed",
        payload=completed_payload,
        event_key="trial-evidence-completed",
    )

    reloaded = WPlusSopStore(tmp_path / "wplus-sop.json").get_session(session_id)
    assert reloaded is not None
    snapshot = serialize_session(reloaded)

    assert snapshot["trial"]["summary"] == "预跑完成"
    assert snapshot["trial"]["warnings"] == ["结果仅包含脱敏字段"]
    assert snapshot["trial"]["started_at"] == "2026-08-03T08:00:00Z"
    assert snapshot["trial"]["completed_at"] == "2026-08-03T08:00:02Z"
    assert snapshot["trial"]["steps"] == [
        {
            "step_id": f"step-{run_id}",
            "title": "调用业务能力",
            "capability": "crm.query",
            "status": "completed",
            "summary": "查询完成，共 1 条脱敏记录",
            "elapsed_ms": 1200,
        },
    ]
    assert snapshot["trial"]["result_rows"][0]["name"] == "示例记录"
    assert snapshot["facts"] == ["统计范围为未来 30 天"]
    assert snapshot["unknowns"] == ["是否排除已冻结账户"]
    assert snapshot["capabilities"] == [
        {
            "capability_id": "crm.query",
            "name": "crm.query",
            "verification_status": "verified",
            "output_contract_status": "verified",
        },
    ]

    await _send(
        service,
        session_id,
        "submit_trial_feedback",
        {"feedback": "请排除冻结账户"},
        request_id="cmd-trial-evidence-rerun",
    )
    rerun_snapshot = serialize_session(service.get_session(session_id))
    assert rerun_snapshot["trial"]["status"] == "planning"
    assert rerun_snapshot["trial"]["result_rows"] == []
    assert rerun_snapshot["trial"]["summary"] is None
    assert rerun_snapshot["capabilities"] == []


@pytest.mark.asyncio
async def test_confirm_waits_for_owning_chat_idle_before_store_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    before_proposal = service.store.get_entry_proposal(proposal.proposal_id)
    service.workspace.task_tracker.status = "running"
    monkeypatch.setattr(
        service_module,
        "_CHAT_IDLE_WAIT_TIMEOUT_SECONDS",
        0.001,
    )
    monkeypatch.setattr(service_module, "_CHAT_IDLE_POLL_SECONDS", 0.001)

    async def unexpected_start(**_kwargs):
        pytest.fail("Agent run must not start while the owning Chat is busy")

    monkeypatch.setattr(
        service_module,
        "start_wplus_chat_turn",
        unexpected_start,
    )

    with pytest.raises(WPlusOwningChatFinalizingError):
        await service.confirm_entry(
            proposal_id=proposal.proposal_id,
            command_request_id="cmd-entry-chat-busy",
            skill_snapshot_id="sha256:miner",
        )

    assert service.store.get_entry_proposal(proposal.proposal_id) == (
        before_proposal
    )
    assert service.get_active_session() is None


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
async def test_confirm_allows_source_id_to_differ_from_chat_channel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    service.ownership = _ownership().model_copy(
        update={"source_id": "external-source-1"},
    )
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    captured: dict[str, object] = {}

    async def fake_start(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    mutation = await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-different-source",
        skill_snapshot_id="sha256:miner",
    )

    assert (
        mutation.record.projection.ownership.source_id == "external-source-1"
    )
    assert captured["source_id"] == "external-source-1"
    assert captured["chat"] is service.workspace.chat_manager.chat


@pytest.mark.asyncio
async def test_confirm_reuses_verified_chat_for_entry_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    chat = service.workspace.chat_manager.chat
    lookups: list[str] = []

    async def one_shot_get_chat(chat_id: str):
        lookups.append(chat_id)
        return chat if len(lookups) == 1 else None

    async def fake_start(**kwargs):
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(
        service.workspace.chat_manager,
        "get_chat",
        one_shot_get_chat,
    )
    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)

    mutation = await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-one-chat-read",
        skill_snapshot_id="sha256:miner",
    )

    assert mutation.record.projection.state is (
        SessionState.GENERATING_STAGE_PROPOSAL
    )
    assert lookups == ["chat-1"]
    assert service.workspace.chat_manager.updates == 1
    assert chat.meta["wplus_sop_entry_proposal"] == {
        "proposal_id": proposal.proposal_id,
        "mode": "explicit",
        "status": "confirmed",
        "session_id": mutation.record.projection.sop_session_id,
    }


@pytest.mark.asyncio
async def test_confirm_outbox_recovers_failed_entry_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )

    class FailOnceChatManager:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(
                id="chat-1",
                session_id="logical-1",
                user_id="user-1",
                channel="console",
                meta={
                    "wplus_sop_entry_proposal": {
                        "proposal_id": proposal.proposal_id,
                        "mode": "explicit",
                        "status": "pending",
                        "session_id": None,
                    },
                },
            )
            self.update_attempts = 0

        async def get_chat(self, chat_id: str):
            return deepcopy(self.chat) if chat_id == self.chat.id else None

        async def update_chat(self, chat):
            self.update_attempts += 1
            if self.update_attempts == 1:
                raise OSError("temporary chats.json write failure")
            self.chat = deepcopy(chat)
            return deepcopy(chat)

    chat_manager = FailOnceChatManager()
    service.workspace.chat_manager = chat_manager

    async def fake_start(**kwargs):
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)

    mutation = await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-recover-projection",
        skill_snapshot_id="sha256:miner",
    )
    projected = await service.flush_chat_projection_outbox()

    assert mutation.record.projection.state is (
        SessionState.GENERATING_STAGE_PROPOSAL
    )
    assert projected == 1
    assert chat_manager.update_attempts == 2
    assert chat_manager.chat.meta["wplus_sop_entry_proposal"] == {
        "proposal_id": proposal.proposal_id,
        "mode": "explicit",
        "status": "confirmed",
        "session_id": mutation.record.projection.sop_session_id,
    }
    assert service.store.pending_outbox() == []


@pytest.mark.asyncio
async def test_submit_answers_accepts_structured_and_legacy_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    session_id = _create_structured_answer_session(service)

    async def fake_start(**kwargs):
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    mutation = await _send(
        service,
        session_id,
        "submit_answers",
        {
            "answers": {
                "q-single": {
                    "selected_option_ids": ["other"],
                    "text": "企业微信侧边栏",
                },
                "q-multi": ["chat", "api"],
                "q-note": "仅处理企业租户",
            },
        },
        request_id="cmd-structured-answers",
    )

    accepted = mutation.record.projection.answers[-1].answers
    assert mutation.record.projection.state is SessionState.GENERATING_TRIAL
    assert accepted[0].selected_option_ids == ["other"]
    assert accepted[0].text == "企业微信侧边栏"
    assert accepted[1].selected_option_ids == ["chat", "api"]
    assert accepted[2].text == "仅处理企业租户"


@pytest.mark.asyncio
async def test_submit_answers_waits_for_prior_chat_run_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    session_id = _create_structured_answer_session(service)
    tracker = service.workspace.task_tracker
    tracker.status = "running"
    tracker.idle_after_reads = 2
    starts: list[dict[str, object]] = []

    async def fake_start(**kwargs):
        if tracker.status != "idle":
            raise WPlusChatRunBusyError(
                "The owning Chat already has an active Agent run",
            )
        starts.append(kwargs)
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    mutation = await _send(
        service,
        session_id,
        "submit_answers",
        {
            "answers": {
                "q-single": {"selected_option_ids": ["fixed"]},
                "q-multi": {"selected_option_ids": ["chat"]},
                "q-note": "无",
            },
        },
        request_id="cmd-wait-for-prior-chat-run",
    )

    assert tracker.status_reads >= 2
    assert len(starts) == 1
    assert mutation.record.projection.state is SessionState.GENERATING_TRIAL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tracker_status", "expected_status", "runtime_ready"),
    [
        ("idle", "ready", True),
        ("running", "finalizing", False),
        ("stopping", "stopping", False),
    ],
)
async def test_runtime_status_projects_owning_chat_task_state(
    tmp_path: Path,
    tracker_status: str,
    expected_status: str,
    runtime_ready: bool,
) -> None:
    service = _service(tmp_path)
    session_id = _create_structured_answer_session(service)
    service.workspace.task_tracker.status = tracker_status

    status = await service.get_runtime_status(session_id)

    assert status == {
        "status": expected_status,
        "runtime_ready": runtime_ready,
        "blocking_run_id": (
            None
            if runtime_ready
            else service.get_session(session_id).projection.current_run_id
        ),
    }


@pytest.mark.asyncio
async def test_runtime_status_without_task_tracker_is_ready(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    session_id = _create_structured_answer_session(service)
    del service.workspace.task_tracker

    assert await service.get_runtime_status(session_id) == {
        "status": "ready",
        "runtime_ready": True,
        "blocking_run_id": None,
    }


@pytest.mark.asyncio
async def test_runtime_status_is_running_during_active_generation(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    session_id = "sop-runtime-running"
    _create_generation_run(
        service,
        session_id=session_id,
        created_at=datetime.now(timezone.utc),
        state=SessionState.GENERATING_QUESTIONS,
    )
    service.workspace.task_tracker.status = "running"

    assert await service.get_runtime_status(session_id) == {
        "status": "running",
        "runtime_ready": False,
        "blocking_run_id": f"run-{session_id}",
    }


@pytest.mark.asyncio
async def test_prior_chat_run_timeout_does_not_mutate_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    session_id = _create_structured_answer_session(service)
    service.workspace.task_tracker.status = "running"
    monkeypatch.setattr(
        service_module,
        "_CHAT_IDLE_WAIT_TIMEOUT_SECONDS",
        0.001,
    )
    monkeypatch.setattr(
        service_module,
        "_CHAT_IDLE_POLL_SECONDS",
        0.001,
    )
    before = service.get_session(session_id)

    with pytest.raises(
        WPlusOwningChatFinalizingError,
        match="still finalizing",
    ) as raised:
        await _send(
            service,
            session_id,
            "submit_answers",
            {
                "answers": {
                    "q-single": {"selected_option_ids": ["fixed"]},
                    "q-multi": {"selected_option_ids": ["chat"]},
                    "q-note": "无",
                },
            },
            request_id="cmd-prior-chat-run-timeout",
        )

    assert raised.value.code == "owning_chat_finalizing"
    assert raised.value.retry_after_ms > 0
    assert service.get_session(session_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("answer_overrides", "error_match"),
    [
        (
            {"q-single": {"selected_option_ids": ["missing"]}},
            "selected option",
        ),
        (
            {
                "q-single": {
                    "selected_option_ids": ["fixed", "other"],
                    "text": "自定义",
                },
            },
            "single_select",
        ),
        (
            {"q-multi": {"selected_option_ids": []}},
            "multi_select",
        ),
        (
            {
                "q-single": {
                    "selected_option_ids": ["other"],
                    "text": "   ",
                },
            },
            "custom input",
        ),
        (
            {"q-multi": {"selected_option_ids": "chat"}},
            "selected_option_ids",
        ),
    ],
)
async def test_invalid_structured_answers_do_not_advance_session(
    tmp_path: Path,
    answer_overrides: dict,
    error_match: str,
) -> None:
    service = _service(tmp_path)
    session_id = _create_structured_answer_session(service)
    answers = {
        "q-single": {"selected_option_ids": ["fixed"]},
        "q-multi": {"selected_option_ids": ["chat"]},
        "q-note": {"selected_option_ids": [], "text": "无"},
        **answer_overrides,
    }
    before = service.get_session(session_id)

    with pytest.raises(WPlusCommandError, match=error_match):
        await _send(
            service,
            session_id,
            "submit_answers",
            {"answers": answers},
            request_id=f"cmd-invalid-{error_match}",
        )

    assert service.get_session(session_id) == before


@pytest.mark.asyncio
async def test_outbox_rejects_recreated_chat_with_drifted_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )

    async def fake_start(**kwargs):
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-drift-before-outbox",
        skill_snapshot_id="sha256:miner",
    )
    updates_before_flush = service.workspace.chat_manager.updates
    service.workspace.chat_manager.chat = SimpleNamespace(
        id="chat-1",
        session_id="other-logical-session",
        user_id="other-user",
        channel="console",
        meta={},
    )

    assert await service.flush_chat_projection_outbox() == 0
    assert service.workspace.chat_manager.updates == updates_before_flush
    assert len(service.store.pending_outbox()) == 1
    assert service.workspace.chat_manager.chat.meta == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chat_attribute", "drifted_value"),
    [
        ("id", "other-chat"),
        ("user_id", "other-user"),
        ("session_id", "other-logical-session"),
    ],
)
async def test_confirm_rejects_chat_identity_drift_before_store_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    chat_attribute: str,
    drifted_value: str,
) -> None:
    service = _service(tmp_path)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    before_proposal = service.store.get_entry_proposal(proposal.proposal_id)
    setattr(service.workspace.chat_manager.chat, chat_attribute, drifted_value)
    if chat_attribute == "id":
        drifted_chat = service.workspace.chat_manager.chat

        async def get_drifted_chat(_chat_id: str):
            return drifted_chat

        monkeypatch.setattr(
            service.workspace.chat_manager,
            "get_chat",
            get_drifted_chat,
        )

    async def unexpected_start(**_kwargs):
        pytest.fail("Agent run must not start for a drifted Chat")

    monkeypatch.setattr(
        service_module,
        "start_wplus_chat_turn",
        unexpected_start,
    )
    with pytest.raises(WPlusOwnershipError):
        await service.confirm_entry(
            proposal_id=proposal.proposal_id,
            command_request_id=f"cmd-entry-drifted-{chat_attribute}",
            skill_snapshot_id="sha256:miner",
        )

    assert service.store.get_entry_proposal(proposal.proposal_id) == (
        before_proposal
    )
    assert service.store.list_sessions() == []
    assert service.store.pending_outbox() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chat_attribute", "drifted_value"),
    [
        ("id", "other-chat"),
        ("user_id", "other-user"),
        ("session_id", "other-logical-session"),
    ],
)
async def test_run_command_rejects_chat_identity_drift_before_store_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    chat_attribute: str,
    drifted_value: str,
) -> None:
    service = _service(tmp_path)
    session_id = "sop-drifted-command"
    service.store.create_session(
        SessionProjection(
            sop_session_id=session_id,
            ownership=_ownership(),
            skill_snapshot_id="sha256:miner",
            state=SessionState.AWAITING_QUEUE_CONFIRMATION,
            state_version=1,
            title="SOP",
        ),
        command_receipt=CommandReceipt(
            command_request_id="cmd-create-drifted-command",
            command="confirm_entry",
            sop_session_id=session_id,
            resulting_state_version=1,
        ),
    )
    before_record = service.get_session(session_id)
    setattr(service.workspace.chat_manager.chat, chat_attribute, drifted_value)
    if chat_attribute == "id":
        drifted_chat = service.workspace.chat_manager.chat

        async def get_drifted_chat(_chat_id: str):
            return drifted_chat

        monkeypatch.setattr(
            service.workspace.chat_manager,
            "get_chat",
            get_drifted_chat,
        )

    async def unexpected_start(**_kwargs):
        pytest.fail("Agent run must not start for a drifted Chat")

    monkeypatch.setattr(
        service_module,
        "start_wplus_chat_turn",
        unexpected_start,
    )
    with pytest.raises(WPlusOwnershipError):
        await service.execute_command(
            sop_session_id=session_id,
            command="confirm_stage_queue",
            command_request_id=f"cmd-run-drifted-{chat_attribute}",
            expected_state_version=1,
            payload={
                "stages": [
                    {"stage_id": "stage-1", "title": "确认范围"},
                    {"stage_id": "stage-2", "title": "生成结果"},
                ],
            },
        )

    assert service.get_session(session_id) == before_record
    assert service.store.pending_outbox() == []


@pytest.mark.asyncio
async def test_complete_two_stage_flow_preserves_nested_object_lists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    starts: list[dict[str, object]] = []

    async def fake_start(**kwargs):
        starts.append(kwargs)
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
    assert [start["command"] for start in starts] == [
        "propose_stage_queue",
        "confirm_stage_queue",
        "submit_answers",
        "confirm_stage",
        "submit_answers",
        "confirm_stage",
    ]
    assert starts[-1]["target_state"] == "FinalizingOutputs"
    finalizing_payload = starts[-1]["payload"]
    assert isinstance(finalizing_payload, dict)
    assert finalizing_payload["final_result_persisted"] is False
    assert await service.flush_chat_projection_outbox() > 0
    assert service.workspace.chat_manager.chat.meta[
        "wplus_sop_session"
    ]["state"] == "Completed"
    assert service.store.pending_outbox() == []


@pytest.mark.asyncio
async def test_question_generation_commands_forward_server_target_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    starts: list[dict[str, object]] = []

    async def fake_start(**kwargs):
        starts.append(kwargs)
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    proposal = service.create_entry_proposal(
        original_text="创建两环节 SOP",
        mode="explicit",
    )
    confirmed = await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-target-state",
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
        event_key="target-state-stage-proposal",
    )

    await _send(
        service,
        session_id,
        "confirm_stage_queue",
        {
            "stages": [
                {"stage_id": "stage-1", "name": "确认范围"},
                {"stage_id": "stage-2", "name": "生成结果"},
            ],
        },
        request_id="cmd-target-state-queue",
    )
    assert starts[-1]["command"] == "confirm_stage_queue"
    assert starts[-1]["target_state"] == "GeneratingQuestions"
    assert starts[-1]["payload"]["current_stage_id"] == "stage-1"

    service.append_agent_event(
        kind="question_batch",
        payload=_question_payload("stage-1", "target-state"),
        event_key="target-state-questions",
    )
    await _send(
        service,
        session_id,
        "submit_answers",
        {
            "answers": {"q-target-state": "yes"},
        },
        request_id="cmd-target-state-answers",
    )
    service.append_agent_event(
        kind="trial_plan",
        payload=_trial_plan_payload("target-state"),
        event_key="target-state-trial-plan",
    )
    service.append_agent_event(
        kind="trial_execution_completed",
        payload=_trial_result_payload("target-state"),
        event_key="target-state-trial-result",
    )
    await _send(
        service,
        session_id,
        "accept_trial",
        request_id="cmd-target-state-accept",
    )
    await _send(
        service,
        session_id,
        "confirm_stage",
        request_id="cmd-target-state-next-stage",
    )

    assert starts[-1]["command"] == "confirm_stage"
    assert starts[-1]["target_state"] == "GeneratingQuestions"
    assert starts[-1]["payload"]["current_stage_id"] == "stage-2"


@pytest.mark.asyncio
async def test_resume_question_generation_forwards_server_target_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    session_id = "sop-resume-questions"
    service.store.create_session(
        SessionProjection(
            sop_session_id=session_id,
            ownership=_ownership(),
            skill_snapshot_id="sha256:miner",
            state=SessionState.PAUSED,
            state_version=1,
            title="SOP",
            stages=[Stage(stage_id="stage-1", name="确认范围")],
            current_stage_id="stage-1",
            resume_state=SessionState.GENERATING_QUESTIONS,
        ),
        command_receipt=CommandReceipt(
            command_request_id="cmd-create-resume-questions",
            command="test_setup",
            sop_session_id=session_id,
            resulting_state_version=1,
        ),
    )
    captured: dict[str, object] = {}

    async def fake_start(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    await _send(
        service,
        session_id,
        "resume",
        request_id="cmd-resume-questions",
    )

    assert captured["target_state"] == "GeneratingQuestions"
    assert captured["payload"]["current_stage_id"] == "stage-1"


@pytest.mark.asyncio
async def test_retry_question_generation_forwards_server_target_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    session_id = "sop-retry-questions"
    service.store.create_session(
        SessionProjection(
            sop_session_id=session_id,
            ownership=_ownership(),
            skill_snapshot_id="sha256:miner",
            state=SessionState.RECOVERABLE_FAILURE,
            state_version=1,
            title="SOP",
            stages=[Stage(stage_id="stage-1", name="确认范围")],
            current_stage_id="stage-1",
            current_run_id="run-failed-questions",
            resume_state=SessionState.GENERATING_QUESTIONS,
            last_error={
                "error_code": "question_generation_failed",
                "summary": "生成问题失败",
                "failed_operation": "confirm_stage_queue",
                "failed_run_id": "run-failed-questions",
            },
        ),
        command_receipt=CommandReceipt(
            command_request_id="cmd-create-retry-questions",
            command="test_setup",
            sop_session_id=session_id,
            resulting_state_version=1,
        ),
        run_attempt=RunAttempt(
            run_id="run-failed-questions",
            attempt_id="attempt-failed-questions",
            command_request_id="cmd-failed-questions",
            command="confirm_stage_queue",
            status=RunStatus.FAILED,
        ),
    )
    captured: dict[str, object] = {}

    async def fake_start(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    await _send(
        service,
        session_id,
        "retry_current_turn",
        request_id="cmd-retry-questions",
    )

    assert captured["target_state"] == "GeneratingQuestions"
    assert captured["payload"] == {
        "target_state": "GeneratingQuestions",
        "retry_of_run_id": "run-failed-questions",
        "current_stage_id": "stage-1",
    }


def test_wrong_event_reports_allowed_events_for_generating_questions(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    _create_generation_run(
        service,
        session_id="sop-question-event-contract",
        created_at=datetime.now(timezone.utc),
        state=SessionState.GENERATING_QUESTIONS,
    )
    before = service.get_session("sop-question-event-contract")

    with pytest.raises(
        WPlusCommandError,
        match=(
            "allowed agent events: lifecycle_progress, question_batch, "
            "recoverable_failure"
        ),
    ):
        service.append_agent_event(
            kind="stage_queue_confirmed",
            payload={
                "stages": [
                    {
                        "stage_id": "stage-1",
                        "name": "确认范围",
                        "status": "clarifying",
                    },
                    {"stage_id": "stage-2", "name": "生成结果"},
                ],
            },
            event_key="wrong-stage-queue-confirmed",
            trusted_sop_session_id="sop-question-event-contract",
            trusted_run_id="run-sop-question-event-contract",
            trusted_attempt_id="attempt-sop-question-event-contract",
        )

    assert service.get_session("sop-question-event-contract") == before


def test_question_batch_rejects_stage_id_mismatch_without_side_effects(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    session_id = "sop-question-stage-mismatch"
    _create_question_generation_run(service, session_id=session_id)
    before = service.get_session(session_id)
    outbox_before = service.store.pending_outbox()

    with pytest.raises(WPlusCommandError, match="current_stage_id=stage-1"):
        service.append_agent_event(
            kind="question_batch",
            payload=_question_payload("stage-2", "mismatch"),
            event_key="mismatched-question-batch",
            trusted_sop_session_id=session_id,
            trusted_run_id=f"run-{session_id}",
            trusted_attempt_id=f"attempt-{session_id}",
        )

    assert service.get_session(session_id) == before
    assert service.store.pending_outbox() == outbox_before


def test_failed_event_can_be_corrected_within_the_same_run_attempt(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    session_id = "sop-correct-question-event"
    _create_question_generation_run(service, session_id=session_id)
    trusted_identity = {
        "trusted_sop_session_id": session_id,
        "trusted_run_id": f"run-{session_id}",
        "trusted_attempt_id": f"attempt-{session_id}",
    }
    baseline = service.get_session(session_id)
    baseline_event_ids = {event.event_id for event in baseline.events}
    baseline_outbox_ids = {
        item.projection_event_id for item in service.store.pending_outbox()
    }

    with pytest.raises(WPlusCommandError, match="allowed agent events"):
        service.append_agent_event(
            kind="stage_queue_confirmed",
            payload={
                "stages": [
                    {
                        "stage_id": "stage-1",
                        "name": "确认范围",
                        "status": "clarifying",
                    },
                    {"stage_id": "stage-2", "name": "生成结果"},
                ],
            },
            event_key="question-boundary",
            **trusted_identity,
        )

    accepted = service.append_agent_event(
        kind="question_batch",
        payload=_question_payload("stage-1", "corrected"),
        event_key="question-boundary",
        **trusted_identity,
    )

    assert accepted.record.projection.state is SessionState.AWAITING_ANSWER
    assert [
        event.kind.value
        for event in accepted.record.events
        if event.event_id not in baseline_event_ids
    ] == [
        "question_batch",
    ]
    assert [
        item.kind
        for item in service.store.pending_outbox()
        if item.projection_event_id not in baseline_outbox_ids
    ] == [
        "question_batch",
    ]


@pytest.mark.asyncio
async def test_historical_question_event_is_not_duplicate_in_next_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)

    async def fake_start(**kwargs):
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    proposal = service.create_entry_proposal(
        original_text="创建两环节 SOP",
        mode="explicit",
    )
    confirmed = await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id="cmd-entry-historical-question",
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
        event_key="historical-question-stages",
    )
    await _send(
        service,
        session_id,
        "confirm_stage_queue",
        {
            "stages": [
                {"stage_id": "stage-1", "name": "确认范围"},
                {"stage_id": "stage-2", "name": "生成结果"},
            ],
        },
        request_id="cmd-historical-question-queue",
    )
    stage_one_payload = _question_payload("stage-1", "historical")
    first = service.append_agent_event(
        kind="question_batch",
        payload=stage_one_payload,
        event_key="historical-question-key",
    )
    awaiting_answer_replay = service.append_agent_event(
        kind="question_batch",
        payload=stage_one_payload,
        event_key="historical-question-key",
    )

    assert first.duplicate is False
    assert awaiting_answer_replay.duplicate is True
    assert len(awaiting_answer_replay.record.events) == len(first.record.events)

    await _send(
        service,
        session_id,
        "submit_answers",
        {"answers": {"q-historical": "yes"}},
        request_id="cmd-historical-question-answers",
    )
    service.append_agent_event(
        kind="trial_plan",
        payload=_trial_plan_payload("historical-question"),
        event_key="historical-question-trial-plan",
    )
    service.append_agent_event(
        kind="trial_execution_completed",
        payload=_trial_result_payload("historical-question"),
        event_key="historical-question-trial-result",
    )
    await _send(
        service,
        session_id,
        "accept_trial",
        request_id="cmd-historical-question-accept",
    )
    await _send(
        service,
        session_id,
        "confirm_stage",
        request_id="cmd-historical-question-next-stage",
    )
    before = service.get_session(session_id)
    outbox_before = service.store.pending_outbox()

    with pytest.raises(WPlusCommandError, match="current_stage_id=stage-2"):
        service.append_agent_event(
            kind="question_batch",
            payload=stage_one_payload,
            event_key="historical-question-key",
        )

    assert service.get_session(session_id) == before
    assert service.store.pending_outbox() == outbox_before


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
    revision_questions = _question_payload("stage-1", "revision")
    revision_questions["questions"][0]["options"][1][
        "requires_custom_input"
    ] = True
    service.append_agent_event(
        kind="question_batch",
        payload=revision_questions,
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
    revision_result = _trial_result_payload("trial-revision")
    revision_result.update(
        {
            "confirmed_facts": ["旧范围事实"],
            "unknowns": ["旧范围未知项"],
        },
    )
    service.append_agent_event(
        kind="trial_execution_completed",
        payload=revision_result,
        event_key="revision-result",
    )

    before_revision = service.get_session(session_id).projection.state_version
    with pytest.raises(WPlusCommandError, match="custom input"):
        await _send(
            service,
            session_id,
            "revise_answer",
            {
                "revised_round": 1,
                "answers": {
                    "q-revision": {
                        "selected_option_ids": ["no"],
                        "text": "   ",
                    },
                },
            },
            request_id="cmd-invalid-custom-revision",
        )
    assert (
        service.get_session(session_id).projection.state_version
        == before_revision
    )

    revised = await _send(
        service,
        session_id,
        "revise_answer",
        {
            "revised_round": 1,
            "answers": {
                "q-revision": {
                    "selected_option_ids": ["no"],
                    "text": "改为人工复核",
                },
            },
            "reason": "范围发生变化",
        },
        request_id="cmd-revise-answer",
    )

    projection = revised.record.projection
    assert projection.state is SessionState.GENERATING_TRIAL
    assert projection.revision == 2
    assert projection.round == 1
    assert projection.answers[0].answers[0].selected_option_ids == ["no"]
    assert projection.answers[0].answers[0].text == "改为人工复核"
    assert projection.trial_result_lists == []
    assert projection.confirmed_facts == []
    assert projection.unknowns == []
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
async def test_retry_current_turn_allows_source_id_to_differ_from_chat_channel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    service.ownership = _ownership().model_copy(
        update={"source_id": "external-source-1"},
    )
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
            command_request_id="cmd-entry-external-source-retry",
            skill_snapshot_id="sha256:miner",
        )

    failed = service.get_active_session()
    assert failed is not None
    assert failed.projection.state is SessionState.RECOVERABLE_FAILURE
    assert service.workspace.chat_manager.chat.channel == "console"
    failed_run = failed.runs[0]
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
        request_id="cmd-retry-external-source",
    )

    assert captured["source_id"] == "external-source-1"
    assert captured["command"] == "retry_current_turn"
    assert captured["payload"] == {
        "target_state": "GeneratingStageProposal",
        "retry_of_run_id": failed_run.run_id,
    }
    assert (
        retried.record.projection.state
        is SessionState.GENERATING_STAGE_PROPOSAL
    )
    assert len(retried.record.runs) == 2
    assert retried.record.runs[0].status is RunStatus.FAILED
    assert retried.record.runs[1].retry_of_run_id == failed_run.run_id
    assert retried.record.runs[1].run_id == captured["run_id"]


@pytest.mark.asyncio
async def test_confirm_retry_replays_runtime_failure_without_duplicate_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    proposal = service.create_entry_proposal(
        original_text="创建 SOP",
        mode="explicit",
    )
    starts: list[dict[str, object]] = []

    async def fail_start(**kwargs):
        starts.append(kwargs)
        raise RuntimeError("runtime unavailable")

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fail_start)
    command_request_id = "cmd-entry-idempotent-runtime-failure"
    with pytest.raises(WPlusRuntimeStartError, match="runtime unavailable"):
        await service.confirm_entry(
            proposal_id=proposal.proposal_id,
            command_request_id=command_request_id,
            skill_snapshot_id="sha256:miner",
        )

    failed = service.get_active_session()
    assert failed is not None
    original_receipt = failed.command_receipts[command_request_id]
    original_outbox = service.store.pending_outbox()

    replayed = await service.confirm_entry(
        proposal_id=proposal.proposal_id,
        command_request_id=command_request_id,
        skill_snapshot_id="sha256:miner",
    )

    assert replayed.duplicate is True
    assert replayed.receipt == original_receipt
    assert (
        replayed.record.projection.sop_session_id
        == failed.projection.sop_session_id
    )
    assert len(starts) == 1
    sessions = service.store.list_sessions()
    assert len(sessions) == 1
    assert len(sessions[0].runs) == 1
    assert service.store.pending_outbox() == original_outbox
    assert len(
        {item.projection_event_id for item in original_outbox},
    ) == len(original_outbox)


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
async def test_finalizing_retry_reports_when_sop_result_is_already_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    captured: dict[str, object] = {}
    session_id = "sop-finalizing-retry"
    failed_run_id = "run-finalizing-failed"
    service.store.create_session(
        SessionProjection(
            sop_session_id=session_id,
            ownership=_ownership(),
            skill_snapshot_id="sha256:miner",
            state=SessionState.RECOVERABLE_FAILURE,
            state_version=1,
            title="SOP",
            current_run_id=failed_run_id,
            resume_state=SessionState.FINALIZING_OUTPUTS,
            last_error=RecoverableFailurePayload(
                error_code="agent_turn_incomplete",
                summary="最终产出未完成",
                failed_operation="confirm_stage",
                failed_run_id=failed_run_id,
            ),
            final_result=FinalSopResult(
                sop_spec={"name": "客户经营 SOP"},
                readable_sop="# 客户经营 SOP",
                html="<h1>客户经营 SOP</h1>",
            ),
        ),
        command_receipt=CommandReceipt(
            command_request_id="cmd-finalizing-original",
            command="confirm_stage",
            sop_session_id=session_id,
            resulting_state_version=1,
            starts_run=True,
            run_id=failed_run_id,
            attempt_id="attempt-finalizing-failed",
        ),
        run_attempt=RunAttempt(
            run_id=failed_run_id,
            attempt_id="attempt-finalizing-failed",
            command_request_id="cmd-finalizing-original",
            command="confirm_stage",
            status=RunStatus.FAILED,
        ),
    )

    async def fake_start(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(run_id=kwargs["run_id"])

    monkeypatch.setattr(service_module, "start_wplus_chat_turn", fake_start)
    await _send(
        service,
        session_id,
        "retry_current_turn",
        {"final_result_persisted": False},
        request_id="cmd-finalizing-retry",
    )

    assert captured["payload"] == {
        "target_state": "FinalizingOutputs",
        "retry_of_run_id": failed_run_id,
        "final_result_persisted": True,
    }


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
