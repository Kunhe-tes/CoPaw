# -*- coding: utf-8 -*-
"""Typed protocol and persisted projection models for the W+ SOP workspace.

The browser consumes these structured objects directly.  Markdown is never a
source of truth for workflow state or interactive controls.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Literal, TypeAlias

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    """Base model used by the persisted protocol."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )


class SessionState(str, Enum):
    GENERATING_STAGE_PROPOSAL = "GeneratingStageProposal"
    AWAITING_QUEUE_CONFIRMATION = "AwaitingQueueConfirmation"
    GENERATING_QUESTIONS = "GeneratingQuestions"
    AWAITING_ANSWER = "AwaitingAnswer"
    GENERATING_TRIAL = "GeneratingTrial"
    EXECUTING_TRIAL = "ExecutingTrial"
    AWAITING_TRIAL_FEEDBACK = "AwaitingTrialFeedback"
    AWAITING_STAGE_CONFIRMATION = "AwaitingStageConfirmation"
    FINALIZING_OUTPUTS = "FinalizingOutputs"
    MEMORY_REVIEW = "MemoryReview"
    COMPLETED = "Completed"
    PENDING_EXIT = "PendingExit"
    PAUSED = "Paused"
    RECOVERABLE_FAILURE = "RecoverableFailure"
    TERMINATED = "Terminated"


class StageStatus(str, Enum):
    PENDING = "pending"
    CLARIFYING = "clarifying"
    READY_FOR_TRIAL = "ready_for_trial"
    TRIAL_RUNNING = "trial_running"
    FEEDBACK_REVIEW = "feedback_review"
    AWAITING_STAGE_CONFIRMATION = "awaiting_stage_confirmation"
    CONFIRMED = "confirmed"
    INVALIDATED = "invalidated"


class QuestionType(str, Enum):
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    FREE_TEXT = "free_text"


class EventKind(str, Enum):
    STAGE_PROPOSAL = "stage_proposal"
    STAGE_QUEUE_CONFIRMED = "stage_queue_confirmed"
    LIFECYCLE_PROGRESS = "lifecycle_progress"
    QUESTION_BATCH = "question_batch"
    ANSWER_ACCEPTED = "answer_accepted"
    TRIAL_PLAN = "trial_plan"
    TRIAL_EXECUTION_STARTED = "trial_execution_started"
    TRIAL_EXECUTION_PROGRESS = "trial_execution_progress"
    TRIAL_EXECUTION_COMPLETED = "trial_execution_completed"
    TRIAL_EXECUTION_FAILED = "trial_execution_failed"
    TRIAL_FEEDBACK_ACCEPTED = "trial_feedback_accepted"
    STAGE_CONFIRMATION_REQUIRED = "stage_confirmation_required"
    STAGE_CONFIRMED = "stage_confirmed"
    REVISION_APPLIED = "revision_applied"
    SOP_RESULT = "sop_result"
    MEMORY_CANDIDATES = "memory_candidates"
    SESSION_STATE_CHANGED = "session_state_changed"
    RECOVERABLE_FAILURE = "recoverable_failure"
    TERMINATION_SUMMARY = "termination_summary"


class RunStatus(str, Enum):
    CLAIMED = "claimed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EntryDetectionMode(str, Enum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"


class EntryProposalStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class MemoryCandidateStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class _IdentifiedModel(StrictModel):
    """Model with reusable stable-ID validation."""

    _id_fields: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def _validate_ids(self) -> "_IdentifiedModel":
        for field_name in self._id_fields:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty stable ID")
        return self


class OwnershipTuple(_IdentifiedModel):
    """Trusted ownership coordinates for every W+ read and write."""

    tenant_id: str
    source_id: str
    user_id: str
    agent_id: str
    chat_id: str
    logical_chat_session_id: str

    _id_fields = (
        "tenant_id",
        "source_id",
        "user_id",
        "agent_id",
        "chat_id",
        "logical_chat_session_id",
    )

    @property
    def active_chat_key(self) -> str:
        """Return a deterministic non-public key for active-session indexing."""

        return "\x1f".join(
            (
                self.tenant_id,
                self.source_id,
                self.user_id,
                self.agent_id,
                self.chat_id,
            ),
        )


class Stage(_IdentifiedModel):
    stage_id: str
    name: str
    description: str | None = None
    status: StageStatus = StageStatus.PENDING

    _id_fields = ("stage_id",)

    @field_validator("name")
    @classmethod
    def _non_empty_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("stage name must be non-empty")
        return value


class StageQueue(StrictModel):
    stages: list[Stage] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def _unique_stages(self) -> "StageQueue":
        ids = [stage.stage_id for stage in self.stages]
        normalized_names = [stage.name.casefold() for stage in self.stages]
        if len(ids) != len(set(ids)):
            raise ValueError("stage_id values must be unique")
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("stage names must be unique")
        return self


class QuestionOption(_IdentifiedModel):
    option_id: str
    label: str
    description: str | None = None

    _id_fields = ("option_id",)

    @field_validator("label")
    @classmethod
    def _non_empty_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("option label must be non-empty")
        return value


class Question(_IdentifiedModel):
    question_id: str
    prompt: str
    type: QuestionType
    required: bool = True
    options: list[QuestionOption] = Field(default_factory=list)
    help_text: str | None = None

    _id_fields = ("question_id",)

    @field_validator("prompt")
    @classmethod
    def _non_empty_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question prompt must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_options(self) -> "Question":
        ids = [option.option_id for option in self.options]
        if len(ids) != len(set(ids)):
            raise ValueError("option_id values must be unique within a question")
        if self.type is QuestionType.FREE_TEXT and self.options:
            raise ValueError("free_text questions cannot contain options")
        if self.type is not QuestionType.FREE_TEXT and not self.options:
            raise ValueError("select questions require at least one option")
        return self


class QuestionBatch(_IdentifiedModel):
    batch_id: str
    stage_id: str
    questions: list[Question] = Field(min_length=1, max_length=3)

    _id_fields = ("batch_id", "stage_id")

    @model_validator(mode="after")
    def _unique_questions(self) -> "QuestionBatch":
        ids = [question.question_id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question_id values must be unique within a batch")
        return self


class QuestionAnswer(_IdentifiedModel):
    question_id: str
    selected_option_ids: list[str] = Field(default_factory=list)
    text: str | None = None

    _id_fields = ("question_id",)

    @model_validator(mode="after")
    def _has_answer(self) -> "QuestionAnswer":
        if not self.selected_option_ids and not (self.text or "").strip():
            raise ValueError("an answer must contain a selection or text")
        if len(self.selected_option_ids) != len(set(self.selected_option_ids)):
            raise ValueError("selected option IDs must be unique")
        return self


class AnswerBatch(_IdentifiedModel):
    batch_id: str
    stage_id: str
    answers: list[QuestionAnswer] = Field(min_length=1, max_length=3)

    _id_fields = ("batch_id", "stage_id")

    @model_validator(mode="after")
    def _unique_answers(self) -> "AnswerBatch":
        ids = [answer.question_id for answer in self.answers]
        if len(ids) != len(set(ids)):
            raise ValueError("a question may only be answered once per batch")
        return self


class ResultColumn(_IdentifiedModel):
    field: str
    label: str
    type: Literal["string", "number", "boolean", "object", "array", "null"]

    _id_fields = ("field",)


_SENSITIVE_RESULT_KEY_SUBJECTS = frozenset(
    {
        "email",
        "phone",
        "telephone",
        "tel",
        "mobile",
        "cellphone",
        "msisdn",
        "mail",
        "customer",
        "customers",
        "cust",
        "client",
        "clients",
        "consumer",
        "buyer",
        "account",
        "accounts",
        "acct",
        "order",
        "orders",
        "purchase",
        "card",
        "balance",
        "transaction",
        "raw",
        "contact",
        "address",
        "id",
        "identifier",
        "token",
        "raw_response",
        "raw_customer_data",
    },
)
_SUMMARY_RESULT_KEY_TOKENS = frozenset(
    {
        "count",
        "counts",
        "num",
        "total",
        "totals",
        "sum",
        "average",
        "avg",
        "mean",
        "median",
        "minimum",
        "min",
        "maximum",
        "max",
        "rate",
        "ratio",
        "percent",
        "percentage",
        "distribution",
        "breakdown",
        "bucket",
        "buckets",
        "summary",
        "summaries",
        "stat",
        "stats",
        "metric",
        "metrics",
        "trend",
        "segment",
        "segments",
        "status",
        "statuses",
        "category",
        "categories",
        "type",
        "types",
        "region",
        "regions",
        "tier",
        "tiers",
        "group",
        "groups",
        "channel",
        "channels",
        "period",
        "periods",
        "date",
        "day",
        "week",
        "month",
        "quarter",
        "year",
        "revenue",
        "volume",
    },
)
_RESULT_KEY_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_RESULT_KEY_ASCII_TOKEN = re.compile(r"[a-z0-9]+")


def _normalized_result_key_tokens(key: str) -> tuple[str, ...]:
    expanded = _RESULT_KEY_CAMEL_BOUNDARY.sub("_", key.strip())
    return tuple(_RESULT_KEY_ASCII_TOKEN.findall(expanded.casefold()))


def _is_forbidden_result_key(key: str) -> bool:
    tokens = _normalized_result_key_tokens(key)
    if not tokens:
        return False
    collapsed = "".join(tokens)
    if any(token in _SUMMARY_RESULT_KEY_TOKENS for token in tokens):
        return False
    if collapsed in {
        "email",
        "emailaddress",
        "mailaddress",
        "phone",
        "phonenumber",
        "telephone",
        "mobile",
        "mobilenumber",
        "cellphone",
        "msisdn",
        "mail",
        "customer",
        "customers",
        "cust",
        "client",
        "clients",
        "consumer",
        "buyer",
        "account",
        "accounts",
        "acct",
        "order",
        "orders",
        "purchase",
        "balance",
        "rawresponse",
        "rawcustomerdata",
        "contact",
        "address",
        "id",
        "identifier",
        "token",
    }:
        return True
    return any(token in _SENSITIVE_RESULT_KEY_SUBJECTS for token in tokens)


_RESULT_EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}(?![\w.-])",
    re.IGNORECASE,
)
_RESULT_MAINLAND_MOBILE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?86[\s-]?)?1[3-9]\d{9}(?!\d)",
)
_RESULT_PHONE_CANDIDATE_PATTERN = re.compile(
    r"(?<!\w)\+?[\d(][\d\s().-]{6,}\d(?!\w)",
)
_RESULT_ISO_DATE_PATTERN = re.compile(
    r"^\d{4}-\d{1,2}-\d{1,2}$",
)
_RESULT_AREA_PHONE_PATTERN = re.compile(
    r"^\d{2,4}-\d{7,8}$",
)


def _contains_sensitive_contact_value(value: str) -> bool:
    if _RESULT_EMAIL_PATTERN.search(value):
        return True
    if _RESULT_MAINLAND_MOBILE_PATTERN.search(value):
        return True
    stripped = value.strip()
    if _RESULT_ISO_DATE_PATTERN.fullmatch(stripped):
        return False
    if _RESULT_AREA_PHONE_PATTERN.fullmatch(stripped):
        return True
    for match in _RESULT_PHONE_CANDIDATE_PATTERN.finditer(value):
        candidate = match.group(0).strip()
        if _RESULT_ISO_DATE_PATTERN.fullmatch(candidate):
            continue
        digits = re.sub(r"\D", "", candidate)
        if not 8 <= len(digits) <= 15:
            continue
        separators = sum(candidate.count(char) for char in " -.()")
        if candidate.startswith("+") or "(" in candidate or separators >= 2:
            return True
    return False


def _find_sensitive_result_value(value: JsonValue) -> str | None:
    if isinstance(value, str):
        return value if _contains_sensitive_contact_value(value) else None
    if isinstance(value, dict):
        for nested in value.values():
            found = _find_sensitive_result_value(nested)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_sensitive_result_value(nested)
            if found is not None:
                return found
    return None


def _find_forbidden_result_key(value: JsonValue) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if _is_forbidden_result_key(key):
                return key
            found = _find_forbidden_result_key(nested)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_forbidden_result_key(nested)
            if found is not None:
                return found
    return None


class ResultObjectList(_IdentifiedModel):
    """A typed object list whose nested row structure is never flattened."""

    list_id: str
    label: str
    columns: list[ResultColumn] = Field(default_factory=list)
    rows: list[dict[str, JsonValue]] = Field(default_factory=list)
    truncated: bool = False
    total_count: int | None = Field(default=None, ge=0)

    _id_fields = ("list_id",)

    @model_validator(mode="after")
    def _reject_raw_customer_payloads(self) -> "ResultObjectList":
        for column in self.columns:
            if _is_forbidden_result_key(column.field):
                raise ValueError(
                    "persisted result columns cannot contain raw field "
                    f"{column.field!r}",
                )
        forbidden = _find_forbidden_result_key(self.rows)
        if forbidden is not None:
            raise ValueError(
                f"persisted result rows cannot contain raw field {forbidden!r}",
            )
        sensitive_value = _find_sensitive_result_value(self.rows)
        if sensitive_value is not None:
            raise ValueError(
                "persisted result rows cannot contain a sensitive contact value",
            )
        return self


class TrialStep(_IdentifiedModel):
    step_id: str
    label: str
    capability_id: str
    capability_version: str | None = None

    _id_fields = ("step_id", "capability_id")


class MemoryCandidate(_IdentifiedModel):
    candidate_id: str
    summary: str
    value: JsonValue
    status: MemoryCandidateStatus = MemoryCandidateStatus.PENDING
    failure_reason: str | None = None

    _id_fields = ("candidate_id",)


class FinalSopResult(StrictModel):
    sop_spec: dict[str, JsonValue]
    readable_sop: str
    html: str
    example_result_html: str | None = None
    schema_validated: bool = True
    privacy_validated: bool = True

    @model_validator(mode="after")
    def _all_declared_results_valid(self) -> "FinalSopResult":
        if not self.schema_validated or not self.privacy_validated:
            raise ValueError("final SOP results must pass schema and privacy validation")
        return self


class StageProposalPayload(StageQueue):
    pass


class StageQueueConfirmedPayload(StageQueue):
    pass


class LifecycleProgressPayload(StrictModel):
    phase: str
    message: str
    run_id: str | None = None
    percent: float | None = Field(default=None, ge=0, le=100)


class QuestionBatchPayload(QuestionBatch):
    pass


class AnswerAcceptedPayload(AnswerBatch):
    pass


class TrialPlanPayload(StrictModel):
    run_id: str
    input_snapshot_id: str
    steps: list[TrialStep] = Field(min_length=1)
    authorization_summary: str | None = None


class TrialExecutionStartedPayload(StrictModel):
    run_id: str
    attempt_id: str
    started_at: datetime = Field(default_factory=utc_now)


class TrialExecutionProgressPayload(StrictModel):
    run_id: str
    step_id: str
    status: str
    summary: str | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)


class TrialExecutionCompletedPayload(StrictModel):
    run_id: str
    summary: str
    result_lists: list[ResultObjectList] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    schema_validated: bool = True
    completed_at: datetime = Field(default_factory=utc_now)


class TrialExecutionFailedPayload(StrictModel):
    run_id: str
    error_code: str
    summary: str
    failed_step_id: str | None = None
    retryable: bool = True


class TrialFeedbackAcceptedPayload(StrictModel):
    feedback: str
    prior_run_id: str
    rerun_id: str


class StageConfirmationRequiredPayload(StrictModel):
    stage_id: str
    summary: str


class StageConfirmedPayload(StrictModel):
    stage_id: str
    next_stage_id: str | None = None
    is_final_stage: bool = False


class RevisionAppliedPayload(StrictModel):
    revised_round: int = Field(ge=1)
    invalidated_event_ids: list[str] = Field(default_factory=list)
    reason: str


class SopResultPayload(StrictModel):
    result: FinalSopResult


class MemoryCandidatesPayload(StrictModel):
    candidates: list[MemoryCandidate] = Field(default_factory=list)


class SessionStateChangedPayload(StrictModel):
    previous_state: SessionState | None
    state: SessionState
    reason: str | None = None


class RecoverableFailurePayload(StrictModel):
    error_code: str
    summary: str
    failed_operation: str
    failed_run_id: str | None = None


class TerminationSummaryPayload(StrictModel):
    summary: str
    confirmed_facts: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    completed_stage_ids: list[str] = Field(default_factory=list)
    incomplete_stage_ids: list[str] = Field(default_factory=list)
    valid_sop: Literal[False] = False


EventPayload: TypeAlias = (
    StageProposalPayload
    | StageQueueConfirmedPayload
    | LifecycleProgressPayload
    | QuestionBatchPayload
    | AnswerAcceptedPayload
    | TrialPlanPayload
    | TrialExecutionStartedPayload
    | TrialExecutionProgressPayload
    | TrialExecutionCompletedPayload
    | TrialExecutionFailedPayload
    | TrialFeedbackAcceptedPayload
    | StageConfirmationRequiredPayload
    | StageConfirmedPayload
    | RevisionAppliedPayload
    | SopResultPayload
    | MemoryCandidatesPayload
    | SessionStateChangedPayload
    | RecoverableFailurePayload
    | TerminationSummaryPayload
)


_PAYLOAD_MODELS: dict[EventKind, type[StrictModel]] = {
    EventKind.STAGE_PROPOSAL: StageProposalPayload,
    EventKind.STAGE_QUEUE_CONFIRMED: StageQueueConfirmedPayload,
    EventKind.LIFECYCLE_PROGRESS: LifecycleProgressPayload,
    EventKind.QUESTION_BATCH: QuestionBatchPayload,
    EventKind.ANSWER_ACCEPTED: AnswerAcceptedPayload,
    EventKind.TRIAL_PLAN: TrialPlanPayload,
    EventKind.TRIAL_EXECUTION_STARTED: TrialExecutionStartedPayload,
    EventKind.TRIAL_EXECUTION_PROGRESS: TrialExecutionProgressPayload,
    EventKind.TRIAL_EXECUTION_COMPLETED: TrialExecutionCompletedPayload,
    EventKind.TRIAL_EXECUTION_FAILED: TrialExecutionFailedPayload,
    EventKind.TRIAL_FEEDBACK_ACCEPTED: TrialFeedbackAcceptedPayload,
    EventKind.STAGE_CONFIRMATION_REQUIRED: StageConfirmationRequiredPayload,
    EventKind.STAGE_CONFIRMED: StageConfirmedPayload,
    EventKind.REVISION_APPLIED: RevisionAppliedPayload,
    EventKind.SOP_RESULT: SopResultPayload,
    EventKind.MEMORY_CANDIDATES: MemoryCandidatesPayload,
    EventKind.SESSION_STATE_CHANGED: SessionStateChangedPayload,
    EventKind.RECOVERABLE_FAILURE: RecoverableFailurePayload,
    EventKind.TERMINATION_SUMMARY: TerminationSummaryPayload,
}


class StructuredInteractionEnvelope(_IdentifiedModel):
    object: Literal["structured_interaction"] = "structured_interaction"
    protocol_version: Literal[1] = 1
    interaction: Literal["wplus_sop"] = "wplus_sop"
    event_id: str
    sop_session_id: str = Field(
        validation_alias=AliasChoices("sop_session_id", "session_id"),
        serialization_alias="session_id",
    )
    chat_id: str
    revision: int = Field(ge=1)
    round: int = Field(ge=0)
    state_version: int = Field(ge=1)
    kind: EventKind
    payload: EventPayload
    created_at: datetime = Field(default_factory=utc_now)

    _id_fields = ("event_id", "sop_session_id", "chat_id")

    @property
    def session_id(self) -> str:
        """Protocol-compatible alias used in the ADR examples."""

        return self.sop_session_id

    @model_validator(mode="before")
    @classmethod
    def _parse_typed_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        raw_kind = value.get("kind")
        if raw_kind is None:
            return value
        try:
            kind = EventKind(raw_kind)
        except (TypeError, ValueError):
            return value
        expected_model = _PAYLOAD_MODELS[kind]
        payload = value.get("payload")
        if payload is not None and not isinstance(payload, expected_model):
            if isinstance(payload, BaseModel):
                raise ValueError(
                    f"payload for {kind.value} must be "
                    f"{expected_model.__name__}",
                )
            copied = dict(value)
            copied["payload"] = expected_model.model_validate(payload)
            return copied
        return value

    @model_validator(mode="after")
    def _payload_matches_kind(self) -> "StructuredInteractionEnvelope":
        expected_model = _PAYLOAD_MODELS[self.kind]
        if not isinstance(self.payload, expected_model):
            raise ValueError(
                f"payload for {self.kind.value} must be "
                f"{expected_model.__name__}",
            )
        return self


class CommandReceipt(_IdentifiedModel):
    command_request_id: str
    command: str
    sop_session_id: str | None
    resulting_state_version: int | None = Field(default=None, ge=1)
    starts_run: bool = False
    run_id: str | None = None
    attempt_id: str | None = None
    result: JsonValue = None
    created_at: datetime = Field(default_factory=utc_now)

    _id_fields = ("command_request_id",)

    @model_validator(mode="after")
    def _validate_run_identity(self) -> "CommandReceipt":
        if self.starts_run and (not self.run_id or not self.attempt_id):
            raise ValueError("a run-starting receipt requires run_id and attempt_id")
        return self


class RunAttempt(_IdentifiedModel):
    run_id: str
    attempt_id: str
    command_request_id: str
    command: str
    status: RunStatus
    retry_of_run_id: str | None = None
    rerun_of_run_id: str | None = None
    input_snapshot_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)

    _id_fields = ("run_id", "attempt_id", "command_request_id")

    @model_validator(mode="after")
    def _one_lineage_kind(self) -> "RunAttempt":
        if self.retry_of_run_id and self.rerun_of_run_id:
            raise ValueError("a run cannot be both a retry and a feedback rerun")
        return self


class ChatProjectionOutboxItem(_IdentifiedModel):
    projection_event_id: str
    sop_session_id: str
    chat_id: str
    event_id: str
    kind: str
    payload: JsonValue
    created_at: datetime = Field(default_factory=utc_now)
    acknowledged_at: datetime | None = None

    _id_fields = (
        "projection_event_id",
        "sop_session_id",
        "chat_id",
        "event_id",
    )

    @property
    def pending(self) -> bool:
        return self.acknowledged_at is None


class WPlusEntryProposal(_IdentifiedModel):
    """Persisted Chat preflight proposal; deliberately not a SOP Session."""

    proposal_id: str
    ownership: OwnershipTuple
    logical_chat_session_id: str
    original_request: JsonValue
    original_request_digest: str
    detection_mode: EntryDetectionMode
    status: EntryProposalStatus = EntryProposalStatus.PENDING
    suppression_token: str | None = None
    suppression_claim_id: str | None = None
    suppression_claimed_at: datetime | None = None
    suppression_consumed_at: datetime | None = None
    command_receipt: CommandReceipt | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    _id_fields = (
        "proposal_id",
        "logical_chat_session_id",
        "original_request_digest",
    )

    @model_validator(mode="after")
    def _validate_resolution(self) -> "WPlusEntryProposal":
        if self.logical_chat_session_id != self.ownership.logical_chat_session_id:
            raise ValueError(
                "proposal logical_chat_session_id must match ownership",
            )
        if self.status is EntryProposalStatus.PENDING:
            if (
                self.command_receipt is not None
                or self.suppression_token is not None
                or self.suppression_claim_id is not None
                or self.suppression_claimed_at is not None
                or self.suppression_consumed_at is not None
            ):
                raise ValueError("a pending proposal cannot contain a resolution")
        elif self.command_receipt is None:
            raise ValueError("a resolved proposal requires a command receipt")
        if (
            self.status is EntryProposalStatus.REJECTED
            and not self.suppression_token
        ):
            raise ValueError("a rejected proposal requires a suppression token")
        if (
            (
                self.suppression_claim_id is not None
                or self.suppression_claimed_at is not None
                or self.suppression_consumed_at is not None
            )
            and self.status is not EntryProposalStatus.REJECTED
        ):
            raise ValueError(
                "only a rejected proposal can claim its suppression token",
            )
        if (self.suppression_claim_id is None) != (
            self.suppression_claimed_at is None
        ):
            raise ValueError("suppression claim id and timestamp must coexist")
        if (
            self.status is EntryProposalStatus.CONFIRMED
            and (
                self.command_receipt is None
                or not self.command_receipt.sop_session_id
            )
        ):
            raise ValueError("a confirmed proposal requires a Session receipt")
        return self


class SessionProjection(_IdentifiedModel):
    """Authoritative current-state projection rebuilt from persisted events."""

    sop_session_id: str
    ownership: OwnershipTuple
    skill_snapshot_id: str
    state: SessionState
    state_version: int = Field(ge=1)
    revision: int = Field(default=1, ge=1)
    round: int = Field(default=0, ge=0)
    title: str
    stages: list[Stage] = Field(default_factory=list)
    current_stage_id: str | None = None
    current_question_batch: QuestionBatch | None = None
    answers: list[AnswerBatch] = Field(default_factory=list)
    invalidated_history: list[JsonValue] = Field(default_factory=list)
    confirmed_facts: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    current_run_id: str | None = None
    trial_result_lists: list[ResultObjectList] = Field(default_factory=list)
    trial_feedback: list[str] = Field(default_factory=list)
    final_result: FinalSopResult | None = None
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    resume_state: SessionState | None = None
    pending_exit_action: Literal["pause", "terminate"] | None = None
    last_error: RecoverableFailurePayload | None = None
    termination_summary: TerminationSummaryPayload | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    _id_fields = ("sop_session_id", "skill_snapshot_id")

    @model_validator(mode="after")
    def _validate_stage_references(self) -> "SessionProjection":
        stage_ids = [stage.stage_id for stage in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("projection stage IDs must be unique")
        if self.current_stage_id and self.current_stage_id not in stage_ids:
            raise ValueError("current_stage_id must reference the stage queue")
        if self.state is SessionState.PAUSED and self.resume_state is None:
            raise ValueError("a paused Session requires resume_state")
        return self

    @property
    def chat_id(self) -> str:
        return self.ownership.chat_id

    @property
    def logical_chat_session_id(self) -> str:
        return self.ownership.logical_chat_session_id

    @property
    def is_terminal(self) -> bool:
        return self.state in {
            SessionState.COMPLETED,
            SessionState.TERMINATED,
        }

    @property
    def holds_chat_slot(self) -> bool:
        return not self.is_terminal

    @property
    def locks_chat_input(self) -> bool:
        return self.state not in {
            SessionState.PAUSED,
            SessionState.COMPLETED,
            SessionState.TERMINATED,
        }


class SessionRecord(StrictModel):
    projection: SessionProjection
    events: list[StructuredInteractionEnvelope] = Field(default_factory=list)
    command_receipts: dict[str, CommandReceipt] = Field(default_factory=dict)
    runs: list[RunAttempt] = Field(default_factory=list)
    outbox: list[ChatProjectionOutboxItem] = Field(default_factory=list)


class WPlusSopStoreFile(StrictModel):
    schema_version: Literal[1] = 1
    entry_proposals: dict[str, WPlusEntryProposal] = Field(default_factory=dict)
    sessions: dict[str, SessionRecord] = Field(default_factory=dict)
    command_index: dict[str, CommandReceipt] = Field(default_factory=dict)


_MAIN_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.GENERATING_STAGE_PROPOSAL: frozenset(
        {SessionState.AWAITING_QUEUE_CONFIRMATION},
    ),
    SessionState.AWAITING_QUEUE_CONFIRMATION: frozenset(
        {SessionState.GENERATING_QUESTIONS},
    ),
    SessionState.GENERATING_QUESTIONS: frozenset(
        {SessionState.AWAITING_ANSWER},
    ),
    SessionState.AWAITING_ANSWER: frozenset({SessionState.GENERATING_TRIAL}),
    SessionState.GENERATING_TRIAL: frozenset({SessionState.EXECUTING_TRIAL}),
    SessionState.EXECUTING_TRIAL: frozenset(
        {SessionState.AWAITING_TRIAL_FEEDBACK},
    ),
    SessionState.AWAITING_TRIAL_FEEDBACK: frozenset(
        {
            SessionState.GENERATING_TRIAL,
            SessionState.AWAITING_STAGE_CONFIRMATION,
        },
    ),
    SessionState.AWAITING_STAGE_CONFIRMATION: frozenset(
        {
            SessionState.GENERATING_TRIAL,
            SessionState.GENERATING_QUESTIONS,
            SessionState.FINALIZING_OUTPUTS,
        },
    ),
    SessionState.FINALIZING_OUTPUTS: frozenset(
        {
            SessionState.MEMORY_REVIEW,
            SessionState.COMPLETED,
        },
    ),
    SessionState.MEMORY_REVIEW: frozenset({SessionState.COMPLETED}),
}

_GENERATING_STATES = frozenset(
    {
        SessionState.GENERATING_STAGE_PROPOSAL,
        SessionState.GENERATING_QUESTIONS,
        SessionState.GENERATING_TRIAL,
        SessionState.EXECUTING_TRIAL,
        SessionState.FINALIZING_OUTPUTS,
    },
)
_STABLE_WAITING_STATES = frozenset(
    {
        SessionState.AWAITING_QUEUE_CONFIRMATION,
        SessionState.AWAITING_ANSWER,
        SessionState.AWAITING_TRIAL_FEEDBACK,
        SessionState.AWAITING_STAGE_CONFIRMATION,
        SessionState.MEMORY_REVIEW,
        SessionState.RECOVERABLE_FAILURE,
    },
)
_RESUMABLE_STATES = frozenset(
    set(_GENERATING_STATES)
    | set(_STABLE_WAITING_STATES)
    | {SessionState.PENDING_EXIT},
)


def legal_next_states(state: SessionState) -> frozenset[SessionState]:
    """Return all structurally legal next states for ``state``."""

    states = set(_MAIN_TRANSITIONS.get(state, frozenset()))
    if state in _GENERATING_STATES:
        states.add(state)
        states.update(
            {
                SessionState.PENDING_EXIT,
                SessionState.RECOVERABLE_FAILURE,
                SessionState.TERMINATED,
            },
        )
    elif state in _STABLE_WAITING_STATES:
        states.update({SessionState.PAUSED, SessionState.TERMINATED})
        if state is SessionState.RECOVERABLE_FAILURE:
            states.update(_GENERATING_STATES)
    elif state is SessionState.PENDING_EXIT:
        states.update(
            {
                SessionState.PENDING_EXIT,
                SessionState.PAUSED,
                SessionState.COMPLETED,
                SessionState.TERMINATED,
            },
        )
    elif state is SessionState.PAUSED:
        states.update(_RESUMABLE_STATES)
        states.add(SessionState.TERMINATED)
    return frozenset(states)


def assert_legal_transition(
    current: SessionState,
    target: SessionState,
) -> None:
    """Raise when a state transition violates the server-owned state machine."""

    if target not in legal_next_states(current):
        raise ValueError(
            "Illegal W+ SOP state transition: "
            f"{current.value} -> {target.value}",
        )


def validate_envelope(value: Any) -> StructuredInteractionEnvelope:
    """Validate untrusted tool or persisted data as a typed envelope."""

    try:
        return StructuredInteractionEnvelope.model_validate(value)
    except ValidationError:
        raise
