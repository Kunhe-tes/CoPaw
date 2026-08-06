# -*- coding: utf-8 -*-
"""Ownership-aware W+ SOP application service."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from .models import (
    AnswerAcceptedPayload,
    AnswerBatch,
    ChatProjectionOutboxItem,
    CommandReceipt,
    EntryDetectionMode,
    EntryProposalStatus,
    EventKind,
    MemoryCandidatesPayload,
    MemoryCandidateStatus,
    MemoryWriteCompletedPayload,
    MemoryWriteBatchResultPayload,
    MemoryWriteFailedPayload,
    MemoryWriteReceipt,
    OwnershipTuple,
    Question,
    QuestionAnswer,
    QuestionBatchPayload,
    RecoverableFailurePayload,
    RevisionAppliedPayload,
    RunAttempt,
    RunStatus,
    SessionProjection,
    SessionRecord,
    SessionState,
    SessionStateChangedPayload,
    SopResultPayload,
    Stage,
    StageConfirmationRequiredPayload,
    StageConfirmedPayload,
    StageProposalPayload,
    StageQueue,
    StageQueueConfirmedPayload,
    StageStatus,
    StructuredInteractionEnvelope,
    TerminationSummaryPayload,
    TrialExecutionCompletedPayload,
    TrialExecutionFailedPayload,
    TrialFeedbackAcceptedPayload,
    TrialPlanPayload,
    WPlusEntryProposal,
)
from .memory_policy import (
    WPlusMemoryPolicyError,
    normalize_anonymous_user_scope,
    resolve_memory_target,
)
from .runtime import WPlusChatRunBusyError, start_wplus_chat_turn
from .store import (
    StaleStateVersionError,
    StoreMutation,
    WPlusSopStore,
    WPlusSopStoreError,
)

logger = logging.getLogger(__name__)

_OUTBOX_LOCKS_GUARD = threading.Lock()
_OUTBOX_LOCKS: dict[str, asyncio.Lock] = {}
_CHAT_IDLE_WAIT_TIMEOUT_SECONDS = 10.0
_CHAT_IDLE_POLL_SECONDS = 0.05
_CHAT_IDLE_RETRY_AFTER_MS = 1000


def _outbox_lock(store_path: Path, chat_id: str) -> asyncio.Lock:
    key = f"{store_path.expanduser().resolve()}::{chat_id}"
    with _OUTBOX_LOCKS_GUARD:
        return _OUTBOX_LOCKS.setdefault(key, asyncio.Lock())


class WPlusOwnershipError(LookupError):
    """Fail-closed ownership mismatch."""


class WPlusCommandError(ValueError):
    """Malformed or illegal state command."""


def _parse_memory_decisions(
    payload: dict[str, Any],
    candidates: list[Any],
) -> dict[str, str]:
    raw_decisions = payload.get("decisions")
    if set(payload) != {"decisions"} or not isinstance(raw_decisions, list):
        raise WPlusCommandError("Memory decisions must be a complete list")
    decisions: dict[str, str] = {}
    for raw in raw_decisions:
        if not isinstance(raw, dict) or set(raw) != {"candidate_id", "decision"}:
            raise WPlusCommandError("Invalid memory decision")
        candidate_id = raw.get("candidate_id")
        decision = raw.get("decision")
        if (
            not isinstance(candidate_id, str)
            or candidate_id in decisions
            or decision not in {"approve", "reject"}
        ):
            raise WPlusCommandError("Invalid memory decision")
        candidate = next(
            (
                item
                for item in candidates
                if item.candidate_id == candidate_id
            ),
            None,
        )
        if (
            decision == "approve"
            and candidate is not None
            and candidate.legacy_read_only
        ):
            raise WPlusCommandError(
                "Cannot approve a read-only legacy memory candidate",
            )
        decisions[candidate_id] = decision
    unresolved_ids = {
        candidate.candidate_id
        for candidate in candidates
        if candidate.status
        in {MemoryCandidateStatus.PENDING, MemoryCandidateStatus.FAILED}
    }
    if set(decisions) != unresolved_ids:
        raise WPlusCommandError("Memory decisions must cover every unresolved candidate")
    return decisions


def _memory_runtime_candidate(candidate: Any) -> dict[str, Any]:
    if candidate.legacy_read_only:
        raise WPlusCommandError(
            "Cannot write a read-only legacy memory candidate",
        )
    if (
        candidate.memory_type is None
        or not isinstance(candidate.value, dict)
        or not (candidate.evidence or "").strip()
        or candidate.target_scope is None
        or candidate.target_file is None
    ):
        raise WPlusCommandError("Memory candidate is not ready for an approved run")
    return {
        "candidate_id": candidate.candidate_id,
        "type": candidate.memory_type,
        "content": candidate.value,
        "evidence": candidate.evidence,
        "target_scope": candidate.target_scope,
        "target_file": candidate.target_file,
        "script": "scripts/memory_store.py",
        "approved": True,
    }


def _apply_memory_batch_results(
    projection: SessionProjection,
    payload: MemoryWriteBatchResultPayload,
) -> tuple[list[Any], SessionState]:
    active_ids = projection.active_memory_candidate_ids or (
        [projection.active_memory_candidate_id]
        if projection.active_memory_candidate_id
        else []
    )
    results_by_id = {result.candidate_id: result for result in payload.results}
    if set(results_by_id) != set(active_ids):
        raise WPlusCommandError(
            "Memory batch result must cover every server-bound candidate",
        )
    candidates = [candidate.model_copy(deep=True) for candidate in projection.memory_candidates]
    for index, candidate in enumerate(candidates):
        result = results_by_id.get(candidate.candidate_id)
        if result is None:
            continue
        if candidate.status is not MemoryCandidateStatus.WRITING:
            raise WPlusCommandError("Memory candidate is not being written")
        if result.status == "succeeded":
            if (
                result.target_scope != candidate.target_scope
                or result.target_file != candidate.target_file
            ):
                raise WPlusCommandError(
                    "Memory write receipt does not match approved candidate",
                )
            candidates[index] = candidate.model_copy(
                update={
                    "status": MemoryCandidateStatus.APPROVED,
                    "failure_reason": None,
                    "write_receipt": MemoryWriteReceipt(
                        memory_id=(
                            f"wplus-sop/{projection.sop_session_id}/"
                            f"{candidate.candidate_id}"
                        ),
                        target_scope=result.target_scope,
                        target_file=result.target_file,
                        reused_existing=(result.result == "duplicate"),
                        store_result=result.result,
                    ),
                },
            )
        else:
            candidates[index] = candidate.model_copy(
                update={
                    "status": MemoryCandidateStatus.FAILED,
                    "failure_reason": (result.summary or "")[:500],
                    "write_receipt": None,
                },
            )
    target = (
        SessionState.MEMORY_REVIEW
        if any(candidate.status is MemoryCandidateStatus.FAILED for candidate in candidates)
        else SessionState.COMPLETED
    )
    return candidates, target


class WPlusOwningChatFinalizingError(WPlusCommandError):
    """The owning Chat has not released its prior Agent run yet."""

    code = "owning_chat_finalizing"

    def __init__(self, *, retry_after_ms: int = _CHAT_IDLE_RETRY_AFTER_MS):
        super().__init__(
            "The prior owning Chat Agent run is still finalizing",
        )
        self.retry_after_ms = retry_after_ms


class WPlusRuntimeStartError(RuntimeError):
    """Session was persisted but its Agent run could not start."""


class _WPlusRunClaimLostError(RuntimeError):
    """The persisted run stopped being active before task registration."""


_RUN_EVENT_STATES: dict[EventKind, frozenset[SessionState]] = {
    EventKind.STAGE_PROPOSAL: frozenset(
        {SessionState.GENERATING_STAGE_PROPOSAL},
    ),
    EventKind.QUESTION_BATCH: frozenset(
        {SessionState.GENERATING_QUESTIONS},
    ),
    EventKind.TRIAL_PLAN: frozenset(
        {
            SessionState.GENERATING_QUESTIONS,
            SessionState.GENERATING_TRIAL,
        },
    ),
    EventKind.TRIAL_EXECUTION_STARTED: frozenset(
        {
            SessionState.GENERATING_QUESTIONS,
            SessionState.GENERATING_TRIAL,
            SessionState.EXECUTING_TRIAL,
        },
    ),
    EventKind.TRIAL_EXECUTION_PROGRESS: frozenset(
        {
            SessionState.GENERATING_QUESTIONS,
            SessionState.GENERATING_TRIAL,
            SessionState.EXECUTING_TRIAL,
        },
    ),
    EventKind.TRIAL_EXECUTION_COMPLETED: frozenset(
        {
            SessionState.GENERATING_QUESTIONS,
            SessionState.GENERATING_TRIAL,
            SessionState.EXECUTING_TRIAL,
        },
    ),
    EventKind.TRIAL_EXECUTION_FAILED: frozenset(
        {
            SessionState.GENERATING_QUESTIONS,
            SessionState.GENERATING_TRIAL,
            SessionState.EXECUTING_TRIAL,
        },
    ),
    EventKind.SOP_RESULT: frozenset({SessionState.FINALIZING_OUTPUTS}),
    EventKind.MEMORY_CANDIDATES: frozenset(
        {SessionState.FINALIZING_OUTPUTS},
    ),
    EventKind.MEMORY_WRITE_COMPLETED: frozenset(
        {SessionState.WRITING_MEMORY},
    ),
    EventKind.MEMORY_WRITE_FAILED: frozenset(
        {SessionState.WRITING_MEMORY},
    ),
    EventKind.MEMORY_WRITE_BATCH_RESULT: frozenset(
        {SessionState.WRITING_MEMORY},
    ),
    EventKind.LIFECYCLE_PROGRESS: frozenset(
        {
            SessionState.GENERATING_STAGE_PROPOSAL,
            SessionState.GENERATING_QUESTIONS,
            SessionState.GENERATING_TRIAL,
            SessionState.EXECUTING_TRIAL,
            SessionState.FINALIZING_OUTPUTS,
            SessionState.WRITING_MEMORY,
        },
    ),
    EventKind.RECOVERABLE_FAILURE: frozenset(
        {
            SessionState.GENERATING_STAGE_PROPOSAL,
            SessionState.GENERATING_QUESTIONS,
            SessionState.GENERATING_TRIAL,
            SessionState.EXECUTING_TRIAL,
            SessionState.FINALIZING_OUTPUTS,
            SessionState.WRITING_MEMORY,
        },
    ),
}

_PENDING_EXIT_BOUNDARIES = frozenset(
    {
        EventKind.STAGE_PROPOSAL,
        EventKind.QUESTION_BATCH,
        EventKind.TRIAL_EXECUTION_COMPLETED,
        EventKind.TRIAL_EXECUTION_FAILED,
        EventKind.MEMORY_CANDIDATES,
        EventKind.MEMORY_WRITE_COMPLETED,
        EventKind.MEMORY_WRITE_FAILED,
        EventKind.MEMORY_WRITE_BATCH_RESULT,
        EventKind.RECOVERABLE_FAILURE,
    },
)

_ORPHAN_RECOVERY_STATES = frozenset(
    {
        SessionState.GENERATING_STAGE_PROPOSAL,
        SessionState.GENERATING_QUESTIONS,
        SessionState.GENERATING_TRIAL,
        SessionState.EXECUTING_TRIAL,
        SessionState.FINALIZING_OUTPUTS,
        SessionState.WRITING_MEMORY,
    },
)
_ORPHAN_RECOVERY_GRACE = timedelta(seconds=5)


def store_path_for_workspace(workspace_dir: Path | str) -> Path:
    """Return the local single-process W+ store path."""
    return Path(workspace_dir).expanduser() / ".sop" / "wplus-sop.json"


def _validate_delivered_artifacts(
    *,
    workspace_dir: Path | str,
    result: Any,
) -> None:
    """Verify that Agent-declared deliveries are real workspace static files."""
    static_root = (
        Path(workspace_dir).expanduser().resolve() / "static"
    ).resolve()
    for artifact in result.artifacts:
        local_file = (static_root / artifact.static_file_name).resolve()
        try:
            local_file.relative_to(static_root)
        except ValueError as exc:
            raise WPlusCommandError("artifact escaped workspace static") from exc
        if not local_file.is_file():
            raise WPlusCommandError(
                f"delivered artifact is missing: {artifact.artifact_id}",
            )
        raw = local_file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != artifact.sha256:
            raise WPlusCommandError(
                f"delivered artifact hash mismatch: {artifact.artifact_id}",
            )


def _result_preview(result: Any) -> dict[str, str | None]:
    artifacts_by_id = {
        artifact.artifact_id: artifact
        for artifact in result.artifacts
    }
    markdown_artifact = artifacts_by_id.get("sop_render_md")
    html_artifact = artifacts_by_id.get("sop_render_html")
    return {
        "markdown": result.readable_sop,
        "html": result.html,
        "markdown_url": (
            markdown_artifact.static_url if markdown_artifact else None
        ),
        "html_url": html_artifact.static_url if html_artifact else None,
        "markdown_sha256": (
            markdown_artifact.sha256 if markdown_artifact else None
        ),
        "html_sha256": html_artifact.sha256 if html_artifact else None,
    }


def _same_ownership(left: OwnershipTuple, right: OwnershipTuple) -> bool:
    return left.model_dump(mode="json") == right.model_dump(mode="json")


def _serialize_stage(
    stage: Stage,
    *,
    current_stage_id: str | None,
) -> dict[str, Any]:
    if stage.status is StageStatus.CONFIRMED:
        status = "confirmed"
    elif stage.stage_id == current_stage_id:
        status = "current"
    elif stage.status is StageStatus.INVALIDATED:
        status = "invalidated"
    else:
        status = "pending"
    return {
        "stage_id": stage.stage_id,
        "title": stage.name,
        "description": stage.description,
        "status": status,
    }


def _current_trial_events(
    record: SessionRecord,
    run_id: str | None,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, dict[str, Any]],
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    plan: dict[str, Any] | None = None
    started: dict[str, Any] | None = None
    completed: dict[str, Any] | None = None
    failed: dict[str, Any] | None = None
    progress_by_step: dict[str, dict[str, Any]] = {}
    for event in record.events:
        payload = event.payload.model_dump(mode="json")
        if payload.get("run_id") != run_id:
            continue
        if event.kind is EventKind.TRIAL_PLAN:
            plan = payload
        elif event.kind is EventKind.TRIAL_EXECUTION_STARTED:
            started = payload
        elif event.kind is EventKind.TRIAL_EXECUTION_PROGRESS:
            progress_by_step[str(payload["step_id"])] = payload
        elif event.kind is EventKind.TRIAL_EXECUTION_COMPLETED:
            completed = payload
        elif event.kind is EventKind.TRIAL_EXECUTION_FAILED:
            failed = payload
    return plan, started, progress_by_step, completed, failed


def _serialize_trial_steps(
    plan: dict[str, Any] | None,
    progress_by_step: dict[str, dict[str, Any]],
    completed: dict[str, Any] | None,
    failed: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    steps: list[dict[str, Any]] = []
    capabilities: list[dict[str, Any]] = []
    seen_capabilities: set[str] = set()
    is_completed = completed is not None
    contract_verified = bool(completed and completed.get("schema_validated"))
    for step in (plan or {}).get("steps", []):
        step_id = str(step["step_id"])
        progress = progress_by_step.get(step_id, {})
        status = str(progress.get("status") or "pending")
        if is_completed:
            status = "completed"
        elif failed is not None and failed.get("failed_step_id") == step_id:
            status = "failed"
        if status not in {
            "pending",
            "running",
            "completed",
            "failed",
            "blocked",
        }:
            status = "running"
        capability_id = str(step["capability_id"])
        steps.append(
            {
                "step_id": step_id,
                "title": str(step["label"]),
                "capability": capability_id,
                "status": status,
                "summary": progress.get("summary"),
                "elapsed_ms": progress.get("elapsed_ms"),
            },
        )
        if capability_id in seen_capabilities:
            continue
        seen_capabilities.add(capability_id)
        capabilities.append(
            {
                "capability_id": capability_id,
                "name": capability_id,
                "verification_status": (
                    "verified" if is_completed else "unverified"
                ),
                "output_contract_status": (
                    "verified" if contract_verified else "unverified"
                ),
            },
        )
    return steps, capabilities


def _trial_status(
    current_attempt: RunAttempt | None,
    *,
    completed: bool,
    failed: bool,
) -> str:
    if completed:
        return "completed"
    if failed:
        return "failed"
    if current_attempt is None or current_attempt.status is RunStatus.CLAIMED:
        return "planning"
    if current_attempt.status is RunStatus.RUNNING:
        return "running"
    return "failed"


def _serialize_current_trial(
    record: SessionRecord,
    current_attempt: RunAttempt | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    projection = record.projection
    run_id = projection.current_run_id
    result_lists = projection.trial_result_lists
    if not run_id and not result_lists:
        return None, []
    plan, started, progress_by_step, completed, failed = _current_trial_events(
        record,
        run_id,
    )

    result_columns: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    if result_lists:
        result_columns = [
            column.model_dump(mode="json")
            for column in result_lists[0].columns
        ]
        result_rows = result_lists[0].rows

    steps, capabilities = _serialize_trial_steps(
        plan,
        progress_by_step,
        completed,
        failed,
    )
    trial = {
        "run_id": run_id or (current_attempt.run_id if current_attempt else ""),
        "attempt_id": current_attempt.attempt_id if current_attempt else None,
        "rerun_of_run_id": (
            current_attempt.rerun_of_run_id if current_attempt else None
        ),
        "status": _trial_status(
            current_attempt,
            completed=completed is not None,
            failed=failed is not None,
        ),
        "started_at": (started or {}).get("started_at"),
        "completed_at": (completed or {}).get("completed_at"),
        "elapsed_ms": None,
        "steps": steps,
        "summary": (completed or failed or {}).get("summary"),
        "warnings": (completed or {}).get("warnings", []),
        "result_columns": result_columns,
        "result_rows": result_rows,
    }
    return trial, capabilities


def serialize_session(record: SessionRecord) -> dict[str, Any]:
    """Project the persisted domain model into the frontend contract."""
    projection = record.projection
    current_attempt = next(
        (
            attempt
            for attempt in reversed(record.runs)
            if attempt.run_id == projection.current_run_id
        ),
        None,
    )
    question_batch = None
    if projection.current_question_batch is not None:
        batch = projection.current_question_batch
        question_batch = {
            "batch_id": batch.batch_id,
            "stage_id": batch.stage_id,
            "questions": [
                {
                    "question_id": question.question_id,
                    "kind": question.type.value,
                    "prompt": question.prompt,
                    "help_text": question.help_text,
                    "required": question.required,
                    "options": [
                        option.model_dump(mode="json")
                        for option in question.options
                    ],
                }
                for question in batch.questions
            ],
        }

    trial, capabilities = _serialize_current_trial(record, current_attempt)

    return {
        "session_id": projection.sop_session_id,
        "chat_id": projection.chat_id,
        "logical_chat_session_id": projection.logical_chat_session_id,
        "title": projection.title,
        "state": projection.state.value,
        "state_version": projection.state_version,
        "revision": projection.revision,
        "round": projection.round,
        "stages": [
            _serialize_stage(
                stage,
                current_stage_id=projection.current_stage_id,
            )
            for stage in projection.stages
        ],
        "current_stage_id": projection.current_stage_id,
        "question_batch": question_batch,
        "trial": trial,
        "facts": projection.confirmed_facts,
        "unknowns": projection.unknowns,
        "capabilities": capabilities,
        "artifacts": [
            {
                "artifact_id": artifact.artifact_id,
                "name": artifact.name,
                "format": (
                    "json"
                    if artifact.name.endswith(".json")
                    else (
                        "markdown"
                        if artifact.name.endswith(".md")
                        else "html"
                    )
                ),
                "status": "validated",
                "download_url": artifact.static_url,
                "sha256": artifact.sha256,
                "copied_by": artifact.copied_by,
            }
            for artifact in (
                projection.final_result.artifacts
                if projection.final_result is not None
                else []
            )
        ],
        "result_preview": (
            _result_preview(projection.final_result)
            if projection.final_result is not None
            else None
        ),
        "memory_candidates": [
            {
                "candidate_id": candidate.candidate_id,
                "title": candidate.summary,
                "description": candidate.summary,
                "memory_type": candidate.memory_type,
                "content": candidate.value,
                "evidence": candidate.evidence,
                "target_scope": candidate.target_scope,
                "target_file": candidate.target_file,
                "status": candidate.status.value,
                "failure_reason": candidate.failure_reason,
                "write_receipt": (
                    candidate.write_receipt.model_dump(mode="json")
                    if candidate.write_receipt is not None
                    else None
                ),
                "legacy_read_only": candidate.legacy_read_only,
            }
            for candidate in projection.memory_candidates
        ],
        "failure": (
            {
                "code": projection.last_error.error_code,
                "message": projection.last_error.summary,
                "retryable": True,
                "failed_run_id": projection.last_error.failed_run_id,
            }
            if projection.last_error is not None
            else None
        ),
        "pending_exit": (
            {
                "requested_action": projection.pending_exit_action,
                "requested_at": projection.updated_at.isoformat(),
            }
            if projection.pending_exit_action is not None
            else None
        ),
        "resume_state": (
            projection.resume_state.value
            if projection.resume_state is not None
            else None
        ),
        "updated_at": projection.updated_at.isoformat(),
    }


class WPlusSopService:
    """Coordinate the durable state machine and existing Agent runtime."""

    def __init__(
        self,
        *,
        workspace: Any,
        ownership: OwnershipTuple,
        store: WPlusSopStore | None = None,
    ):
        self.workspace = workspace
        self.ownership = ownership
        self.store = store or WPlusSopStore(
            store_path_for_workspace(workspace.workspace_dir),
        )

    def _owned_record(self, sop_session_id: str) -> SessionRecord:
        record = self.store.get_session(sop_session_id)
        if record is None or not _same_ownership(
            record.projection.ownership,
            self.ownership,
        ):
            raise WPlusOwnershipError(sop_session_id)
        return record

    def get_session(self, sop_session_id: str) -> SessionRecord:
        return self._owned_record(sop_session_id)

    def get_active_session(self) -> SessionRecord | None:
        return self.store.get_active_by_chat(self.ownership)

    async def get_runtime_status(
        self,
        sop_session_id: str,
    ) -> dict[str, Any]:
        """Project transient owning-Chat availability without persisting it."""

        record = self._owned_record(sop_session_id)
        task_tracker = getattr(self.workspace, "task_tracker", None)
        get_status = getattr(task_tracker, "get_status", None)
        if not callable(get_status):
            tracker_status = "idle"
        else:
            tracker_status = await get_status(self.ownership.chat_id)

        if tracker_status == "idle":
            status = "ready"
        elif tracker_status == "stopping":
            status = "stopping"
        else:
            projection = record.projection
            effective_state = (
                projection.resume_state
                if projection.state is SessionState.PENDING_EXIT
                else projection.state
            )
            status = (
                "running"
                if effective_state in _ORPHAN_RECOVERY_STATES
                else "finalizing"
            )
        runtime_ready = status == "ready"
        return {
            "status": status,
            "runtime_ready": runtime_ready,
            "blocking_run_id": (
                None
                if runtime_ready
                else record.projection.current_run_id
            ),
        }

    async def recover_orphaned_generation_run(
        self,
        sop_session_id: str,
    ) -> StoreMutation | None:
        """Fail an old persisted run only when its Chat task is gone."""

        record = self._owned_record(sop_session_id)
        projection = record.projection
        recovery_state = (
            projection.resume_state
            if projection.state is SessionState.PENDING_EXIT
            else projection.state
        )
        if (
            recovery_state not in _ORPHAN_RECOVERY_STATES
            or projection.current_run_id is None
        ):
            return None
        candidates = [
            attempt
            for attempt in record.runs
            if attempt.run_id == projection.current_run_id
            and attempt.status in {RunStatus.CLAIMED, RunStatus.RUNNING}
        ]
        if len(candidates) != 1:
            return None
        now = datetime.now(timezone.utc)
        if now - candidates[0].created_at < _ORPHAN_RECOVERY_GRACE:
            return None

        task_tracker = getattr(self.workspace, "task_tracker", None)
        if task_tracker is None:
            return None

        # TaskTracker serializes this callback with registration for this Chat.
        # The Store then revalidates and persists the event and run settlement
        # in one locked save.
        def _recover_while_idle() -> StoreMutation | None:
            current = self._owned_record(sop_session_id)
            current_projection = current.projection
            current_recovery_state = (
                current_projection.resume_state
                if current_projection.state is SessionState.PENDING_EXIT
                else current_projection.state
            )
            current_candidates = [
                attempt
                for attempt in current.runs
                if attempt.run_id == current_projection.current_run_id
                and attempt.status in {RunStatus.CLAIMED, RunStatus.RUNNING}
            ]
            if (
                current_recovery_state not in _ORPHAN_RECOVERY_STATES
                or current_projection.current_run_id is None
                or len(current_candidates) != 1
                or now - current_candidates[0].created_at
                < _ORPHAN_RECOVERY_GRACE
            ):
                return None
            attempt = current_candidates[0]
            payload = RecoverableFailurePayload(
                error_code="orphaned_agent_run",
                summary=(
                    "后台 Agent 任务已丢失；可以从原生成步骤安全重试。"
                ),
                failed_operation=attempt.command,
                failed_run_id=attempt.run_id,
            )
            if current_projection.state is SessionState.PENDING_EXIT:
                terminate = (
                    current_projection.pending_exit_action == "terminate"
                )
                if terminate:
                    event_kind = EventKind.TERMINATION_SUMMARY
                    event_payload: Any = TerminationSummaryPayload(
                        summary=(
                            "用户已请求结束；丢失的后台 Agent 任务已安全终止。"
                        ),
                    )
                    next_state = SessionState.TERMINATED
                    projection_changes = {
                        "pending_exit_action": None,
                        "termination_summary": event_payload,
                    }
                    run_status = RunStatus.CANCELLED
                else:
                    event_kind = EventKind.SESSION_STATE_CHANGED
                    event_payload = SessionStateChangedPayload(
                        previous_state=SessionState.PENDING_EXIT,
                        state=SessionState.PAUSED,
                        reason="orphaned_agent_run_after_save_and_exit",
                    )
                    next_state = SessionState.PAUSED
                    projection_changes = {
                        "last_error": payload,
                        "pending_exit_action": None,
                        "resume_state": SessionState.RECOVERABLE_FAILURE,
                    }
                    run_status = RunStatus.FAILED
            else:
                event_kind = EventKind.RECOVERABLE_FAILURE
                event_payload = payload
                next_state = SessionState.RECOVERABLE_FAILURE
                projection_changes = {
                    "last_error": payload,
                    "resume_state": current_recovery_state,
                }
                run_status = RunStatus.FAILED
            event = self._event(
                current,
                event_kind,
                event_payload.model_dump(mode="json"),
                event_id=f"evt_orphaned_run_{attempt.attempt_id}",
            )
            return self.store.commit_event(
                sop_session_id,
                expected_state_version=current_projection.state_version,
                event=event,
                next_state=next_state,
                projection_changes=projection_changes,
                outbox_item=self._outbox(event),
                run_completion=(
                    attempt.run_id,
                    attempt.attempt_id,
                    run_status,
                ),
            )

        try:
            _was_idle, recovered = await task_tracker.call_if_idle(
                self.ownership.chat_id,
                _recover_while_idle,
            )
            return recovered
        except (StaleStateVersionError, WPlusSopStoreError):
            logger.info(
                "W+ orphan recovery lost a concurrent race session=%s",
                sop_session_id,
            )
            return None
        except Exception:
            logger.exception(
                "Could not inspect or recover W+ Agent task session=%s",
                sop_session_id,
            )
            return None

    def _assert_runtime_claim_active(
        self,
        *,
        sop_session_id: str,
        run_id: str,
        attempt_id: str,
    ) -> None:
        """Revalidate one exact persisted claim before task registration."""

        record = self._owned_record(sop_session_id)
        runtime_state = (
            record.projection.resume_state
            if record.projection.state is SessionState.PENDING_EXIT
            else record.projection.state
        )
        if (
            runtime_state not in _ORPHAN_RECOVERY_STATES
            or record.projection.current_run_id != run_id
        ):
            raise _WPlusRunClaimLostError(
                "W+ run claim is no longer active",
            )
        matches = [
            attempt
            for attempt in record.runs
            if attempt.run_id == run_id
            and attempt.attempt_id == attempt_id
            and attempt.status in {RunStatus.CLAIMED, RunStatus.RUNNING}
        ]
        if len(matches) != 1:
            raise _WPlusRunClaimLostError(
                "W+ run attempt is no longer active",
            )

    def _chat_has_expected_ownership(self, chat: Any) -> bool:
        return bool(
            chat is not None
            and str(getattr(chat, "id", "")) == self.ownership.chat_id
            and str(getattr(chat, "user_id", "")) == self.ownership.user_id
            and str(getattr(chat, "session_id", ""))
            == self.ownership.logical_chat_session_id
        )

    @staticmethod
    def _entry_proposal_chat_metadata(
        proposal: WPlusEntryProposal,
    ) -> dict[str, Any]:
        receipt = proposal.command_receipt
        return {
            "proposal_id": proposal.proposal_id,
            "mode": proposal.detection_mode.value,
            "status": proposal.status.value,
            "session_id": (
                receipt.sop_session_id if receipt is not None else None
            ),
        }

    async def _verified_owned_chat(self) -> Any:
        """Load the Chat again at run start and fail closed on identity drift."""

        chat = await self.workspace.chat_manager.get_chat(
            self.ownership.chat_id,
        )
        if not self._chat_has_expected_ownership(chat):
            raise WPlusOwnershipError(self.ownership.chat_id)
        return chat

    async def _wait_for_owning_chat_idle(self) -> None:
        """Wait for the prior Agent producer to release the owning Chat."""

        task_tracker = getattr(self.workspace, "task_tracker", None)
        get_status = getattr(task_tracker, "get_status", None)
        if not callable(get_status):
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _CHAT_IDLE_WAIT_TIMEOUT_SECONDS
        while await get_status(self.ownership.chat_id) != "idle":
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise WPlusOwningChatFinalizingError()
            await asyncio.sleep(min(_CHAT_IDLE_POLL_SECONDS, remaining))

    async def project_entry_proposal(
        self,
        proposal: WPlusEntryProposal,
        *,
        verified_chat: Any | None = None,
    ) -> bool:
        """Persist the proposal/control-card lifecycle in owning Chat metadata."""

        try:
            chat = (
                await self._verified_owned_chat()
                if verified_chat is None
                else verified_chat
            )
            if not self._chat_has_expected_ownership(chat):
                raise WPlusOwnershipError(self.ownership.chat_id)
            chat.meta = {
                **(chat.meta or {}),
                "wplus_sop_entry_proposal": (
                    self._entry_proposal_chat_metadata(proposal)
                ),
            }
            await self.workspace.chat_manager.update_chat(chat)
            return True
        except Exception:
            logger.exception(
                "Failed to project W+ entry proposal %s into Chat %s",
                proposal.proposal_id,
                self.ownership.chat_id,
            )
            return False

    async def flush_chat_projection_outbox(self) -> int:
        """Project pending Session updates into Chat metadata, then ack them.

        The durable W+ store remains authoritative. A failed or unavailable
        Chat write leaves every item pending so a later command/event can
        retry without losing the projection.
        """
        async with _outbox_lock(self.store.path, self.ownership.chat_id):
            chat_manager = getattr(self.workspace, "chat_manager", None)
            if chat_manager is None:
                return 0
            pending: list[ChatProjectionOutboxItem] = []
            for item in self.store.pending_outbox():
                record = self.store.get_session(item.sop_session_id)
                if record is not None and _same_ownership(
                    record.projection.ownership,
                    self.ownership,
                ):
                    pending.append(item)
            if not pending:
                return 0
            pending.sort(key=lambda item: item.created_at)
            session_label = pending[-1].sop_session_id
            try:
                chat = await chat_manager.get_chat(self.ownership.chat_id)
                if not self._chat_has_expected_ownership(chat):
                    return 0
                existing_meta = chat.meta or {}
                existing_audit = existing_meta.get("wplus_sop_audit", [])
                audit = (
                    [dict(item) for item in existing_audit]
                    if isinstance(existing_audit, list)
                    else []
                )
                projected_ids = {
                    str(item.get("projection_event_id") or "")
                    for item in audit
                    if isinstance(item, dict)
                }
                for item in pending:
                    if item.projection_event_id in projected_ids:
                        continue
                    audit.append(
                        {
                            "projection_event_id": item.projection_event_id,
                            "session_id": item.sop_session_id,
                            "event_id": item.event_id,
                            "kind": item.kind,
                            "payload": item.payload,
                            "created_at": item.created_at.isoformat(),
                        },
                    )
                    projected_ids.add(item.projection_event_id)

                latest = pending[-1]
                record = self.store.get_session(latest.sop_session_id)
                if record is None or not _same_ownership(
                    record.projection.ownership,
                    self.ownership,
                ):
                    return 0
                entry_proposal = None
                for item in reversed(pending):
                    proposal_id = item.payload.get("entry_proposal_id")
                    if not isinstance(proposal_id, str) or not proposal_id:
                        continue
                    candidate = self.store.get_entry_proposal(proposal_id)
                    if candidate is not None and _same_ownership(
                        candidate.ownership,
                        self.ownership,
                    ):
                        entry_proposal = candidate
                        break
                chat.meta = {
                    **existing_meta,
                    **(
                        {
                            "wplus_sop_entry_proposal": (
                                self._entry_proposal_chat_metadata(
                                    entry_proposal,
                                )
                            ),
                        }
                        if entry_proposal is not None
                        else {}
                    ),
                    "wplus_sop_session": {
                        "session_id": record.projection.sop_session_id,
                        "title": record.projection.title,
                        "state": record.projection.state.value,
                        "state_version": record.projection.state_version,
                        "last_event_kind": latest.kind,
                    },
                    "wplus_sop_audit": audit,
                }
                persisted = await chat_manager.update_chat(chat)
                persisted_audit = (persisted.meta or {}).get(
                    "wplus_sop_audit",
                    [],
                )
                durable_ids = {
                    str(item.get("projection_event_id") or "")
                    for item in persisted_audit
                    if isinstance(item, dict)
                }
            except Exception:
                logger.exception(
                    "Failed to project W+ SOP Session %s into Chat %s",
                    session_label,
                    self.ownership.chat_id,
                )
                return 0
            acknowledged = 0
            for item in pending:
                if item.projection_event_id not in durable_ids:
                    continue
                acknowledged += int(
                    self.store.ack_outbox(item.projection_event_id),
                )
            return acknowledged

    def create_entry_proposal(
        self,
        *,
        original_text: str,
        mode: str,
        memory_user_scope: str | None = None,
    ) -> WPlusEntryProposal:
        normalized_memory_user_scope = normalize_anonymous_user_scope(
            memory_user_scope,
        )
        digest = hashlib.sha256(original_text.encode("utf-8")).hexdigest()
        identity_seed = "|".join(
            (
                self.ownership.active_chat_key,
                self.ownership.logical_chat_session_id,
                digest,
                normalized_memory_user_scope or "",
            ),
        )
        generation = 0
        while True:
            proposal_id = str(
                uuid5(
                    NAMESPACE_URL,
                    (
                        identity_seed
                        if generation == 0
                        else f"{identity_seed}|generation:{generation}"
                    ),
                ),
            )
            existing = self.store.get_entry_proposal(proposal_id)
            if existing is None:
                break
            if existing.status is EntryProposalStatus.PENDING:
                return existing
            generation += 1
        proposal = WPlusEntryProposal(
            proposal_id=proposal_id,
            ownership=self.ownership,
            logical_chat_session_id=self.ownership.logical_chat_session_id,
            original_request={"text": original_text},
            original_request_digest=f"sha256:{digest}",
            memory_user_scope=normalized_memory_user_scope,
            detection_mode=EntryDetectionMode(mode),
        )
        return self.store.create_entry_proposal(proposal)

    def _owned_proposal(self, proposal_id: str) -> WPlusEntryProposal:
        proposal = self.store.get_entry_proposal(proposal_id)
        if proposal is None or not _same_ownership(
            proposal.ownership,
            self.ownership,
        ):
            raise WPlusOwnershipError(proposal_id)
        return proposal

    async def _on_agent_turn_complete(
        self,
        *,
        sop_session_id: str,
        run_id: str,
        attempt_id: str,
        command: str,
    ) -> None:
        """Reconcile a finished TaskTracker run with the durable SOP state."""

        try:
            record = self._owned_record(sop_session_id)
            projection = record.projection
            exact_attempt = next(
                (
                    attempt
                    for attempt in record.runs
                    if attempt.run_id == run_id
                    and attempt.attempt_id == attempt_id
                ),
                None,
            )
            if exact_attempt is not None and exact_attempt.status in {
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            }:
                await self.flush_chat_projection_outbox()
                return
            if projection.current_run_id != run_id:
                self.store.finish_run(
                    sop_session_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    status=RunStatus.COMPLETED,
                )
                return

            if projection.state is SessionState.PENDING_EXIT:
                terminate = projection.pending_exit_action == "terminate"
                if terminate:
                    target = SessionState.TERMINATED
                    typed_payload: Any = TerminationSummaryPayload(
                        summary=(
                            "用户请求彻底结束；当前 Agent 响应已完整落盘。"
                        ),
                    )
                    changes: dict[str, Any] = {
                        "pending_exit_action": None,
                        "termination_summary": typed_payload,
                    }
                    kind = EventKind.TERMINATION_SUMMARY
                else:
                    target = SessionState.PAUSED
                    typed_payload = SessionStateChangedPayload(
                        previous_state=projection.state,
                        state=target,
                        reason="agent_turn_completed_after_save_and_exit",
                    )
                    changes = {"pending_exit_action": None}
                    kind = EventKind.SESSION_STATE_CHANGED
                event = self._event(
                    record,
                    kind,
                    typed_payload.model_dump(mode="json"),
                    event_id=f"evt_run_boundary_{attempt_id}",
                )
                self.store.commit_event(
                    sop_session_id,
                    expected_state_version=projection.state_version,
                    event=event,
                    next_state=target,
                    projection_changes=changes,
                    outbox_item=self._outbox(event),
                )
                self.store.finish_run(
                    sop_session_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    status=(
                        RunStatus.CANCELLED
                        if terminate
                        else RunStatus.COMPLETED
                    ),
                )
            elif projection.state in {
                SessionState.GENERATING_STAGE_PROPOSAL,
                SessionState.GENERATING_QUESTIONS,
                SessionState.GENERATING_TRIAL,
                SessionState.EXECUTING_TRIAL,
                SessionState.FINALIZING_OUTPUTS,
                SessionState.WRITING_MEMORY,
            }:
                self._record_runtime_failure(
                    sop_session_id=sop_session_id,
                    summary=(
                        "Agent turn completed without the required "
                        "structured W+ event"
                    ),
                    failed_operation=command,
                    failed_run_id=run_id,
                    failed_attempt_id=attempt_id,
                )
            else:
                status = (
                    RunStatus.FAILED
                    if (
                        projection.state is SessionState.RECOVERABLE_FAILURE
                        and projection.last_error is not None
                        and projection.last_error.failed_run_id == run_id
                    )
                    else RunStatus.COMPLETED
                )
                self.store.finish_run(
                    sop_session_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    status=status,
                )
            await self.flush_chat_projection_outbox()
        except Exception:
            logger.exception(
                "Failed to reconcile W+ Agent completion session=%s run=%s",
                sop_session_id,
                run_id,
            )

    async def confirm_entry(
        self,
        *,
        proposal_id: str,
        command_request_id: str,
        skill_snapshot_id: str,
    ) -> StoreMutation:
        proposal = self._owned_proposal(proposal_id)
        if proposal.status is EntryProposalStatus.CONFIRMED:
            existing = proposal.command_receipt
            if (
                existing is not None
                and existing.command_request_id == command_request_id
                and existing.sop_session_id
            ):
                await self.project_entry_proposal(proposal)
                return StoreMutation(
                    record=self._owned_record(existing.sop_session_id),
                    receipt=existing,
                    duplicate=True,
                )

        await self._wait_for_owning_chat_idle()
        chat = await self._verified_owned_chat()
        sop_session_id = f"sop_{uuid4().hex}"
        run_id = f"run_{uuid4().hex}"
        attempt_id = f"attempt_{uuid4().hex}"
        projection = SessionProjection(
            sop_session_id=sop_session_id,
            ownership=self.ownership,
            skill_snapshot_id=skill_snapshot_id,
            state=SessionState.GENERATING_STAGE_PROPOSAL,
            state_version=1,
            title="W+ SOP 澄清",
            memory_user_scope=proposal.memory_user_scope,
            current_run_id=run_id,
        )
        receipt = CommandReceipt(
            command_request_id=command_request_id,
            command="confirm_entry",
            sop_session_id=sop_session_id,
            resulting_state_version=1,
            starts_run=True,
            run_id=run_id,
            attempt_id=attempt_id,
        )
        attempt = RunAttempt(
            run_id=run_id,
            attempt_id=attempt_id,
            command_request_id=command_request_id,
            command="confirm_entry",
            status=RunStatus.CLAIMED,
        )
        initial_event_id = f"evt_session_created_{sop_session_id}"
        initial_outbox = ChatProjectionOutboxItem(
            projection_event_id=f"chatproj_{initial_event_id}",
            sop_session_id=sop_session_id,
            chat_id=self.ownership.chat_id,
            event_id=initial_event_id,
            kind=EventKind.SESSION_STATE_CHANGED.value,
            payload={
                "state_version": projection.state_version,
                "entry_proposal_id": proposal_id,
                "kind": EventKind.SESSION_STATE_CHANGED.value,
                "payload": {
                    "previous_state": None,
                    "state": projection.state.value,
                    "reason": "entry_confirmed",
                },
            },
        )
        mutation = self.store.confirm_entry_proposal(
            proposal_id,
            projection=projection,
            receipt=receipt,
            run_attempt=attempt,
            outbox_item=initial_outbox,
        )
        if mutation.duplicate:
            return mutation

        confirmed_proposal = self.store.get_entry_proposal(proposal_id)
        if confirmed_proposal is not None:
            await self.project_entry_proposal(
                confirmed_proposal,
                verified_chat=chat,
            )
        original_text = str(
            (proposal.original_request or {}).get("text", "")
            if isinstance(proposal.original_request, dict)
            else "",
        )
        try:
            await start_wplus_chat_turn(
                workspace=self.workspace,
                chat=chat,
                user_id=self.ownership.user_id,
                source_id=self.ownership.source_id,
                sop_session_id=sop_session_id,
                command="propose_stage_queue",
                payload={
                    "original_request": original_text,
                    "memory_user_scope": proposal.memory_user_scope,
                },
                run_id=run_id,
                attempt_id=attempt_id,
                target_state=SessionState.GENERATING_STAGE_PROPOSAL.value,
                on_complete=lambda: self._on_agent_turn_complete(
                    sop_session_id=sop_session_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    command="propose_stage_queue",
                ),
                before_start=lambda: self._assert_runtime_claim_active(
                    sop_session_id=sop_session_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                ),
            )
        except _WPlusRunClaimLostError:
            return StoreMutation(
                record=self._owned_record(sop_session_id),
                receipt=receipt,
            )
        except (RuntimeError, WPlusChatRunBusyError) as exc:
            self._record_runtime_failure(
                sop_session_id=sop_session_id,
                summary=str(exc),
                failed_operation="propose_stage_queue",
                failed_run_id=run_id,
                failed_attempt_id=attempt_id,
            )
            raise WPlusRuntimeStartError(str(exc)) from exc
        return mutation

    def reject_entry(
        self,
        *,
        proposal_id: str,
        command_request_id: str,
    ) -> WPlusEntryProposal:
        self._owned_proposal(proposal_id)
        token = f"suppress_{uuid4().hex}"
        receipt = CommandReceipt(
            command_request_id=command_request_id,
            command="reject_entry",
            sop_session_id=None,
        )
        return self.store.resolve_entry_proposal(
            proposal_id,
            status=EntryProposalStatus.REJECTED,
            receipt=receipt,
            suppression_token=token,
        )

    def validate_suppression(
        self,
        *,
        proposal_id: str,
        suppression_token: str,
        original_text: str,
    ) -> bool:
        try:
            self._owned_proposal(proposal_id)
        except WPlusOwnershipError:
            return False
        digest = "sha256:" + hashlib.sha256(
            original_text.encode("utf-8"),
        ).hexdigest()
        return self.store.suppression_matches(
            proposal_id,
            suppression_token=suppression_token,
            original_request_digest=digest,
            ownership=self.ownership,
        )

    def consume_suppression(
        self,
        *,
        proposal_id: str,
        claim_id: str,
        suppression_token: str,
        original_text: str,
    ) -> bool:
        digest = "sha256:" + hashlib.sha256(
            original_text.encode("utf-8"),
        ).hexdigest()
        return self.store.consume_suppression(
            proposal_id,
            claim_id=claim_id,
            suppression_token=suppression_token,
            original_request_digest=digest,
            ownership=self.ownership,
        )

    def claim_suppression(
        self,
        *,
        proposal_id: str,
        suppression_token: str,
        original_text: str,
    ) -> str | None:
        digest = "sha256:" + hashlib.sha256(
            original_text.encode("utf-8"),
        ).hexdigest()
        return self.store.claim_suppression(
            proposal_id,
            suppression_token=suppression_token,
            original_request_digest=digest,
            ownership=self.ownership,
        )

    def release_suppression_claim(
        self,
        *,
        proposal_id: str,
        claim_id: str,
    ) -> bool:
        return self.store.release_suppression_claim(
            proposal_id,
            claim_id=claim_id,
            ownership=self.ownership,
        )

    def _record_runtime_failure(
        self,
        *,
        sop_session_id: str,
        summary: str,
        failed_operation: str,
        failed_run_id: str | None,
        failed_attempt_id: str | None,
    ) -> None:
        record = self._owned_record(sop_session_id)
        payload = RecoverableFailurePayload(
            error_code="runtime_start_failed",
            summary=summary or "Agent runtime could not start",
            failed_operation=failed_operation,
            failed_run_id=failed_run_id,
        )
        event = self._event(
            record,
            EventKind.RECOVERABLE_FAILURE,
            payload.model_dump(mode="json"),
        )
        self.store.commit_event(
            sop_session_id,
            expected_state_version=record.projection.state_version,
            event=event,
            next_state=SessionState.RECOVERABLE_FAILURE,
            projection_changes={
                "last_error": payload,
                "resume_state": record.projection.state,
            },
            outbox_item=self._outbox(event),
            run_completion=(
                (
                    failed_run_id,
                    failed_attempt_id,
                    RunStatus.FAILED,
                )
                if failed_run_id is not None
                and failed_attempt_id is not None
                else None
            ),
        )

    @staticmethod
    def _event(
        record: SessionRecord,
        kind: EventKind,
        payload: dict[str, Any],
        *,
        event_id: str | None = None,
    ) -> StructuredInteractionEnvelope:
        projection = record.projection
        return StructuredInteractionEnvelope(
            event_id=event_id or f"evt_{uuid4().hex}",
            sop_session_id=projection.sop_session_id,
            chat_id=projection.chat_id,
            revision=projection.revision,
            round=projection.round,
            state_version=projection.state_version + 1,
            kind=kind,
            payload=payload,
        )

    @staticmethod
    def _outbox(
        event: StructuredInteractionEnvelope,
    ) -> ChatProjectionOutboxItem:
        return ChatProjectionOutboxItem(
            projection_event_id=f"chatproj_{event.event_id}",
            sop_session_id=event.sop_session_id,
            chat_id=event.chat_id,
            event_id=event.event_id,
            kind=event.kind.value,
            payload={
                "state_version": event.state_version,
                "kind": event.kind.value,
                "payload": event.payload.model_dump(mode="json"),
            },
        )

    @staticmethod
    def _normalize_stages(raw: Any) -> list[Stage]:
        if not isinstance(raw, list):
            raise WPlusCommandError("stages must be an array")
        stages = [
            Stage(
                stage_id=str(item.get("stage_id", "")),
                name=str(item.get("title", item.get("name", ""))),
                description=item.get("description"),
            )
            for item in raw
            if isinstance(item, dict)
        ]
        return StageQueue(stages=stages).stages

    @staticmethod
    def _answers_payload(
        record: SessionRecord,
        payload: dict[str, Any],
    ) -> AnswerAcceptedPayload:
        batch = record.projection.current_question_batch
        if batch is None:
            raise WPlusCommandError("No current question batch")
        raw_answers = payload.get("answers")
        if not isinstance(raw_answers, dict):
            raise WPlusCommandError("answers must be an object")
        answers: list[QuestionAnswer] = []
        for question in batch.questions:
            value = raw_answers.get(question.question_id)
            answer = WPlusSopService._question_answer(question, value)
            answers.append(answer)
        return AnswerAcceptedPayload(
            batch_id=batch.batch_id,
            stage_id=batch.stage_id,
            answers=answers,
        )

    @staticmethod
    def _questions_for_answer_batch(
        record: SessionRecord,
        answer_batch: AnswerBatch,
    ) -> dict[str, Question]:
        """Recover the immutable question contract used by a saved answer."""
        for event in reversed(record.events):
            if (
                event.kind is EventKind.QUESTION_BATCH
                and isinstance(event.payload, QuestionBatchPayload)
                and event.payload.batch_id == answer_batch.batch_id
            ):
                return {
                    question.question_id: question
                    for question in event.payload.questions
                }
        return {}

    @staticmethod
    def _structured_question_answer(
        question_id: str,
        value: dict[str, Any],
    ) -> QuestionAnswer:
        unexpected = set(value) - {"selected_option_ids", "text"}
        if unexpected:
            raise WPlusCommandError(
                "structured answers only allow selected_option_ids and text",
            )
        selected = value.get("selected_option_ids", [])
        if not isinstance(selected, list) or any(
            not isinstance(item, str) or not item for item in selected
        ):
            raise WPlusCommandError(
                "selected_option_ids must be an array of non-empty strings",
            )
        if len(selected) != len(set(selected)):
            raise WPlusCommandError("selected_option_ids must be unique")
        text = value.get("text")
        if text is not None and not isinstance(text, str):
            raise WPlusCommandError("answer text must be a string")
        try:
            return QuestionAnswer(
                question_id=question_id,
                selected_option_ids=selected,
                text=text,
            )
        except ValueError as exc:
            raise WPlusCommandError(str(exc)) from exc

    @staticmethod
    def _validated_structured_question_answer(
        question: Question,
        value: dict[str, Any],
    ) -> QuestionAnswer:
        selected = value.get("selected_option_ids", [])
        if not isinstance(selected, list):
            raise WPlusCommandError(
                "selected_option_ids must be an array of non-empty strings",
            )
        if question.type.value == "single_select" and len(selected) != 1:
            raise WPlusCommandError(
                "single_select answers require exactly one selected option",
            )
        if question.type.value == "multi_select" and not selected:
            raise WPlusCommandError(
                "multi_select answers require at least one selected option",
            )
        answer = WPlusSopService._structured_question_answer(
            question.question_id,
            value,
        )
        option_ids = {option.option_id for option in question.options}
        unknown = set(answer.selected_option_ids) - option_ids
        if unknown:
            raise WPlusCommandError(
                "selected option IDs must belong to the current question",
            )
        if question.type.value == "free_text" and answer.selected_option_ids:
            raise WPlusCommandError(
                "free_text answers cannot contain selected option IDs",
            )
        return answer

    @staticmethod
    def _legacy_question_answer(
        question: Question,
        value: Any,
    ) -> QuestionAnswer:
        if isinstance(value, list):
            return QuestionAnswer(
                question_id=question.question_id,
                selected_option_ids=[str(item) for item in value],
            )
        if question.type.value == "single_select":
            return QuestionAnswer(
                question_id=question.question_id,
                selected_option_ids=[str(value or "")],
            )
        return QuestionAnswer(
            question_id=question.question_id,
            text=str(value or ""),
        )

    @staticmethod
    def _validate_custom_answer_text(
        question: Question,
        answer: QuestionAnswer,
    ) -> None:
        custom_option_ids = {
            option.option_id
            for option in question.options
            if option.requires_custom_input
        }
        if custom_option_ids.intersection(answer.selected_option_ids) and not (
            answer.text or ""
        ).strip():
            raise WPlusCommandError(
                "selected option requires non-empty custom input text",
            )

    @staticmethod
    def _question_answer(question: Question, value: Any) -> QuestionAnswer:
        answer = (
            WPlusSopService._validated_structured_question_answer(
                question,
                value,
            )
            if isinstance(value, dict)
            else WPlusSopService._legacy_question_answer(question, value)
        )
        WPlusSopService._validate_custom_answer_text(question, answer)
        return answer

    async def execute_command(
        self,
        *,
        sop_session_id: str,
        command: str,
        command_request_id: str,
        expected_state_version: int,
        payload: dict[str, Any],
    ) -> StoreMutation:
        record = self._owned_record(sop_session_id)
        projection = record.projection
        existing_receipt = record.command_receipts.get(command_request_id)
        if existing_receipt is not None:
            if existing_receipt.command != command:
                raise WPlusCommandError(
                    "command_request_id was already used for another command",
                )
            return StoreMutation(
                record=record,
                receipt=existing_receipt,
                duplicate=True,
            )
        if projection.state_version != expected_state_version:
            raise StaleStateVersionError(
                f"Expected {expected_state_version}, "
                f"found {projection.state_version}",
            )

        target_state: SessionState
        kind: EventKind
        typed_payload: Any
        changes: dict[str, Any] = {}
        starts_run = False
        retry_of: str | None = None
        rerun_of: str | None = None
        cancel_active_run = False
        runtime_payload = payload

        if command == "confirm_stage_queue":
            if projection.state is not SessionState.AWAITING_QUEUE_CONFIRMATION:
                raise WPlusCommandError("Stage queue is not awaiting confirmation")
            stages = self._normalize_stages(payload.get("stages"))
            stages[0].status = StageStatus.CLARIFYING
            typed_payload = StageQueueConfirmedPayload(stages=stages)
            target_state = SessionState.GENERATING_QUESTIONS
            kind = EventKind.STAGE_QUEUE_CONFIRMED
            changes = {
                "stages": stages,
                "current_stage_id": stages[0].stage_id,
            }
            starts_run = True
        elif command == "submit_answers":
            if projection.state is not SessionState.AWAITING_ANSWER:
                raise WPlusCommandError("Session is not awaiting answers")
            typed_payload = self._answers_payload(record, payload)
            target_state = SessionState.GENERATING_QUESTIONS
            kind = EventKind.ANSWER_ACCEPTED
            changes = {
                "answers": [*projection.answers, typed_payload],
                "round": projection.round + 1,
            }
            starts_run = True
        elif command == "submit_trial_feedback":
            if projection.state is not SessionState.AWAITING_TRIAL_FEEDBACK:
                raise WPlusCommandError("Session is not awaiting trial feedback")
            feedback = str(payload.get("feedback", "")).strip()
            rerun_of = str(
                payload.get("rerun_of_run_id")
                or projection.current_run_id
                or "",
            )
            if not feedback or not rerun_of:
                raise WPlusCommandError("feedback and prior run are required")
            target_state = SessionState.GENERATING_TRIAL
            kind = EventKind.TRIAL_FEEDBACK_ACCEPTED
            typed_payload = TrialFeedbackAcceptedPayload(
                feedback=feedback,
                prior_run_id=rerun_of,
                rerun_id="pending",
            )
            changes = {
                "trial_feedback": [*projection.trial_feedback, feedback],
                "trial_result_lists": [],
            }
            starts_run = True
        elif command == "accept_trial":
            if projection.state is not SessionState.AWAITING_TRIAL_FEEDBACK:
                raise WPlusCommandError("Session is not awaiting trial feedback")
            if not projection.current_stage_id:
                raise WPlusCommandError("Current stage is missing")
            target_state = SessionState.AWAITING_STAGE_CONFIRMATION
            kind = EventKind.STAGE_CONFIRMATION_REQUIRED
            typed_payload = StageConfirmationRequiredPayload(
                stage_id=projection.current_stage_id,
                summary="用户接受当前预跑结果，等待环节确认。",
            )
        elif command == "confirm_stage":
            if projection.state is not SessionState.AWAITING_STAGE_CONFIRMATION:
                raise WPlusCommandError("Stage is not awaiting confirmation")
            current_id = projection.current_stage_id
            if not current_id:
                raise WPlusCommandError("Current stage is missing")
            stages = [stage.model_copy(deep=True) for stage in projection.stages]
            current_index = next(
                (
                    index
                    for index, stage in enumerate(stages)
                    if stage.stage_id == current_id
                ),
                -1,
            )
            if current_index < 0:
                raise WPlusCommandError("Current stage is not in the queue")
            stages[current_index].status = StageStatus.CONFIRMED
            is_final = current_index == len(stages) - 1
            next_stage_id = None
            if is_final:
                target_state = SessionState.FINALIZING_OUTPUTS
            else:
                stages[current_index + 1].status = StageStatus.CLARIFYING
                next_stage_id = stages[current_index + 1].stage_id
                target_state = SessionState.GENERATING_QUESTIONS
            kind = EventKind.STAGE_CONFIRMED
            typed_payload = StageConfirmedPayload(
                stage_id=current_id,
                next_stage_id=next_stage_id,
                is_final_stage=is_final,
            )
            changes = {
                "stages": stages,
                "current_stage_id": next_stage_id or current_id,
                "current_question_batch": None,
            }
            starts_run = True
        elif command == "revise_answer":
            if projection.state not in {
                SessionState.AWAITING_ANSWER,
                SessionState.AWAITING_TRIAL_FEEDBACK,
                SessionState.AWAITING_STAGE_CONFIRMATION,
            }:
                raise WPlusCommandError(
                    "Answers can only be revised from a stable active state",
                )
            revised_round = int(payload.get("revised_round") or 0)
            if revised_round < 1 or revised_round > len(projection.answers):
                raise WPlusCommandError("Invalid revised_round")
            previous = projection.answers[revised_round - 1]
            raw_answers = payload.get("answers")
            if not isinstance(raw_answers, dict):
                raise WPlusCommandError("answers must be an object")
            replacement_answers: list[QuestionAnswer] = []
            original_questions = self._questions_for_answer_batch(
                record,
                previous,
            )
            for prior_answer in previous.answers:
                value = raw_answers.get(prior_answer.question_id)
                original_question = original_questions.get(
                    prior_answer.question_id,
                )
                if original_question is not None:
                    replacement_answers.append(
                        self._question_answer(original_question, value),
                    )
                elif isinstance(value, dict):
                    replacement_answers.append(
                        self._structured_question_answer(
                            prior_answer.question_id,
                            value,
                        ),
                    )
                elif isinstance(value, list):
                    replacement_answers.append(
                        QuestionAnswer(
                            question_id=prior_answer.question_id,
                            selected_option_ids=[
                                str(item) for item in value
                            ],
                        ),
                    )
                elif prior_answer.text is not None:
                    replacement_answers.append(
                        QuestionAnswer(
                            question_id=prior_answer.question_id,
                            text=str(value or ""),
                        ),
                    )
                else:
                    replacement_answers.append(
                        QuestionAnswer(
                            question_id=prior_answer.question_id,
                            selected_option_ids=[str(value or "")],
                        ),
                    )
            replacement = AnswerBatch(
                batch_id=previous.batch_id,
                stage_id=previous.stage_id,
                answers=replacement_answers,
            )
            invalidated_event_ids = [
                event.event_id
                for event in record.events
                if event.round >= revised_round
            ]
            typed_payload = RevisionAppliedPayload(
                revised_round=revised_round,
                invalidated_event_ids=invalidated_event_ids,
                reason=str(payload.get("reason") or "user_revised_answer"),
            )
            stages = [
                stage.model_copy(deep=True) for stage in projection.stages
            ]
            revised_stage_seen = False
            for stage in stages:
                if stage.stage_id == previous.stage_id:
                    stage.status = StageStatus.CLARIFYING
                    revised_stage_seen = True
                elif revised_stage_seen:
                    stage.status = StageStatus.PENDING
            target_state = SessionState.GENERATING_QUESTIONS
            kind = EventKind.REVISION_APPLIED
            changes = {
                "revision": projection.revision + 1,
                "round": revised_round,
                "answers": [
                    *projection.answers[: revised_round - 1],
                    replacement,
                ],
                "invalidated_history": [
                    *projection.invalidated_history,
                    {
                        "revision": projection.revision,
                        "revised_round": revised_round,
                        "invalidated_event_ids": invalidated_event_ids,
                        "answers": [
                            answer.model_dump(mode="json")
                            for answer in projection.answers[
                                revised_round - 1 :
                            ]
                        ],
                        "trial_result_lists": [
                            result.model_dump(mode="json")
                            for result in projection.trial_result_lists
                        ],
                        "final_result": (
                            projection.final_result.model_dump(mode="json")
                            if projection.final_result is not None
                            else None
                        ),
                        "memory_candidates": [
                            candidate.model_dump(mode="json")
                            for candidate in projection.memory_candidates
                        ],
                    },
                ],
                "stages": stages,
                "current_stage_id": previous.stage_id,
                "current_question_batch": None,
                "trial_result_lists": [],
                "trial_feedback": [],
                "confirmed_facts": [],
                "unknowns": [],
                "final_result": None,
                "memory_candidates": [],
                "last_error": None,
            }
            starts_run = True
        elif command in {"save_and_exit", "terminate"}:
            terminate = command == "terminate"
            if projection.state in {
                SessionState.COMPLETED,
                SessionState.TERMINATED,
            }:
                raise WPlusCommandError("Session is already terminal")
            if projection.state is SessionState.PENDING_EXIT:
                raise WPlusCommandError("Session already has a pending exit")
            if (
                command == "save_and_exit"
                and projection.state is SessionState.PAUSED
            ):
                raise WPlusCommandError("Session is already paused")
            generating = projection.state in {
                SessionState.GENERATING_STAGE_PROPOSAL,
                SessionState.GENERATING_QUESTIONS,
                SessionState.GENERATING_TRIAL,
                SessionState.EXECUTING_TRIAL,
                SessionState.FINALIZING_OUTPUTS,
                SessionState.WRITING_MEMORY,
            }
            target_state = (
                SessionState.PENDING_EXIT
                if generating
                else (
                    SessionState.TERMINATED
                    if terminate
                    else SessionState.PAUSED
                )
            )
            kind = (
                EventKind.TERMINATION_SUMMARY
                if target_state is SessionState.TERMINATED
                else EventKind.SESSION_STATE_CHANGED
            )
            if kind is EventKind.TERMINATION_SUMMARY:
                typed_payload = TerminationSummaryPayload(
                    summary="用户彻底结束 W+ SOP 会话。",
                )
                changes["termination_summary"] = typed_payload
            else:
                typed_payload = SessionStateChangedPayload(
                    previous_state=projection.state,
                    state=target_state,
                    reason=command,
                )
                changes.update(
                    {
                        "resume_state": projection.state,
                        "pending_exit_action": (
                            "terminate"
                            if terminate
                            else (
                                "pause"
                                if target_state is SessionState.PENDING_EXIT
                                else None
                            )
                        ),
                    },
                )
        elif command in {"cancel_run_and_pause", "continue_waiting"}:
            if projection.state is not SessionState.PENDING_EXIT:
                raise WPlusCommandError("Session has no pending exit")
            if command == "continue_waiting":
                target_state = SessionState.PENDING_EXIT
                kind = EventKind.SESSION_STATE_CHANGED
                typed_payload = SessionStateChangedPayload(
                    previous_state=projection.state,
                    state=target_state,
                    reason="continue_waiting",
                )
            else:
                target_state = SessionState.PAUSED
                kind = EventKind.SESSION_STATE_CHANGED
                typed_payload = SessionStateChangedPayload(
                    previous_state=projection.state,
                    state=target_state,
                    reason="cancel_run_and_pause",
                )
                changes = {
                    "resume_state": (
                        projection.resume_state
                        if projection.resume_state is not SessionState.PENDING_EXIT
                        else SessionState.RECOVERABLE_FAILURE
                    ),
                    "pending_exit_action": None,
                }
                cancel_active_run = True
        elif command == "resume":
            if projection.state is not SessionState.PAUSED:
                raise WPlusCommandError("Session is not paused")
            target_state = projection.resume_state or SessionState.RECOVERABLE_FAILURE
            if target_state is SessionState.PENDING_EXIT:
                target_state = SessionState.RECOVERABLE_FAILURE
            kind = EventKind.SESSION_STATE_CHANGED
            typed_payload = SessionStateChangedPayload(
                previous_state=projection.state,
                state=target_state,
                reason="resume",
            )
            changes = {"resume_state": None, "pending_exit_action": None}
            starts_run = target_state in {
                SessionState.GENERATING_STAGE_PROPOSAL,
                SessionState.GENERATING_QUESTIONS,
                SessionState.GENERATING_TRIAL,
                SessionState.FINALIZING_OUTPUTS,
                SessionState.WRITING_MEMORY,
            }
        elif command == "retry_current_turn":
            if projection.state is not SessionState.RECOVERABLE_FAILURE:
                raise WPlusCommandError("Session has no recoverable failure")
            target_state = projection.resume_state
            failed_run_id = (
                projection.last_error.failed_run_id
                if projection.last_error is not None
                else None
            )
            failed_attempts = [
                attempt
                for attempt in record.runs
                if attempt.run_id == failed_run_id
                and attempt.status is RunStatus.FAILED
            ]
            if (
                target_state not in _ORPHAN_RECOVERY_STATES
                or failed_run_id is None
                or len(failed_attempts) != 1
            ):
                raise WPlusCommandError(
                    "Recoverable failure has no valid server-owned retry target",
                )
            kind = EventKind.SESSION_STATE_CHANGED
            typed_payload = SessionStateChangedPayload(
                previous_state=projection.state,
                state=target_state,
                reason="retry_current_turn",
            )
            retry_of = failed_run_id
            changes = {"last_error": None, "resume_state": None}
            runtime_payload = {
                "target_state": target_state.value,
                "retry_of_run_id": failed_run_id,
            }
            starts_run = True
        elif command == "confirm_outputs":
            if projection.state is not SessionState.OUTPUT_REVIEW:
                raise WPlusCommandError("Session outputs are not awaiting confirmation")
            target_state = (
                SessionState.MEMORY_REVIEW
                if projection.memory_candidates
                else SessionState.COMPLETED
            )
            kind = EventKind.SESSION_STATE_CHANGED
            typed_payload = SessionStateChangedPayload(
                previous_state=projection.state,
                state=target_state,
                reason="outputs_confirmed",
            )
        elif command in {"resolve_memory", "skip_memory"}:
            if projection.state is not SessionState.MEMORY_REVIEW:
                raise WPlusCommandError("Session is not reviewing memory")
            candidates = [
                candidate.model_copy(deep=True)
                for candidate in projection.memory_candidates
            ]
            if command == "skip_memory":
                decisions = {
                    candidate.candidate_id: "reject"
                    for candidate in candidates
                    if candidate.status
                    in {MemoryCandidateStatus.PENDING, MemoryCandidateStatus.FAILED}
                }
            else:
                decisions = _parse_memory_decisions(payload, candidates)
            approved_payloads: list[dict[str, Any]] = []
            active_ids: list[str] = []
            for index, candidate in enumerate(candidates):
                decision = decisions.get(candidate.candidate_id)
                if decision is None:
                    continue
                if decision == "approve":
                    approved_payloads.append(_memory_runtime_candidate(candidate))
                    active_ids.append(candidate.candidate_id)
                    status = MemoryCandidateStatus.WRITING
                else:
                    status = MemoryCandidateStatus.REJECTED
                candidates[index] = candidate.model_copy(
                    update={
                        "status": status,
                        "failure_reason": None,
                        "write_receipt": None,
                    },
                )
            starts_run = bool(active_ids)
            target_state = (
                SessionState.WRITING_MEMORY
                if starts_run
                else SessionState.COMPLETED
            )
            if starts_run:
                runtime_payload = {"candidates": approved_payloads}
            kind = EventKind.MEMORY_CANDIDATES
            typed_payload = MemoryCandidatesPayload(candidates=candidates)
            changes = {
                "memory_candidates": candidates,
                "active_memory_candidate_id": None,
                "active_memory_candidate_ids": active_ids,
            }
        else:
            raise WPlusCommandError(f"Unsupported command: {command}")

        if starts_run and target_state is SessionState.GENERATING_QUESTIONS:
            current_stage_id = changes.get(
                "current_stage_id",
                projection.current_stage_id,
            )
            if not isinstance(current_stage_id, str) or not current_stage_id:
                raise WPlusCommandError(
                    "Question generation requires a current_stage_id",
                )
            runtime_payload = {
                **runtime_payload,
                "current_stage_id": current_stage_id,
            }
        if (
            starts_run
            and target_state is SessionState.WRITING_MEMORY
            and "candidates" not in runtime_payload
        ):
            active_ids = projection.active_memory_candidate_ids or (
                [projection.active_memory_candidate_id]
                if projection.active_memory_candidate_id
                else []
            )
            active_candidates = [
                candidate
                for candidate in projection.memory_candidates
                if candidate.candidate_id in active_ids
            ]
            if len(active_candidates) != len(active_ids):
                raise WPlusCommandError(
                    "Memory run has no server-bound candidates",
                )
            runtime_payload = {
                **runtime_payload,
                "candidates": [
                    _memory_runtime_candidate(candidate)
                    for candidate in active_candidates
                ],
            }
        if starts_run and target_state is SessionState.FINALIZING_OUTPUTS:
            runtime_payload = {
                **runtime_payload,
                "final_result_persisted": projection.final_result is not None,
                "memory_user_scope_available": bool(
                    projection.memory_user_scope,
                ),
            }

        if starts_run:
            await self._wait_for_owning_chat_idle()
        chat = await self._verified_owned_chat() if starts_run else None
        run_id = f"run_{uuid4().hex}" if starts_run else None
        attempt_id = f"attempt_{uuid4().hex}" if starts_run else None
        if run_id is not None:
            changes["current_run_id"] = run_id
        if isinstance(typed_payload, TrialFeedbackAcceptedPayload) and run_id:
            typed_payload = typed_payload.model_copy(
                update={"rerun_id": run_id},
            )
        event = self._event(
            record,
            kind,
            typed_payload.model_dump(mode="json"),
        )
        if command == "submit_answers":
            event = event.model_copy(
                update={"round": projection.round + 1},
            )
        elif command == "revise_answer":
            event = event.model_copy(
                update={
                    "revision": projection.revision + 1,
                    "round": int(payload["revised_round"]),
                },
            )
        receipt = CommandReceipt(
            command_request_id=command_request_id,
            command=command,
            sop_session_id=sop_session_id,
            resulting_state_version=event.state_version,
            starts_run=starts_run,
            run_id=run_id,
            attempt_id=attempt_id,
        )
        attempt = (
            RunAttempt(
                run_id=run_id,
                attempt_id=attempt_id,
                command_request_id=command_request_id,
                command=command,
                status=RunStatus.CLAIMED,
                retry_of_run_id=retry_of,
                rerun_of_run_id=rerun_of,
            )
            if run_id and attempt_id
            else None
        )
        if cancel_active_run:
            try:
                await self.workspace.task_tracker.request_stop(
                    self.ownership.chat_id,
                )
            except Exception as exc:
                raise WPlusCommandError(
                    "The active run could not be cancelled",
                ) from exc
        mutation = self.store.commit_event(
            sop_session_id,
            expected_state_version=expected_state_version,
            event=event,
            next_state=target_state,
            projection_changes=changes,
            outbox_item=self._outbox(event),
            command_receipt=receipt,
            run_attempt=attempt,
        )
        if cancel_active_run and projection.current_run_id:
            active_attempt = next(
                (
                    item
                    for item in record.runs
                    if item.run_id == projection.current_run_id
                    and item.status in {RunStatus.CLAIMED, RunStatus.RUNNING}
                ),
                None,
            )
            if active_attempt is not None:
                try:
                    self.store.finish_run(
                        sop_session_id,
                        run_id=active_attempt.run_id,
                        attempt_id=active_attempt.attempt_id,
                        status=RunStatus.CANCELLED,
                    )
                except WPlusSopStoreError:
                    logger.info(
                        "W+ run settled concurrently while cancelling "
                        "session=%s run=%s",
                        sop_session_id,
                        active_attempt.run_id,
                    )
        if mutation.duplicate or not starts_run:
            return mutation

        if chat is None or run_id is None or attempt_id is None:
            raise WPlusOwnershipError(self.ownership.chat_id)
        try:
            await start_wplus_chat_turn(
                workspace=self.workspace,
                chat=chat,
                user_id=self.ownership.user_id,
                source_id=self.ownership.source_id,
                sop_session_id=sop_session_id,
                command=command,
                payload=runtime_payload,
                run_id=run_id,
                attempt_id=attempt_id,
                target_state=target_state.value,
                on_complete=lambda: self._on_agent_turn_complete(
                    sop_session_id=sop_session_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    command=command,
                ),
                before_start=lambda: self._assert_runtime_claim_active(
                    sop_session_id=sop_session_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                ),
            )
        except _WPlusRunClaimLostError:
            return StoreMutation(
                record=self._owned_record(sop_session_id),
                receipt=mutation.receipt,
            )
        except (RuntimeError, WPlusChatRunBusyError) as exc:
            self._record_runtime_failure(
                sop_session_id=sop_session_id,
                summary=str(exc),
                failed_operation=command,
                failed_run_id=run_id,
                failed_attempt_id=attempt_id,
            )
            raise WPlusRuntimeStartError(str(exc)) from exc
        return mutation

    def append_agent_event(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        event_key: str,
        trusted_sop_session_id: str | None = None,
        trusted_run_id: str | None = None,
        trusted_attempt_id: str | None = None,
    ) -> StoreMutation:
        trusted_values = (
            trusted_sop_session_id,
            trusted_run_id,
            trusted_attempt_id,
        )
        if any(trusted_values):
            if not all(trusted_values):
                raise WPlusCommandError(
                    "Incomplete trusted W+ run identity",
                )
            assert trusted_sop_session_id is not None
            assert trusted_run_id is not None
            assert trusted_attempt_id is not None
            record = self._owned_record(trusted_sop_session_id)
            if record.projection.current_run_id != trusted_run_id:
                raise WPlusCommandError(
                    "W+ event run does not match the current claimed run",
                )
            attempt = next(
                (
                    item
                    for item in record.runs
                    if item.run_id == trusted_run_id
                    and item.attempt_id == trusted_attempt_id
                ),
                None,
            )
            if attempt is None or attempt.status not in {
                RunStatus.CLAIMED,
                RunStatus.RUNNING,
            }:
                raise WPlusCommandError(
                    "W+ event attempt is not active",
                )
        else:
            record = self.get_active_session()
        if record is None:
            raise WPlusOwnershipError("No active W+ Session for this Chat")
        try:
            event_kind = EventKind(kind)
        except ValueError as exc:
            raise WPlusCommandError(f"Unsupported event kind: {kind}") from exc

        state = record.projection.state
        effective_state = (
            record.projection.resume_state
            if state is SessionState.PENDING_EXIT
            else state
        )

        stable_id = uuid5(
            NAMESPACE_URL,
            f"{record.projection.sop_session_id}:{event_key}",
        ).hex
        stable_event_id = f"evt_{stable_id}"
        existing_event = next(
            (
                event
                for event in record.events
                if event.event_id == stable_event_id
            ),
            None,
        )
        if existing_event is not None:
            candidate = StructuredInteractionEnvelope(
                event_id=stable_event_id,
                sop_session_id=record.projection.sop_session_id,
                chat_id=record.projection.chat_id,
                revision=existing_event.revision,
                round=existing_event.round,
                state_version=existing_event.state_version,
                kind=event_kind,
                payload=payload,
            )
            existing_payload = (
                existing_event.payload.model_dump(mode="json")
                if hasattr(existing_event.payload, "model_dump")
                else existing_event.payload
            )
            candidate_payload = (
                candidate.payload.model_dump(mode="json")
                if hasattr(candidate.payload, "model_dump")
                else candidate.payload
            )
            if (
                existing_event.kind is not event_kind
                or existing_payload != candidate_payload
            ):
                raise WPlusCommandError(
                    "event_key was already used for another W+ event",
                )
            if (
                effective_state is SessionState.GENERATING_QUESTIONS
                and event_kind is EventKind.QUESTION_BATCH
            ):
                historical_batch = QuestionBatchPayload.model_validate(
                    existing_payload,
                )
                candidate_batch = QuestionBatchPayload.model_validate(
                    candidate_payload,
                )
                current_stage_id = record.projection.current_stage_id
                if (
                    historical_batch.stage_id != current_stage_id
                    or candidate_batch.stage_id != current_stage_id
                ):
                    raise WPlusCommandError(
                        "question_batch stage_id="
                        f"{candidate_batch.stage_id} does not match "
                        f"current_stage_id={current_stage_id or 'missing'}",
                    )
            return StoreMutation(record=record, duplicate=True)

        allowed_states = _RUN_EVENT_STATES.get(event_kind)
        if (
            effective_state is None
            or allowed_states is None
            or effective_state not in allowed_states
        ):
            allowed_event_kinds = (
                sorted(
                    candidate_kind.value
                    for candidate_kind, candidate_states in (
                        _RUN_EVENT_STATES.items()
                    )
                    if effective_state in candidate_states
                )
                if effective_state is not None
                else []
            )
            allowed_event_detail = (
                "; allowed agent events: " + ", ".join(allowed_event_kinds)
                if allowed_event_kinds
                else ""
            )
            raise WPlusCommandError(
                f"{event_kind.value} is not allowed while "
                f"{state.value} is active{allowed_event_detail}",
            )

        target = effective_state
        changes: dict[str, Any] = {}
        if event_kind is EventKind.STAGE_PROPOSAL:
            target = SessionState.AWAITING_QUEUE_CONFIRMATION
            typed = StageProposalPayload.model_validate(payload)
            if any(
                stage.status is not StageStatus.PENDING
                for stage in typed.stages
            ):
                raise WPlusCommandError(
                    "stage_proposal stages must start as pending",
                )
            changes["stages"] = typed.stages
        elif event_kind is EventKind.QUESTION_BATCH:
            target = SessionState.AWAITING_ANSWER
            typed = QuestionBatchPayload.model_validate(payload)
            if typed.stage_id != record.projection.current_stage_id:
                raise WPlusCommandError(
                    f"question_batch stage_id={typed.stage_id} does not match "
                    "current_stage_id="
                    f"{record.projection.current_stage_id or 'missing'}",
                )
            changes.update(
                {
                    "current_question_batch": typed,
                    "current_stage_id": typed.stage_id,
                },
            )
        elif event_kind is EventKind.TRIAL_PLAN:
            target = SessionState.EXECUTING_TRIAL
            typed = TrialPlanPayload.model_validate(payload)
            if (
                trusted_run_id is not None
                and typed.run_id != trusted_run_id
            ):
                raise WPlusCommandError(
                    "trial_plan run_id does not match the trusted run",
                )
            changes["current_run_id"] = typed.run_id
        elif event_kind in {
            EventKind.TRIAL_EXECUTION_STARTED,
            EventKind.TRIAL_EXECUTION_PROGRESS,
        }:
            target = SessionState.EXECUTING_TRIAL
            event_model = StructuredInteractionEnvelope(
                event_id="evt_validation",
                sop_session_id=record.projection.sop_session_id,
                chat_id=record.projection.chat_id,
                revision=record.projection.revision,
                round=record.projection.round,
                state_version=record.projection.state_version + 1,
                kind=event_kind,
                payload=payload,
            )
            typed = event_model.payload
        elif event_kind is EventKind.TRIAL_EXECUTION_COMPLETED:
            target = SessionState.AWAITING_TRIAL_FEEDBACK
            typed = TrialExecutionCompletedPayload.model_validate(payload)
            if (
                trusted_run_id is not None
                and typed.run_id != trusted_run_id
            ):
                raise WPlusCommandError(
                    "trial result run_id does not match the trusted run",
                )
            changes.update(
                {
                    "trial_result_lists": typed.result_lists,
                    "confirmed_facts": typed.confirmed_facts,
                    "unknowns": typed.unknowns,
                },
            )
        elif event_kind is EventKind.TRIAL_EXECUTION_FAILED:
            target = SessionState.RECOVERABLE_FAILURE
            failure = TrialExecutionFailedPayload.model_validate(payload)
            if (
                trusted_run_id is not None
                and failure.run_id != trusted_run_id
            ):
                raise WPlusCommandError(
                    "trial failure run_id does not match the trusted run",
                )
            typed = failure
            changes["last_error"] = RecoverableFailurePayload(
                error_code=failure.error_code,
                summary=failure.summary,
                failed_operation="trial_execution",
                failed_run_id=failure.run_id,
            )
            changes["resume_state"] = effective_state
        elif event_kind is EventKind.SOP_RESULT:
            target = SessionState.FINALIZING_OUTPUTS
            typed = SopResultPayload.model_validate(payload)
            _validate_delivered_artifacts(
                workspace_dir=self.workspace.workspace_dir,
                result=typed.result,
            )
            changes["final_result"] = typed.result
        elif event_kind is EventKind.MEMORY_CANDIDATES:
            if record.projection.final_result is None:
                raise WPlusCommandError(
                    "memory_candidates requires a persisted final SOP result",
                )
            typed = MemoryCandidatesPayload.model_validate(payload)
            if any(
                candidate.status is not MemoryCandidateStatus.PENDING
                or candidate.legacy_read_only
                or candidate.write_receipt is not None
                or candidate.failure_reason is not None
                or candidate.target_scope is not None
                or candidate.target_file is not None
                for candidate in typed.candidates
            ):
                raise WPlusCommandError(
                    "Agent memory candidates must be pending, unwritten, and untargeted",
                )
            targeted_candidates = []
            for candidate in typed.candidates:
                if (
                    candidate.memory_type is None
                    or not isinstance(candidate.value, dict)
                    or not (candidate.evidence or "").strip()
                ):
                    raise WPlusCommandError(
                        "Memory candidates require type, object content, and evidence",
                    )
                try:
                    target_scope, target_file = resolve_memory_target(
                        candidate.memory_type,
                        user_scope=record.projection.memory_user_scope,
                    )
                except WPlusMemoryPolicyError as exc:
                    raise WPlusCommandError(str(exc)) from exc
                targeted_candidates.append(
                    candidate.model_copy(
                        update={
                            "target_scope": target_scope,
                            "target_file": target_file,
                        },
                    ),
                )
            typed = MemoryCandidatesPayload(candidates=targeted_candidates)
            changes["memory_candidates"] = targeted_candidates
            target = SessionState.OUTPUT_REVIEW
        elif event_kind is EventKind.MEMORY_WRITE_BATCH_RESULT:
            typed = MemoryWriteBatchResultPayload.model_validate(payload)
            candidates, target = _apply_memory_batch_results(
                record.projection,
                typed,
            )
            changes.update(
                {
                    "memory_candidates": candidates,
                    "active_memory_candidate_id": None,
                    "active_memory_candidate_ids": [],
                },
            )
        elif event_kind in {
            EventKind.MEMORY_WRITE_COMPLETED,
            EventKind.MEMORY_WRITE_FAILED,
        }:
            candidates = [
                candidate.model_copy(deep=True)
                for candidate in record.projection.memory_candidates
            ]
            active_id = record.projection.active_memory_candidate_id
            match_index = next(
                (
                    index
                    for index, candidate in enumerate(candidates)
                    if candidate.candidate_id == active_id
                ),
                -1,
            )
            if match_index < 0:
                raise WPlusCommandError(
                    "Memory write run has no server-bound candidate",
                )
            candidate = candidates[match_index]
            if candidate.status is not MemoryCandidateStatus.WRITING:
                raise WPlusCommandError("Memory candidate is not being written")
            if event_kind is EventKind.MEMORY_WRITE_COMPLETED:
                completed = MemoryWriteCompletedPayload.model_validate(payload)
                if (
                    completed.candidate_id != candidate.candidate_id
                    or completed.target_scope != candidate.target_scope
                    or completed.target_file != candidate.target_file
                ):
                    raise WPlusCommandError(
                        "Memory write receipt does not match approved candidate",
                    )
                typed = completed
                candidates[match_index] = candidate.model_copy(
                    update={
                        "status": MemoryCandidateStatus.APPROVED,
                        "failure_reason": None,
                        "write_receipt": MemoryWriteReceipt(
                            memory_id=(
                                f"wplus-sop/{record.projection.sop_session_id}/"
                                f"{candidate.candidate_id}"
                            ),
                            target_scope=completed.target_scope,
                            target_file=completed.target_file,
                            reused_existing=(completed.result == "duplicate"),
                            store_result=completed.result,
                        ),
                    },
                )
                unresolved = any(
                    item.status
                    in {
                        MemoryCandidateStatus.PENDING,
                        MemoryCandidateStatus.FAILED,
                    }
                    for item in candidates
                )
                target = (
                    SessionState.MEMORY_REVIEW
                    if unresolved
                    else SessionState.COMPLETED
                )
            else:
                failure = MemoryWriteFailedPayload.model_validate(payload)
                if failure.candidate_id != candidate.candidate_id:
                    raise WPlusCommandError(
                        "Memory write failure does not match approved candidate",
                    )
                typed = failure
                candidates[match_index] = candidate.model_copy(
                    update={
                        "status": MemoryCandidateStatus.FAILED,
                        "failure_reason": failure.summary[:500],
                        "write_receipt": None,
                    },
                )
                target = SessionState.MEMORY_REVIEW
            changes.update(
                {
                    "memory_candidates": candidates,
                    "active_memory_candidate_id": None,
                    "active_memory_candidate_ids": [],
                },
            )
        elif event_kind is EventKind.RECOVERABLE_FAILURE:
            target = SessionState.RECOVERABLE_FAILURE
            typed = RecoverableFailurePayload.model_validate(payload)
            if trusted_run_id is not None and typed.failed_run_id is None:
                typed = typed.model_copy(
                    update={"failed_run_id": trusted_run_id},
                )
            changes["last_error"] = typed
            changes["resume_state"] = effective_state
        else:
            event_model = StructuredInteractionEnvelope(
                event_id="evt_validation",
                sop_session_id=record.projection.sop_session_id,
                chat_id=record.projection.chat_id,
                revision=record.projection.revision,
                round=record.projection.round,
                state_version=record.projection.state_version + 1,
                kind=event_kind,
                payload=payload,
            )
            typed = event_model.payload

        if state is SessionState.PENDING_EXIT:
            if event_kind not in _PENDING_EXIT_BOUNDARIES:
                target = SessionState.PENDING_EXIT
            elif record.projection.pending_exit_action == "terminate":
                target = SessionState.TERMINATED
                changes.update(
                    {
                        "pending_exit_action": None,
                        "termination_summary": TerminationSummaryPayload(
                            summary=(
                                "用户请求彻底结束；后台运行已在安全事件边界停止。"
                            ),
                        ),
                    },
                )
            elif target is SessionState.COMPLETED:
                changes.update(
                    {
                        "pending_exit_action": None,
                        "resume_state": None,
                    },
                )
            else:
                safe_resume_state = target
                target = SessionState.PAUSED
                changes.update(
                    {
                        "pending_exit_action": None,
                        "resume_state": safe_resume_state,
                    },
                )

        event = self._event(
            record,
            event_kind,
            typed.model_dump(mode="json"),
            event_id=stable_event_id,
        )
        return self.store.commit_event(
            record.projection.sop_session_id,
            expected_state_version=record.projection.state_version,
            event=event,
            next_state=target,
            projection_changes=changes,
            outbox_item=self._outbox(event),
        )
