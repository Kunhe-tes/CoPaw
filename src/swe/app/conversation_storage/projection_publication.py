# -*- coding: utf-8 -*-
"""Prepare and validate immutable recovery projection installation deltas."""

from collections import defaultdict, deque
from dataclasses import replace
from datetime import datetime, timezone
import json

from .bundle import BundleBlock
from .chat_mutations import load_metadata_json
from .errors import IntegrityError
from .message_installs import MessageInstall
from .retention import ReaderPins, RetentionStore
from .identity import WorkspaceScope
from .projection_cache import cached, remember, cache_key
from .session_projection import (
    project_state,
    hydrate_state,
    is_projection,
    LISTS,
    FORMAT,
    VERSION,
)
from .message_bundle import encode_message_directory

IDENTITY_FIELDS = (
    "operation_key",
    "scope_kind",
    "service_unit_key",
    "tenant_key",
    "source_key",
    "agent_key",
    "session_id",
    "chat_id",
    "turn_id",
    "base_state_revision",
    "base_history_revision",
    "epoch",
)


def _text(value):
    return (
        bytes(value).decode()
        if isinstance(value, (bytes, bytearray))
        else value
    )


def identity(row):
    return {key: _text(row[key]) for key in IDENTITY_FIELDS}


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _stamp(value):
    if value is None:
        return None
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.isoformat()


async def _existing(service, row):
    known = cached(cache_key(row))
    if known is not None:
        result = defaultdict(deque)
        for key, value in known.items():
            result[key].extend(value)
        return result
    result = defaultdict(deque)
    if row["session_id"] is None or not hasattr(service.db, "fetch_all"):
        remember(cache_key(row), result)
        return result
    retentions = RetentionStore(
        service.db,
        WorkspaceScope.from_row(row),
    )
    batch = ReaderPins(retentions)
    try:
        async with service.db.transaction():
            session = await service.db.fetch_one(
                "SELECT * FROM swe_conversation_sessions WHERE id=%s "
                "AND service_unit_key=%s",
                (row["session_id"], row["service_unit_key"]),
            )
            if (
                session is None
                or session.get("recovery_publication_id") is None
            ):
                remember(cache_key(row), result)
                return result
            await batch.pin([session["recovery_publication_id"]])
        publication = batch.publications[0]
        if publication["session_id"] != row["session_id"]:
            raise IntegrityError(
                "projection root Session association mismatch",
            )
        index = await batch.read(
            service.bundles.inspect,
            _text(publication["relative_path"]),
            expected_length=publication["byte_length"],
        )
        raw = await batch.read(
            service.bundles.read_extent,
            index.relative_path,
            session["recovery_offset"],
            session["recovery_length"],
            expected_length=index.byte_length,
        )
        envelope = load_metadata_json(raw)
        if not is_projection(envelope):
            return result
        from .projection_references import ref_key, snapshot_projection

        source = type(
            "ProjectionSource",
            (),
            {
                "operation_key": _text(publication["operation_key"]),
                "scope": WorkspaceScope.from_row(row),
                "session_id": row["session_id"],
            },
        )()
        snapshot = await snapshot_projection(
            service,
            source,
            envelope,
            index,
            current_id=publication["id"],
            retentions=retentions,
        )
        try:
            for entry in envelope.get("message_directory", []):
                layer = entry["layer"]
                if layer not in ("memory", "task", "error"):
                    continue
                locator = entry["body"]
                if locator["publication_id"] == "self":
                    ref = {
                        "operation_key": source.operation_key,
                        "block_name": locator["block_name"],
                        "position": locator["position"],
                    }
                else:
                    ref = locator
                body = snapshot.payloads[ref_key(ref)]
                result[(layer, canonical(body))].append(
                    {
                        **locator,
                        "publication_id": ref.get(
                            "publication_id",
                            publication["id"],
                        ),
                    },
                )
        finally:
            await snapshot.finish(retentions)
        remember(cache_key(row), result)
        return result
    finally:
        await batch.finish()


async def _previous_directory(service, row):
    retentions = RetentionStore(
        service.db,
        WorkspaceScope.from_row(row),
    )
    batch = ReaderPins(retentions)
    try:
        async with service.db.transaction():
            session = await service.db.fetch_one(
                "SELECT * FROM swe_conversation_sessions WHERE id=%s "
                "AND service_unit_key=%s",
                (row["session_id"], row["service_unit_key"]),
            )
            if (
                session is None
                or session.get("recovery_publication_id") is None
            ):
                return []
            await batch.pin([session["recovery_publication_id"]])
        publication = batch.publications[0]
        index = await batch.read(
            service.bundles.inspect,
            _text(publication["relative_path"]),
            expected_length=publication["byte_length"],
        )
        raw = await batch.read(
            service.bundles.read_extent,
            index.relative_path,
            session["recovery_offset"],
            session["recovery_length"],
            expected_length=index.byte_length,
        )
        envelope = load_metadata_json(raw)
        directory = envelope.get("message_directory", [])
        if not isinstance(directory, list):
            raise IntegrityError("recovery message directory is invalid")
        result = []
        for item in directory:
            entry = dict(item)
            locator = dict(entry["body"])
            if locator["publication_id"] == "self":
                locator["publication_id"] = publication["id"]
                entry["body"] = locator
            result.append(entry)
        return result
    finally:
        await batch.finish()


async def prepare_recovery_blocks(
    service,
    row,
    plan,
    blocks,
):  # pylint: disable=too-many-statements
    if plan.recovery_block is None:
        return blocks
    root = next(
        (item for item in blocks if item.name == plan.recovery_block),
        None,
    )
    if root is None or not isinstance(root.content, bytes):
        return blocks
    state = load_metadata_json(root.content)
    if is_projection(state):
        raise IntegrityError(
            "writers must provide hydrated complete recovery state",
        )
    from .session_projection import LISTS, _parent

    has_history = any(
        (parent := _parent(state, path)) is not None
        and bool(parent.get(path[-1]))
        for path, _, _ in LISTS
    )
    available = (
        await _existing(service, row) if has_history else defaultdict(deque)
    )
    supplied = {item.name: item for item in blocks}
    context = await service.db.fetch_one(
        "SELECT context_epoch,history_high FROM swe_conversation_sessions WHERE id=%s AND service_unit_key=%s",
        (row["session_id"], row["service_unit_key"]),
    )
    epoch = context["context_epoch"]
    for message in plan.messages:
        if (
            message.layer not in ("memory", "task", "error")
            or message.block_name not in supplied
        ):
            continue
        body = load_metadata_json(supplied[message.block_name].content)
        available[(message.layer, canonical(body))].append(
            {
                "operation_key": _text(row["operation_key"]),
                "block_name": message.block_name,
            },
        )

    resolved_bodies = {}

    def resolve(layer, body):
        values = available.get((layer, canonical(body)))
        ref = values.popleft() if values else None
        if ref is not None:
            ref = {**ref, "position": ref.get("position", 0)}
            resolved_bodies[canonical(ref)] = body
        return ref

    frozen_turns = await _frozen_turns(service, row, state)
    projection = project_state(
        state,
        operation_key=_text(row["operation_key"]),
        resolve_message=resolve,
        resolve_turn=lambda key, value: frozen_turns.get(key),
    )
    installations = []
    for name, layer, body in projection.messages:
        source = body.get("id")
        role = body.get("role") or "assistant"
        installations.append(
            MessageInstall(
                name,
                layer,
                role,
                source_msg_key=source,
                turn_id=row["turn_id"],
                context_epoch=epoch,
                in_context=layer == "memory",
                message_timestamp=_stamp(body.get("timestamp")),
            ),
        )
    envelope = {
        **projection.envelope,
        "identity": identity(row),
        "installations": [item.to_dict() for item in installations],
        "dependency_ids": list(projection.dependency_ids),
    }
    # Keep occurrence metadata in the recovery root so current history can be
    # reconstructed without a relational message index. Body references remain
    # in the projection lists and are resolved by projection_references.
    for name, _layer, body in projection.messages:
        resolved_bodies[
            canonical(
                {
                    "operation_key": _text(row["operation_key"]),
                    "block_name": name,
                    "position": 0,
                },
            )
        ] = body
    installs_by_name = {
        item.block_name: item for item in (*installations, *plan.messages)
    }
    previous_entries = (
        []
        if plan.reset is not None
        else await _previous_directory(service, row)
    )
    previous_by_ref = {
        canonical(entry["body"]): entry for entry in previous_entries
    }
    anchors_by_id = defaultdict(deque)
    for entry in previous_entries:
        if entry.get("layer") == "anchor":
            anchors_by_id[entry["raw_id"]].append(entry)
    retained_refs = set()
    directory = []
    seen_refs = set()
    sequence = context.get("history_high", 0) + 1
    projected_layers = set()
    for series in envelope["lists"]:
        layer = next(
            (
                known_layer
                for known_path, known_layer, _ in LISTS
                if tuple(series["path"]) == known_path
            ),
            "memory",
        )
        projected_layers.add(layer)
        for item in series["entries"]:
            ref = dict(item["ref"])
            ref.setdefault("position", 0)
            locator_key = canonical(ref)
            if locator_key in seen_refs:
                continue
            seen_refs.add(locator_key)
            body = resolved_bodies.get(locator_key)
            if body is None:
                raise IntegrityError("recovery body reference lacks directory")
            install = (
                installs_by_name.get(ref["block_name"])
                if "publication_id" not in ref
                else None
            )
            previous = previous_by_ref.get(
                canonical(
                    {
                        "publication_id": ref.get("publication_id", "self"),
                        "block_name": ref["block_name"],
                        "position": ref["position"],
                    },
                ),
            )
            entry = {
                "sequence": (
                    previous.get("sequence", sequence)
                    if previous
                    else sequence
                ),
                "session_order": (
                    previous.get("session_order", sequence)
                    if previous
                    else sequence
                ),
                "raw_id": str(body.get("id", "")),
                "category": install.layer if install is not None else layer,
                "layer": install.layer if install is not None else layer,
                "role": body.get("role") or "assistant",
                "visible": (
                    install.current_visible if install is not None else True
                ),
                "current_visible": (
                    install.current_visible if install is not None else True
                ),
                "in_context": (
                    install.in_context
                    if install is not None
                    else layer == "memory"
                ),
                "body": {
                    "publication_id": ref.get("publication_id", "self"),
                    "block_name": ref["block_name"],
                    "position": ref["position"],
                },
            }
            if install is not None:
                entry.update(
                    {
                        "turn_id": install.turn_id,
                        "origin_chat_id": install.origin_chat_id,
                        "source_msg_key": install.source_msg_key,
                        "source_occurrence_no": install.source_occurrence_no,
                        "context_epoch": install.context_epoch,
                        "kind": install.kind,
                        "task": install.task_run_key,
                        "timestamp": install.message_timestamp,
                        "chat_id": install.origin_chat_id,
                    },
                )
            elif body.get("timestamp") is not None:
                entry["timestamp"] = _stamp(body["timestamp"])
            if previous is not None and install is None:
                entry = {
                    **previous,
                    "body": entry["body"],
                    "in_context": entry["in_context"],
                }
            anchors = anchors_by_id.get(entry["raw_id"])
            if (
                anchors
                and layer == "memory"
                and entry.get("origin_chat_id") is None
            ):
                anchor = anchors.popleft()
                entry.update(
                    {
                        key: anchor[key]
                        for key in (
                            "turn_id",
                            "origin_chat_id",
                            "chat_id",
                            "source_msg_key",
                            "source_occurrence_no",
                        )
                        if anchor.get(key) is not None
                    },
                )
            if previous is None:
                entry["source_occurrence_no"] = sequence - 1
            retained_refs.add(canonical(entry["body"]))
            if plan.reset is not None:
                entry.update(
                    visible=False,
                    current_visible=False,
                    in_context=False,
                )
            directory.append(entry)
            if previous is None:
                sequence += 1
    for previous in previous_entries:
        locator_key = canonical(previous["body"])
        if (
            locator_key in retained_refs
            or previous["sequence"] in plan.prune_ids
            or previous["layer"] in projected_layers
        ):
            continue
        directory.append(previous)
    for install in plan.messages:
        if install.layer not in ("memory", "task", "error", "anchor"):
            continue
        if install.block_name not in supplied:
            continue
        locator = {
            "publication_id": "self",
            "block_name": install.block_name,
            "position": 0,
        }
        locator_key = canonical(locator)
        if locator_key in retained_refs:
            continue
        body = load_metadata_json(supplied[install.block_name].content)
        directory.append(
            {
                "sequence": sequence,
                "session_order": sequence,
                "raw_id": str(body.get("id", "")),
                "category": install.layer,
                "layer": install.layer,
                "role": body.get("role") or "assistant",
                "visible": install.current_visible,
                "current_visible": install.current_visible,
                "in_context": install.in_context,
                "body": locator,
                "turn_id": install.turn_id,
                "origin_chat_id": install.origin_chat_id,
                "source_msg_key": install.source_msg_key,
                "source_occurrence_no": sequence - 1,
                "context_epoch": install.context_epoch,
                "kind": install.kind,
                "task": install.task_run_key,
                "timestamp": install.message_timestamp,
                "chat_id": install.origin_chat_id,
            },
        )
        retained_refs.add(locator_key)
        sequence += 1
    directory.sort(
        key=lambda entry: entry.get("session_order", entry["sequence"]),
    )
    encode_message_directory(directory)
    envelope["message_directory"] = directory
    envelope["dependency_ids"] = sorted(
        set(projection.dependency_ids)
        | {
            entry["body"]["publication_id"]
            for entry in directory
            if entry["body"]["publication_id"] != "self"
        },
    )
    envelope["prune_ids"] = list(plan.prune_ids)
    turn_blocks = []
    if plan.turn_install is not None:
        turns = state.get("turn_states", {})
        for key, value in turns.items():
            if key in frozen_turns:
                continue
            if isinstance(value, dict):
                turn_blocks.append(
                    BundleBlock(
                        "turn:" + key,
                        "turn",
                        canonical(value).encode(),
                    ),
                )
    replacement = BundleBlock(
        root.name,
        root.kind,
        canonical(envelope).encode(),
    )
    return (
        [replacement if item is root else item for item in blocks]
        + list(projection.blocks)
        + turn_blocks
    )


async def _frozen_turns(service, row, state):
    result = {}
    if not isinstance(state.get("turn_states"), dict) or not hasattr(
        service.db,
        "fetch_all",
    ):
        return result
    turns = await service.db.fetch_all(
        "SELECT * FROM swe_conversation_turns WHERE session_id=%s AND service_unit_key=%s AND terminal_publication_id IS NOT NULL ORDER BY id",
        (row["session_id"], row["service_unit_key"]),
    )
    retentions = RetentionStore(
        service.db,
        WorkspaceScope.from_row(row),
    )
    for turn in turns:
        if turn["service_unit_key"] != row["service_unit_key"]:
            raise IntegrityError("cold Turn service unit mismatch")
        key = _text(turn["question_msg_key"])
        value = state["turn_states"].get(key)
        if (
            not isinstance(value, dict)
            or value.get("status") != turn["history_status"]
        ):
            continue
        async with service.db.transaction():
            batch = await retentions.pin(
                [turn["terminal_publication_id"]],
                kind="reader",
            )
        try:
            publication = batch.publications[0]
            if (
                publication["session_id"] != row["session_id"]
                or publication["turn_id"] != turn["id"]
            ):
                raise IntegrityError(
                    "cold Turn publication association differs",
                )
            index = await batch.read(
                service.bundles.inspect,
                _text(publication["relative_path"]),
                expected_length=publication["byte_length"],
            )
            block = index.blocks.get("turn:" + key)
            if block is None or block.kind != "turn":
                continue
            raw = await batch.read(
                service.bundles.read_extent,
                index.relative_path,
                block.offset,
                block.length,
                expected_length=index.byte_length,
            )
            if load_metadata_json(raw) == value:
                result[key] = {
                    "publication_id": publication["id"],
                    "operation_key": _text(publication["operation_key"]),
                    "block_name": block and "turn:" + key,
                    "turn_id": turn["id"],
                }
        finally:
            await retentions.finish_reader(batch)
    return result


def _validate_ref_shape(ref):
    allowed = (
        {"publication_id", "message_id", "offset", "length"}
        if "message_id" in ref
        else (
            {"publication_id", "block_name", "position"}
            if "publication_id" in ref and "position" in ref
            else (
                {"publication_id", "operation_key", "block_name", "turn_id"}
                if "publication_id" in ref
                else {"operation_key", "block_name"}
            )
        )
    )
    if set(ref) == {"operation_key", "block_name", "position"}:
        return
    if set(ref) != allowed:
        raise IntegrityError(
            "projection reference fields are not whitelisted",
        )


def _validate_additions(additions, existing_names, request):
    if len(additions) > 4096 or any(
        item.layer not in ("memory", "task", "error")
        or item.block_name in existing_names
        or item.source_message_id is not None
        or item.turn_id != request.turn_id
        for item in additions
    ):
        raise IntegrityError(
            "recovery projection installer is not an allowed delta",
        )
    if len({item.block_name for item in additions}) != len(additions):
        raise IntegrityError("projection delta block names repeat")


def _context_usage_projection(envelope, plan):
    state = envelope["state"] if is_projection(envelope) else envelope
    from ..runner.context_usage import ContextUsageSnapshot

    usage = state.get("context_usage") if isinstance(state, dict) else None
    invalid = bool(
        plan.reset is not None
        or (
            isinstance(state, dict)
            and state.get("context_usage_invalid", False)
        ),
    )
    try:
        snapshot = ContextUsageSnapshot.model_validate(usage)
        usage_text = snapshot.model_dump_json()
    except (ValueError, TypeError):
        usage_text, invalid = None, True
    return usage_text, invalid


async def effective_recovery_plan(
    service,
    request,
    row,
    plan,
    index,
):  # pylint: disable=too-many-statements
    if plan.recovery_block is None:
        return plan, None
    extent = index.blocks.get(plan.recovery_block)
    if extent is None or extent.kind != "recovery":
        raise IntegrityError("recovery projection block is missing")
    raw = await service._nas_io(
        request.operation_key,
        service.bundles.read_extent,
        index.relative_path,
        extent.offset,
        extent.length,
        expected_length=index.byte_length,
    )
    envelope = load_metadata_json(raw)
    plan = replace(
        plan,
        context_usage_projection=_context_usage_projection(envelope, plan),
    )
    if not is_projection(envelope):
        return plan, None
    if envelope.get("identity") != identity(row):
        raise IntegrityError(
            "recovery projection publication identity mismatch",
        )
    if not isinstance(envelope.get("installations"), list) or not isinstance(
        envelope.get("dependency_ids"),
        list,
    ):
        raise IntegrityError(
            "recovery projection installation metadata is invalid",
        )
    additions = tuple(
        MessageInstall.from_dict(item) for item in envelope["installations"]
    )
    existing_names = {item.block_name for item in plan.messages}
    _validate_additions(additions, existing_names, request)
    names = {item.block_name for item in additions} | existing_names
    refs = [
        entry["ref"]
        for series in envelope["lists"]
        for entry in series["entries"]
    ]
    refs.extend(item["ref"] for item in envelope["turns"])
    for entry in envelope.get("message_directory", []):
        locator = entry["body"]
        if locator["publication_id"] == "self":
            refs.append(
                {
                    "operation_key": request.operation_key,
                    "block_name": locator["block_name"],
                    "position": locator["position"],
                },
            )
        else:
            refs.append(locator)
    targets = set()
    for ref in refs:
        _validate_ref_shape(ref)
        if "publication_id" in ref:
            if (
                type(ref["publication_id"]) is not int
                or ref["publication_id"] <= 0
            ):
                raise IntegrityError(
                    "projection dependency identity is invalid",
                )
            targets.add(ref["publication_id"])
        else:
            if (
                ref.get("operation_key") != request.operation_key
                or ref.get("block_name") not in names
            ):
                raise IntegrityError(
                    "projection same-publication reference is not installed",
                )
            block = index.blocks.get(ref["block_name"])
            if block is None or block.kind not in (
                "memory",
                "message",
                "task",
                "error",
                "anchor",
                "message_bodies",
            ):
                raise IntegrityError(
                    "projection reference block kind is invalid",
                )
    if targets != set(envelope["dependency_ids"]):
        raise IntegrityError(
            "projection dependencies differ from explicit references",
        )
    if {item.block_name for item in additions} - {
        ref.get("block_name") for ref in refs if "publication_id" not in ref
    }:
        raise IntegrityError("unreferenced projection Message installer")
    for item in additions:
        block = index.blocks.get(item.block_name)
        if block is None or block.kind != item.layer:
            raise IntegrityError("projection delta body block kind mismatch")
        payload = await service._nas_io(
            request.operation_key,
            service.bundles.read_extent,
            index.relative_path,
            block.offset,
            block.length,
            expected_length=index.byte_length,
        )
        body = load_metadata_json(payload)
        if (
            not isinstance(body, dict)
            or body.get("id") != item.source_msg_key
            or (body.get("role") or "assistant") != item.role
        ):
            raise IntegrityError("projection delta body identity mismatch")
        if (
            item.origin_chat_id is not None
            or item.archive_chat_id is not None
            or not item.current_visible
            or item.in_context != (item.layer == "memory")
            or item.message_timestamp != _stamp(body.get("timestamp"))
        ):
            raise IntegrityError(
                "projection delta typed fields differ from allowed shape",
            )
    pruned = envelope.get("prune_ids", [])
    if (
        not isinstance(pruned, list)
        or len(pruned) > 4096
        or any(type(value) is not int or value <= 0 for value in pruned)
    ):
        raise IntegrityError("projection prune occurrence IDs are invalid")
    if sorted(set(pruned)) != sorted(set(plan.prune_ids)):
        raise IntegrityError("projection prune set differs from install plan")
    effective = replace(
        plan,
        messages=(*plan.messages, *additions),
        prune_ids=tuple(sorted(set(plan.prune_ids) | set(pruned))),
    )
    return effective, envelope
