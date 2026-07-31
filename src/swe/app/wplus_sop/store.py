# -*- coding: utf-8 -*-
"""Atomic single-process JSON store for W+ SOP sessions."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

from .models import (
    ChatProjectionOutboxItem,
    CommandReceipt,
    EntryProposalStatus,
    OwnershipTuple,
    RunAttempt,
    RunStatus,
    SessionProjection,
    SessionRecord,
    SessionState,
    SessionStateChangedPayload,
    StructuredInteractionEnvelope,
    WPlusEntryProposal,
    WPlusSopStoreFile,
    assert_legal_transition,
)


class WPlusSopStoreError(RuntimeError):
    """Base store failure."""


class ActiveSessionExistsError(WPlusSopStoreError):
    """The owning Chat already holds an active or paused Session."""


class StaleStateVersionError(WPlusSopStoreError):
    """The caller attempted to mutate a stale projection."""


class EntryProposalConflictError(WPlusSopStoreError):
    """An entry proposal was resolved by a different command."""


class SessionNotFoundError(WPlusSopStoreError):
    """The requested Session does not exist."""


@dataclass(frozen=True)
class StoreMutation:
    """Result returned by idempotent store mutations."""

    record: SessionRecord
    receipt: CommandReceipt | None = None
    duplicate: bool = False

    @property
    def projection(self) -> SessionProjection:
        """Compatibility shortcut for callers interested in current state."""
        return self.record.projection


_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[Path, threading.RLock] = {}


def _path_lock(path: Path) -> threading.RLock:
    resolved = path.expanduser().resolve()
    with _LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(resolved, threading.RLock())


_T = TypeVar("_T")


def _clone(value: _T) -> _T:
    if hasattr(value, "model_copy"):
        return value.model_copy(deep=True)
    return value


def _proposal_ids_for_command(
    data: WPlusSopStoreFile,
    command_request_id: str,
) -> list[str]:
    return [
        proposal_id
        for proposal_id, proposal in data.entry_proposals.items()
        if (
            proposal.command_receipt is not None
            and proposal.command_receipt.command_request_id
            == command_request_id
        )
    ]


class WPlusSopStore:
    """Persist the W+ event log, projection, receipts, and Chat outbox.

    The lock is intentionally process-local. V1 enables writes only in the
    single-process desktop runtime; a multi-worker deployment needs a database
    implementation of this interface.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path).expanduser().resolve()
        self._lock = _path_lock(self.path)

    def _load_unlocked(self) -> WPlusSopStoreFile:
        if not self.path.exists():
            return WPlusSopStoreFile()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return WPlusSopStoreFile.model_validate(data)

    def _save_unlocked(self, data: WPlusSopStoreFile) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(f"{self.path.name}.{uuid4().hex}.tmp")
        payload = json.dumps(
            data.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.path)

    @staticmethod
    def _initial_record(projection: SessionProjection) -> SessionRecord:
        event = StructuredInteractionEnvelope(
            event_id=f"evt_session_created_{projection.sop_session_id}",
            sop_session_id=projection.sop_session_id,
            chat_id=projection.chat_id,
            revision=projection.revision,
            round=projection.round,
            state_version=projection.state_version,
            kind="session_state_changed",
            payload=SessionStateChangedPayload(
                previous_state=None,
                state=projection.state,
                reason="entry_confirmed",
            ),
        )
        return SessionRecord(projection=projection, events=[event])

    @staticmethod
    def _find_duplicate(
        data: WPlusSopStoreFile,
        receipt: CommandReceipt | None,
        *,
        expected_ownership: OwnershipTuple | None = None,
        expected_sop_session_id: str | None = None,
        expected_proposal_id: str | None = None,
    ) -> StoreMutation | None:
        if receipt is None:
            return None
        existing = data.command_index.get(receipt.command_request_id)
        if existing is None:
            return None
        if existing.command != receipt.command:
            raise WPlusSopStoreError(
                "command_request_id is already used by another command",
            )
        session_id = existing.sop_session_id
        if not session_id or session_id not in data.sessions:
            raise WPlusSopStoreError(
                "idempotent Session command has no persisted Session",
            )
        record = data.sessions[session_id]
        if expected_proposal_id is not None:
            proposal = data.entry_proposals.get(expected_proposal_id)
            proposal_receipt = (
                proposal.command_receipt if proposal is not None else None
            )
            if (
                _proposal_ids_for_command(
                    data,
                    receipt.command_request_id,
                )
                != [expected_proposal_id]
                or
                proposal is None
                or proposal_receipt is None
                or proposal_receipt.command_request_id
                != receipt.command_request_id
                or proposal_receipt.command != receipt.command
                or proposal_receipt.sop_session_id != session_id
            ):
                raise WPlusSopStoreError(
                    "command_request_id belongs to another proposal scope",
                )
            if expected_ownership is None:
                expected_ownership = proposal.ownership
        elif (
            expected_sop_session_id is not None
            and session_id != expected_sop_session_id
        ):
            raise WPlusSopStoreError(
                "command_request_id belongs to another Session scope",
            )
        if (
            expected_ownership is not None
            and record.projection.ownership != expected_ownership
        ):
            raise WPlusSopStoreError(
                "command_request_id belongs to another ownership scope",
            )
        return StoreMutation(
            record=_clone(record),
            receipt=_clone(existing),
            duplicate=True,
        )

    @staticmethod
    def _assert_no_active_session(
        data: WPlusSopStoreFile,
        projection: SessionProjection,
    ) -> None:
        target_key = projection.ownership.active_chat_key
        for record in data.sessions.values():
            current = record.projection
            if (
                current.ownership.active_chat_key == target_key
                and current.holds_chat_slot
            ):
                raise ActiveSessionExistsError(
                    "The owning Chat already has an active or paused W+ Session",
                )

    def create_entry_proposal(
        self,
        proposal: WPlusEntryProposal,
    ) -> WPlusEntryProposal:
        with self._lock:
            data = self._load_unlocked()
            existing = data.entry_proposals.get(proposal.proposal_id)
            if existing is not None:
                return _clone(existing)
            data.entry_proposals[proposal.proposal_id] = proposal
            self._save_unlocked(data)
            return _clone(proposal)

    def get_entry_proposal(
        self,
        proposal_id: str,
    ) -> WPlusEntryProposal | None:
        with self._lock:
            proposal = self._load_unlocked().entry_proposals.get(proposal_id)
            return _clone(proposal) if proposal is not None else None

    def resolve_entry_proposal(
        self,
        proposal_id: str,
        *,
        status: EntryProposalStatus,
        receipt: CommandReceipt,
        suppression_token: str | None = None,
    ) -> WPlusEntryProposal:
        with self._lock:
            data = self._load_unlocked()
            proposal = data.entry_proposals.get(proposal_id)
            if proposal is None:
                raise EntryProposalConflictError("Entry proposal not found")
            existing = data.command_index.get(receipt.command_request_id)
            if existing is not None:
                proposal_receipt = proposal.command_receipt
                if (
                    _proposal_ids_for_command(
                        data,
                        receipt.command_request_id,
                    )
                    == [proposal_id]
                    and
                    proposal.status is status
                    and proposal_receipt is not None
                    and proposal_receipt.command_request_id
                    == receipt.command_request_id
                    and proposal_receipt.command == receipt.command
                    and existing.command == receipt.command
                    and existing.sop_session_id
                    == proposal_receipt.sop_session_id
                ):
                    return _clone(proposal)
                raise WPlusSopStoreError(
                    "command_request_id belongs to another proposal scope",
                )
            if proposal.status is not EntryProposalStatus.PENDING:
                raise EntryProposalConflictError(
                    "Entry proposal is already resolved",
                )
            if receipt.sop_session_id is not None:
                raise WPlusSopStoreError(
                    "proposal rejection receipt cannot reference a Session",
                )
            updated = proposal.model_copy(
                update={
                    "status": status,
                    "command_receipt": receipt,
                    "suppression_token": suppression_token,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            updated = WPlusEntryProposal.model_validate(updated)
            data.entry_proposals[proposal_id] = updated
            data.command_index[receipt.command_request_id] = receipt
            self._save_unlocked(data)
            return _clone(updated)

    def consume_suppression(
        self,
        proposal_id: str,
        *,
        claim_id: str,
        suppression_token: str,
        original_request_digest: str,
        ownership: OwnershipTuple,
    ) -> bool:
        """Atomically consume a rejected proposal's one-shot replay token."""

        with self._lock:
            data = self._load_unlocked()
            proposal = data.entry_proposals.get(proposal_id)
            if (
                proposal is not None
                and proposal.suppression_consumed_at is not None
            ):
                return False
            if (
                proposal is None
                or proposal.ownership != ownership
                or proposal.status is not EntryProposalStatus.REJECTED
                or proposal.suppression_claim_id != claim_id
                or proposal.suppression_token != suppression_token
                or proposal.original_request_digest != original_request_digest
            ):
                return False
            updated = proposal.model_copy(
                update={
                    "suppression_consumed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            data.entry_proposals[proposal_id] = WPlusEntryProposal.model_validate(
                updated,
            )
            self._save_unlocked(data)
            return True

    def claim_suppression(
        self,
        proposal_id: str,
        *,
        suppression_token: str,
        original_request_digest: str,
        ownership: OwnershipTuple,
    ) -> str | None:
        """Persist a replay claim before reserving the owning Chat run."""

        with self._lock:
            data = self._load_unlocked()
            proposal = data.entry_proposals.get(proposal_id)
            if (
                proposal is None
                or proposal.ownership != ownership
                or proposal.status is not EntryProposalStatus.REJECTED
                or proposal.suppression_token != suppression_token
                or proposal.original_request_digest != original_request_digest
                or proposal.suppression_consumed_at is not None
            ):
                return None
            if proposal.suppression_claim_id is not None:
                return proposal.suppression_claim_id
            claim_id = f"replay_{uuid4().hex}"
            updated = proposal.model_copy(
                update={
                    "suppression_claim_id": claim_id,
                    "suppression_claimed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            data.entry_proposals[proposal_id] = WPlusEntryProposal.model_validate(
                updated,
            )
            self._save_unlocked(data)
            return claim_id

    def release_suppression_claim(
        self,
        proposal_id: str,
        *,
        claim_id: str,
        ownership: OwnershipTuple,
    ) -> bool:
        """Release a claim only when its Chat run never started."""

        with self._lock:
            data = self._load_unlocked()
            proposal = data.entry_proposals.get(proposal_id)
            if (
                proposal is None
                or proposal.ownership != ownership
                or proposal.suppression_claim_id != claim_id
                or proposal.suppression_consumed_at is not None
            ):
                return False
            updated = proposal.model_copy(
                update={
                    "suppression_claim_id": None,
                    "suppression_claimed_at": None,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            data.entry_proposals[proposal_id] = WPlusEntryProposal.model_validate(
                updated,
            )
            self._save_unlocked(data)
            return True

    def suppression_matches(
        self,
        proposal_id: str,
        *,
        suppression_token: str,
        original_request_digest: str,
        ownership: OwnershipTuple,
    ) -> bool:
        """Check a replay token without consuming it before dispatch."""

        with self._lock:
            proposal = self._load_unlocked().entry_proposals.get(proposal_id)
            return bool(
                proposal is not None
                and proposal.ownership == ownership
                and proposal.status is EntryProposalStatus.REJECTED
                and proposal.suppression_token == suppression_token
                and proposal.original_request_digest == original_request_digest
                and proposal.suppression_consumed_at is None
            )

    def confirm_entry_proposal(
        self,
        proposal_id: str,
        *,
        projection: SessionProjection,
        receipt: CommandReceipt,
        run_attempt: RunAttempt | None = None,
        outbox_item: ChatProjectionOutboxItem | None = None,
    ) -> StoreMutation:
        with self._lock:
            data = self._load_unlocked()
            proposal = data.entry_proposals.get(proposal_id)
            if proposal is None:
                raise EntryProposalConflictError("Entry proposal not found")
            if proposal.status is not EntryProposalStatus.PENDING:
                existing = self._find_duplicate(
                    data,
                    receipt,
                    expected_ownership=proposal.ownership,
                    expected_proposal_id=proposal_id,
                )
                if existing is not None:
                    return existing
                raise EntryProposalConflictError(
                    "Entry proposal is already resolved",
                )
            duplicate = self._find_duplicate(
                data,
                receipt,
                expected_ownership=proposal.ownership,
                expected_proposal_id=proposal_id,
            )
            if duplicate is not None:
                return duplicate
            if proposal.ownership != projection.ownership:
                raise EntryProposalConflictError(
                    "Entry proposal and Session ownership do not match",
                )
            if receipt.sop_session_id != projection.sop_session_id:
                raise WPlusSopStoreError(
                    "confirm_entry receipt does not match Session scope",
                )
            self._assert_no_active_session(data, projection)
            record = self._initial_record(projection)
            record.command_receipts[receipt.command_request_id] = receipt
            if run_attempt is not None:
                record.runs.append(run_attempt)
            if outbox_item is not None:
                record.outbox.append(outbox_item)
            data.sessions[projection.sop_session_id] = record
            data.command_index[receipt.command_request_id] = receipt
            updated = proposal.model_copy(
                update={
                    "status": EntryProposalStatus.CONFIRMED,
                    "command_receipt": receipt,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            data.entry_proposals[proposal_id] = WPlusEntryProposal.model_validate(
                updated,
            )
            self._save_unlocked(data)
            return StoreMutation(
                record=_clone(record),
                receipt=_clone(receipt),
            )

    def create_session(
        self,
        projection: SessionProjection,
        *,
        command_receipt: CommandReceipt,
        run_attempt: RunAttempt | None = None,
    ) -> StoreMutation:
        with self._lock:
            data = self._load_unlocked()
            duplicate = self._find_duplicate(
                data,
                command_receipt,
                expected_ownership=projection.ownership,
            )
            if duplicate is not None:
                return duplicate
            if command_receipt.sop_session_id != projection.sop_session_id:
                raise WPlusSopStoreError(
                    "Session receipt does not match Session scope",
                )
            self._assert_no_active_session(data, projection)
            record = self._initial_record(projection)
            record.command_receipts[
                command_receipt.command_request_id
            ] = command_receipt
            if run_attempt is not None:
                record.runs.append(run_attempt)
            data.sessions[projection.sop_session_id] = record
            data.command_index[
                command_receipt.command_request_id
            ] = command_receipt
            self._save_unlocked(data)
            return StoreMutation(
                record=_clone(record),
                receipt=_clone(command_receipt),
            )

    def get_session(self, sop_session_id: str) -> SessionRecord | None:
        with self._lock:
            record = self._load_unlocked().sessions.get(sop_session_id)
            return _clone(record) if record is not None else None

    def list_sessions(self) -> list[SessionRecord]:
        with self._lock:
            return [
                _clone(record)
                for record in self._load_unlocked().sessions.values()
            ]

    def get_active_by_chat(self, ownership: Any) -> SessionRecord | None:
        with self._lock:
            target_key = ownership.active_chat_key
            for record in self._load_unlocked().sessions.values():
                projection = record.projection
                if (
                    projection.ownership.active_chat_key == target_key
                    and projection.holds_chat_slot
                ):
                    return _clone(record)
            return None

    def commit_event(
        self,
        sop_session_id: str,
        *,
        expected_state_version: int,
        event: StructuredInteractionEnvelope,
        next_state: SessionState,
        projection_changes: dict[str, Any] | None = None,
        outbox_item: ChatProjectionOutboxItem | None = None,
        command_receipt: CommandReceipt | None = None,
        run_attempt: RunAttempt | None = None,
        run_completion: tuple[str, str, RunStatus | str] | None = None,
    ) -> StoreMutation:
        with self._lock:
            data = self._load_unlocked()
            record = data.sessions.get(sop_session_id)
            if record is None:
                raise SessionNotFoundError(sop_session_id)
            duplicate = self._find_duplicate(
                data,
                command_receipt,
                expected_ownership=record.projection.ownership,
                expected_sop_session_id=sop_session_id,
            )
            if duplicate is not None:
                return duplicate
            if (
                command_receipt is not None
                and command_receipt.sop_session_id != sop_session_id
            ):
                raise WPlusSopStoreError(
                    "command receipt does not match Session scope",
                )
            projection = record.projection
            if projection.state_version != expected_state_version:
                raise StaleStateVersionError(
                    f"Expected state version {expected_state_version}, "
                    f"found {projection.state_version}",
                )
            if event.sop_session_id != sop_session_id:
                raise WPlusSopStoreError("Event Session does not match")
            if event.chat_id != projection.chat_id:
                raise WPlusSopStoreError("Event Chat does not match")
            if event.state_version != expected_state_version + 1:
                raise WPlusSopStoreError(
                    "Event state_version must increment exactly once",
                )
            if any(item.event_id == event.event_id for item in record.events):
                return StoreMutation(
                    record=_clone(record),
                    receipt=_clone(command_receipt),
                    duplicate=True,
                )
            if next_state is not projection.state:
                assert_legal_transition(projection.state, next_state)
            updates = {
                **(projection_changes or {}),
                "state": next_state,
                "state_version": event.state_version,
                "revision": event.revision,
                "round": event.round,
                "updated_at": event.created_at,
            }
            if run_attempt is not None:
                updates["current_run_id"] = run_attempt.run_id
            next_projection = projection.model_copy(
                update=updates,
                deep=True,
            )
            next_projection = SessionProjection.model_validate(next_projection)
            record.projection = next_projection
            record.events.append(event)
            if outbox_item is not None:
                if not any(
                    item.projection_event_id
                    == outbox_item.projection_event_id
                    for item in record.outbox
                ):
                    record.outbox.append(outbox_item)
            if command_receipt is not None:
                record.command_receipts[
                    command_receipt.command_request_id
                ] = command_receipt
                data.command_index[
                    command_receipt.command_request_id
                ] = command_receipt
            if run_attempt is not None:
                record.runs.append(run_attempt)
            if run_completion is not None:
                self._finish_run_in_record(
                    record,
                    run_id=run_completion[0],
                    attempt_id=run_completion[1],
                    status=run_completion[2],
                    completed_at=event.created_at,
                )
            self._save_unlocked(data)
            return StoreMutation(
                record=_clone(record),
                receipt=_clone(command_receipt),
            )

    def claim_run(
        self,
        sop_session_id: str,
        *,
        expected_state_version: int,
        receipt: CommandReceipt,
        attempt: RunAttempt,
    ) -> StoreMutation:
        with self._lock:
            data = self._load_unlocked()
            record = data.sessions.get(sop_session_id)
            if record is None:
                raise SessionNotFoundError(sop_session_id)
            duplicate = self._find_duplicate(
                data,
                receipt,
                expected_ownership=record.projection.ownership,
                expected_sop_session_id=sop_session_id,
            )
            if duplicate is not None:
                return duplicate
            if receipt.sop_session_id != sop_session_id:
                raise WPlusSopStoreError(
                    "run receipt does not match Session scope",
                )
            if record.projection.state_version != expected_state_version:
                raise StaleStateVersionError(
                    f"Expected state version {expected_state_version}, "
                    f"found {record.projection.state_version}",
                )
            target_version = receipt.resulting_state_version
            if target_version != expected_state_version + 1:
                raise WPlusSopStoreError(
                    "Run claim must increment state_version exactly once",
                )
            record.projection = record.projection.model_copy(
                update={
                    "state_version": target_version,
                    "current_run_id": attempt.run_id,
                    "updated_at": datetime.now(timezone.utc),
                },
                deep=True,
            )
            record.runs.append(attempt)
            record.command_receipts[receipt.command_request_id] = receipt
            data.command_index[receipt.command_request_id] = receipt
            self._save_unlocked(data)
            return StoreMutation(
                record=_clone(record),
                receipt=_clone(receipt),
            )

    @staticmethod
    def _finish_run_in_record(
        record: SessionRecord,
        *,
        run_id: str,
        attempt_id: str,
        status: RunStatus | str,
        completed_at: datetime,
    ) -> RunAttempt:
        try:
            terminal_status = RunStatus(status)
        except ValueError as exc:
            raise WPlusSopStoreError("invalid terminal run status") from exc
        if terminal_status not in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            raise WPlusSopStoreError("invalid terminal run status")
        matches = [
            (index, attempt)
            for index, attempt in enumerate(record.runs)
            if attempt.run_id == run_id and attempt.attempt_id == attempt_id
        ]
        if len(matches) != 1:
            raise WPlusSopStoreError("run attempt does not match Session")
        index, attempt = matches[0]
        if attempt.status in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            if attempt.status is not terminal_status:
                raise WPlusSopStoreError(
                    "run attempt already has another terminal status",
                )
            return _clone(attempt)
        completed = attempt.model_copy(
            update={
                "status": terminal_status,
                "completed_at": completed_at,
            },
        )
        completed = RunAttempt.model_validate(completed)
        record.runs[index] = completed
        return _clone(completed)

    def finish_run(
        self,
        sop_session_id: str,
        *,
        run_id: str,
        attempt_id: str,
        status: RunStatus | str,
    ) -> RunAttempt:
        """Atomically persist a terminal status for one exact run attempt."""

        with self._lock:
            data = self._load_unlocked()
            record = data.sessions.get(sop_session_id)
            if record is None:
                raise SessionNotFoundError(sop_session_id)
            completed = self._finish_run_in_record(
                record,
                run_id=run_id,
                attempt_id=attempt_id,
                status=status,
                completed_at=datetime.now(timezone.utc),
            )
            self._save_unlocked(data)
            return completed

    def pending_outbox(self) -> list[ChatProjectionOutboxItem]:
        with self._lock:
            pending: list[ChatProjectionOutboxItem] = []
            for record in self._load_unlocked().sessions.values():
                pending.extend(item for item in record.outbox if item.pending)
            return [_clone(item) for item in pending]

    def ack_outbox(self, projection_event_id: str) -> bool:
        with self._lock:
            data = self._load_unlocked()
            for record in data.sessions.values():
                for index, item in enumerate(record.outbox):
                    if item.projection_event_id != projection_event_id:
                        continue
                    if item.acknowledged_at is not None:
                        return False
                    record.outbox[index] = item.model_copy(
                        update={"acknowledged_at": datetime.now(timezone.utc)},
                    )
                    self._save_unlocked(data)
                    return True
            return False
