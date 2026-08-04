# -*- coding: utf-8 -*-
"""Pure, versioned state for recoverable Chat Checkpoints.

The model is deliberately independent from AgentScope and ReMe.  Persistence,
prompt assembly, and asynchronous candidate scheduling can therefore share one
validated representation without turning Markdown into the source of truth.
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Literal, Mapping, Sequence, TypeAlias

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
ProgressBucket: TypeAlias = Literal["done", "in_progress", "blocked"]
Confidence: TypeAlias = Literal["verified", "degraded"]

CHECKPOINT_SCHEMA_VERSION = 1
_PROGRESS_BUCKETS: tuple[ProgressBucket, ...] = (
    "done",
    "in_progress",
    "blocked",
)
_RAW_TOOL_OUTPUT_KEY = "raw_tool_output"
_TOOL_RESULT_CONTENT_KEYS = frozenset(
    {
        "body",
        "content",
        "output",
        "response",
        "result",
        "stderr",
        "stdout",
        "text",
        "tool_output",
    },
)
_SAFE_EVENT_FACT_KEYS = frozenset(
    {
        "artifact_ref",
        "artifact_refs",
        "boundary_id",
        "checkpoint_id",
        "command",
        "error_type",
        "exit_code",
        "message_id",
        "reason",
        "role",
        "source_revision",
        "status",
        "task_id",
        "token_count",
        "tool_name",
    },
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _as_tuple(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(str(value) for value in values)


def _contains_raw_tool_output(value: Any) -> bool:
    if isinstance(value, Mapping):
        return _RAW_TOOL_OUTPUT_KEY in value or any(
            _contains_raw_tool_output(item) for item in value.values()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_raw_tool_output(item) for item in value)
    return False


def _contains_tool_result_content(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalised_key = str(key).lower()
            if (
                normalised_key in _TOOL_RESULT_CONTENT_KEYS
                or normalised_key.endswith("_output")
                or normalised_key not in _SAFE_EVENT_FACT_KEYS
            ):
                return True
            if _contains_tool_result_content(item):
                return True
    if isinstance(value, (list, tuple)):
        return any(_contains_tool_result_content(item) for item in value)
    return False


def _normalise_json(value: Any) -> JSONValue:
    if isinstance(value, float) and not math.isfinite(value):
        raise TypeError("Checkpoint facts must use finite JSON numbers")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _normalise_json(item)
            for key, item in sorted(
                value.items(),
                key=lambda item: str(item[0]),
            )
        }
    if isinstance(value, (list, tuple)):
        return [_normalise_json(item) for item in value]
    raise TypeError(
        f"Checkpoint facts must be JSON values, got {type(value)!r}",
    )


def _freeze_json(value: JSONValue) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()},
        )
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> JSONValue:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return _normalise_json(value)


def _valid_ref(value: str) -> bool:
    prefix, separator, suffix = value.partition(":")
    return bool(prefix and separator and suffix)


@dataclass(frozen=True)
class EvidenceItem:
    """One rendered claim and the durable references that support it."""

    text: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskState:
    """The one current task represented by a checkpoint."""

    id: str | None = None
    title: str | None = None
    status: Literal["empty", "in_progress", "completed"] = "empty"
    goal: tuple[EvidenceItem, ...] = ()
    acceptance_criteria: tuple[EvidenceItem, ...] = ()


@dataclass(frozen=True)
class ProgressItem:
    """A completed, active, or blocked unit of work."""

    text: str
    status: ProgressBucket
    evidence_refs: tuple[str, ...] = ()

    def with_status(self, status: ProgressBucket) -> "ProgressItem":
        return replace(self, status=status)


@dataclass(frozen=True)
class ProgressState:
    """Progress grouped for the stable ReMe Markdown projection."""

    done: tuple[ProgressItem, ...] = ()
    in_progress: tuple[ProgressItem, ...] = ()
    blocked: tuple[ProgressItem, ...] = ()

    def items(self, bucket: ProgressBucket) -> tuple[ProgressItem, ...]:
        return getattr(self, bucket)


@dataclass(frozen=True)
class Decision:
    """A task decision with its rationale and evidence."""

    text: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class NextStep:
    """A concrete next action, optionally supported by prior evidence."""

    text: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompletedTask:
    """Compact historical index entry for a closed task in the same Chat."""

    id: str
    title: str
    completed_at: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckpointEvent:
    """An append-only deterministic event not yet merged into a record."""

    id: str
    sequence: int
    epoch: int
    occurred_at: str
    type: str
    facts: Mapping[str, Any]
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        normalised_facts = _normalise_json(dict(self.facts))
        if not isinstance(normalised_facts, dict):
            raise TypeError("Checkpoint event facts must be a JSON object")
        object.__setattr__(self, "facts", _freeze_json(normalised_facts))
        object.__setattr__(self, "source_refs", _as_tuple(self.source_refs))

    @classmethod
    def new(
        cls,
        *,
        sequence: int,
        epoch: int,
        type: str,
        facts: Mapping[str, Any] | None = None,
        source_refs: Sequence[str] = (),
        occurred_at: str | None = None,
    ) -> "CheckpointEvent":
        return cls(
            id=_new_id(),
            sequence=sequence,
            epoch=epoch,
            occurred_at=occurred_at or _utc_now(),
            type=type,
            facts=dict(facts or {}),
            source_refs=_as_tuple(source_refs),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "id": self.id,
            "sequence": self.sequence,
            "epoch": self.epoch,
            "occurred_at": self.occurred_at,
            "type": self.type,
            "facts": _thaw_json(self.facts),
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True)
class CheckpointRecord:
    """Versioned source of truth for a Chat-scoped recoverable checkpoint."""

    schema_version: int
    checkpoint_id: str
    chat_id: str
    epoch: int
    revision: int
    updated_at: str
    confidence: Confidence
    current_task: TaskState
    constraints_and_preferences: tuple[EvidenceItem, ...]
    progress: ProgressState
    key_decisions: tuple[Decision, ...]
    next_steps: tuple[NextStep, ...]
    critical_context: tuple[EvidenceItem, ...]
    risks_and_unverified: tuple[EvidenceItem, ...]
    completed_task_index: tuple[CompletedTask, ...]
    archived_through: str | None
    source_revision: int
    applied_event_sequence: int

    @classmethod
    def new(cls, *, chat_id: str, epoch: int) -> "CheckpointRecord":
        return cls(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            checkpoint_id=_new_id(),
            chat_id=chat_id,
            epoch=epoch,
            revision=0,
            updated_at=_utc_now(),
            confidence="verified",
            current_task=TaskState(),
            constraints_and_preferences=(),
            progress=ProgressState(),
            key_decisions=(),
            next_steps=(),
            critical_context=(),
            risks_and_unverified=(),
            completed_task_index=(),
            archived_through=None,
            source_revision=0,
            applied_event_sequence=0,
        )

    def with_current_task(
        self,
        title: str,
        acceptance_criteria: Sequence[str],
        *,
        evidence_refs: Sequence[str],
    ) -> "CheckpointRecord":
        refs = _as_tuple(evidence_refs)
        task = TaskState(
            id=_new_id(),
            title=title,
            status="in_progress",
            goal=(EvidenceItem(title, refs),),
            acceptance_criteria=tuple(
                EvidenceItem(criterion, refs)
                for criterion in acceptance_criteria
            ),
        )
        return replace(self, current_task=task, updated_at=_utc_now())

    def with_progress(
        self,
        bucket: ProgressBucket,
        text: str,
        evidence_refs: Sequence[str],
    ) -> "CheckpointRecord":
        if bucket not in _PROGRESS_BUCKETS:
            raise ValueError(f"Unsupported progress bucket: {bucket}")
        item = ProgressItem(text, bucket, _as_tuple(evidence_refs))
        if bucket == "done":
            progress = replace(
                self.progress,
                done=(*self.progress.done, item),
            )
        elif bucket == "in_progress":
            progress = replace(
                self.progress,
                in_progress=(*self.progress.in_progress, item),
            )
        else:
            progress = replace(
                self.progress,
                blocked=(*self.progress.blocked, item),
            )
        return replace(self, progress=progress, updated_at=_utc_now())

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-ready representation with stable field names."""
        data = asdict(self)
        return _normalise_json(data)  # type: ignore[return-value]

    def to_json(self) -> str:
        """Serialize the source of truth deterministically for durable writes."""
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class PrecompactionCandidate:
    """A validated but inactive record derived from a stable Chat snapshot."""

    id: str
    chat_id: str
    epoch: int
    base_revision: int
    applied_event_sequence: int
    record: CheckpointRecord
    created_at: str

    @classmethod
    def new(
        cls,
        *,
        record: CheckpointRecord,
        base_revision: int,
        applied_event_sequence: int,
    ) -> "PrecompactionCandidate":
        return cls(
            id=_new_id(),
            chat_id=record.chat_id,
            epoch=record.epoch,
            base_revision=base_revision,
            applied_event_sequence=applied_event_sequence,
            record=record,
            created_at=_utc_now(),
        )


@dataclass(frozen=True)
class InteractionUnit:
    """An indivisible interaction (including its paired tool transaction)."""

    id: str
    token_count: int
    message_ids: tuple[str, ...]


@dataclass(frozen=True)
class CheckpointValidationResult:
    """Validation outcome retained separately from the immutable record."""

    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _validate_refs(
    refs: Sequence[str],
    field_name: str,
    errors: list[str],
) -> None:
    if not refs:
        errors.append(f"{field_name} requires evidence")
        return
    if any(not _valid_ref(ref) for ref in refs):
        errors.append(f"{field_name} contains an invalid evidence reference")


def _validate_evidence_items(
    items: Sequence[EvidenceItem],
    field_name: str,
    errors: list[str],
) -> None:
    for index, item in enumerate(items):
        _validate_refs(item.evidence_refs, f"{field_name}[{index}]", errors)


def validate_checkpoint_record(
    record: CheckpointRecord,
    events: Sequence[CheckpointEvent] = (),
) -> CheckpointValidationResult:
    """Validate source-of-truth invariants without mutating checkpoint state."""
    errors: list[str] = []
    if record.schema_version != CHECKPOINT_SCHEMA_VERSION:
        errors.append("checkpoint schema version is unsupported")
    if not record.chat_id:
        errors.append("checkpoint chat_id must not be empty")
    if record.epoch < 1:
        errors.append("checkpoint epoch must be positive")
    if record.revision < 0:
        errors.append("checkpoint revision must not be negative")
    if record.applied_event_sequence < 0:
        errors.append("checkpoint applied_event_sequence must not be negative")

    task = record.current_task
    if task.status == "empty" and (task.id or task.title or task.goal):
        errors.append("empty current_task must not contain task state")
    if task.status != "empty":
        if not task.id or not task.title:
            errors.append("current_task requires id and title")
        _validate_evidence_items(task.goal, "current_task.goal", errors)
        _validate_evidence_items(
            task.acceptance_criteria,
            "current_task.acceptance_criteria",
            errors,
        )

    _validate_evidence_items(
        record.constraints_and_preferences,
        "constraints_and_preferences",
        errors,
    )
    _validate_evidence_items(
        record.critical_context,
        "critical_context",
        errors,
    )
    _validate_evidence_items(
        record.risks_and_unverified,
        "risks_and_unverified",
        errors,
    )
    for index, item in enumerate(record.key_decisions):
        _validate_refs(item.evidence_refs, f"key_decisions[{index}]", errors)
    for index, item in enumerate(record.next_steps):
        _validate_refs(item.evidence_refs, f"next_steps[{index}]", errors)
    for index, item in enumerate(record.completed_task_index):
        _validate_refs(
            item.evidence_refs,
            f"completed_task_index[{index}]",
            errors,
        )
    for bucket in _PROGRESS_BUCKETS:
        for index, item in enumerate(record.progress.items(bucket)):
            if item.status != bucket:
                errors.append(f"progress.{bucket}[{index}] has wrong status")
            _validate_refs(
                item.evidence_refs,
                f"progress.{bucket}[{index}]",
                errors,
            )

    previous_sequence = record.applied_event_sequence
    for index, event in enumerate(events):
        if event.epoch != record.epoch:
            errors.append(f"event[{index}] epoch differs from checkpoint")
        if event.sequence <= previous_sequence:
            errors.append(f"event[{index}] sequence is not increasing")
        previous_sequence = event.sequence
        if not event.type:
            errors.append(f"event[{index}] type must not be empty")
        _validate_refs(
            event.source_refs,
            f"event[{index}].source_refs",
            errors,
        )
        if _contains_raw_tool_output(event.facts):
            errors.append(
                f"event[{index}].facts must not contain raw_tool_output",
            )
        elif _contains_tool_result_content(event.facts):
            errors.append(
                f"event[{index}].facts must not contain tool result content",
            )
        try:
            _normalise_json(event.facts)
        except TypeError:
            errors.append(
                f"event[{index}].facts must contain strict JSON values",
            )

    return CheckpointValidationResult(errors)


def validate_checkpoint_update(
    previous: CheckpointRecord,
    candidate: CheckpointRecord,
) -> CheckpointValidationResult:
    """Reject semantic updates that invent completed work without evidence."""
    errors = validate_checkpoint_record(candidate).errors.copy()
    if previous.chat_id != candidate.chat_id:
        errors.append("checkpoint update chat_id must not change")
    if previous.epoch != candidate.epoch:
        errors.append("checkpoint update epoch must not change")
    if candidate.applied_event_sequence < previous.applied_event_sequence:
        errors.append("checkpoint update cannot move event sequence backwards")

    old_progress = {
        item.text: item
        for bucket in _PROGRESS_BUCKETS
        for item in previous.progress.items(bucket)
    }
    for item in candidate.progress.done:
        old_item = old_progress.get(item.text)
        new_evidence = set(item.evidence_refs) - set(
            old_item.evidence_refs if old_item else (),
        )
        if (
            old_item is None or old_item.status != "done"
        ) and not new_evidence:
            errors.append("unsupported progress transition")
    return CheckpointValidationResult(errors)


def validate_precompaction_candidate(
    candidate: PrecompactionCandidate,
    active_record: CheckpointRecord,
    current_event_sequence: int,
) -> CheckpointValidationResult:
    """Ensure a pending candidate is safe to install at a later threshold."""
    errors = validate_checkpoint_update(
        active_record,
        candidate.record,
    ).errors.copy()
    if candidate.chat_id != active_record.chat_id:
        errors.append("candidate chat_id differs from active checkpoint")
    if candidate.epoch != active_record.epoch:
        errors.append("candidate epoch differs from active checkpoint")
    if candidate.base_revision != active_record.revision:
        errors.append("candidate base revision is stale")
    if candidate.record.source_revision != candidate.base_revision:
        errors.append(
            "candidate record source revision must match base revision",
        )
    if candidate.record.revision != candidate.base_revision + 1:
        errors.append("candidate record revision must follow base revision")
    if (
        candidate.record.applied_event_sequence
        != candidate.applied_event_sequence
    ):
        errors.append("candidate record event sequence must match wrapper")
    if candidate.applied_event_sequence > current_event_sequence:
        errors.append("candidate event sequence is ahead of the journal")
    if candidate.applied_event_sequence < active_record.applied_event_sequence:
        errors.append("candidate event sequence precedes active checkpoint")
    return CheckpointValidationResult(errors)


def _render_items(
    items: Sequence[EvidenceItem | Decision | NextStep],
) -> list[str]:
    return [f"- {item.text}" for item in items]


def render_recent_event_delta(
    events: Sequence[CheckpointEvent],
    *,
    max_items: int = 5,
    max_characters: int = 1200,
) -> str:
    """Render only a small, deterministic projection of unmerged events."""
    if max_items <= 0 or max_characters <= 0:
        return ""
    lines: list[str] = []
    used = 0
    for event in events[-max_items:]:
        refs = ", ".join(event.source_refs)
        facts = json.dumps(
            _thaw_json(event.facts),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        line = f"- [{event.type}] {facts} ({refs})"
        if used + len(line) > max_characters:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)


def select_whole_interaction_units(
    units: Sequence[InteractionUnit],
    *,
    token_budget: int,
) -> tuple[InteractionUnit, ...]:
    """Select the oldest fitting prefix without splitting an interaction."""
    if token_budget < 0:
        raise ValueError("token_budget must not be negative")
    selected: list[InteractionUnit] = []
    used = 0
    for unit in units:
        if unit.token_count <= 0:
            raise ValueError("interaction unit token_count must be positive")
        if used + unit.token_count > token_budget:
            break
        selected.append(unit)
        used += unit.token_count
    return tuple(selected)


def render_checkpoint_projection(
    record: CheckpointRecord,
    recent_events: Sequence[CheckpointEvent] = (),
    *,
    max_recent_event_items: int = 5,
    max_recent_event_characters: int = 1200,
) -> str:
    """Project structured checkpoint state into ReMe's stable Markdown shape."""
    task = record.current_task
    goal_lines = (
        _render_items(task.goal) if task.goal else ["- 未设置当前任务"]
    )
    if task.acceptance_criteria:
        goal_lines.extend(
            ["", "验收标准：", *_render_items(task.acceptance_criteria)],
        )

    progress_lines: list[str] = []
    progress_sections: tuple[tuple[ProgressBucket, str], ...] = (
        ("done", "已完成"),
        ("in_progress", "进行中"),
        ("blocked", "阻塞"),
    )
    for bucket, title in progress_sections:
        items = record.progress.items(bucket)
        progress_lines.append(f"### {title}")
        progress_lines.extend(
            [f"- {item.text}" for item in items] or ["- 无"],
        )

    sections = [
        "# Chat Checkpoint",
        "## 目标",
        *goal_lines,
        "",
        "## 约束和偏好",
        *(_render_items(record.constraints_and_preferences) or ["- 无"]),
        "",
        "## 进展",
        *progress_lines,
        "",
        "## 关键决策",
        *(_render_items(record.key_decisions) or ["- 无"]),
        "",
        "## 下一步",
        *(_render_items(record.next_steps) or ["- 无"]),
        "",
        "## 关键上下文",
        *(_render_items(record.critical_context) or ["- 无"]),
    ]
    delta = render_recent_event_delta(
        recent_events,
        max_items=max_recent_event_items,
        max_characters=max_recent_event_characters,
    )
    if delta:
        sections.extend(["", "## Recent Event Delta", delta])
    return "\n".join(sections)
