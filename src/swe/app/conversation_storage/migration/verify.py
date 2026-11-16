# -*- coding: utf-8 -*-
"""Full semantic comparisons from committed SQL locators and immutable bodies."""

import asyncio

from ..bundle import BlockExtent, MAX_READ_BYTES
from ..chat_repository import MySQLChatRepository
from ..chat_mutations import (
    load_metadata_json,
    split_metadata,
    validate_light_metadata,
)
from ..identity import WorkspaceScope
from ..session_adapter import MySQLSessionAdapter
from .importer import bundle_stores, validate_inventory
from .install_records import OfflineImportStore
from ..errors import StorageError
from mysql.connector.errors import Error as MySQLError
from ..history import HistoryStore
from ..archive_reader import ArchiveReader
from .importer import archive_batches, message_body, task_projections
from .manifest import SourceBoundary
from .readonly import ReadOnlyDatabase, ReadOnlyRetention, read_only_adapter
from .verify_parallel import (
    verify_workspace_messages as _parallel_message_checks,
)

from .verify_parallel import verify_auxiliary_bodies

from .failure_scope import isolated_verification, raise_shared_failure

VERIFY_ERRORS = (
    ValueError,
    KeyError,
    TypeError,
    OSError,
    StorageError,
    MySQLError,
)


async def _verify_fast_level(
    database,
    stores,
    manifest,
    inventory,
    target,
    report,
    *,
    io,
    io_workers,
    workers,
    memory_bytes,
):
    from .verify_fast import verify_fast_publications

    try:
        expected_scopes = None
        if manifest.data.get("tenant_isolation"):
            expected_scopes = {
                tuple(workspace["scope"])
                for workspace in inventory["workspaces"]
            }
        if io is None:
            from .parallel import MigrationIO

            async with MigrationIO(io_workers) as fast_io:
                summary = await verify_fast_publications(
                    database,
                    stores,
                    manifest,
                    target,
                    io=fast_io,
                    io_workers=io_workers,
                    memory_bytes=memory_bytes // max(1, workers),
                    expected_scopes=expected_scopes,
                )
        else:
            summary = await verify_fast_publications(
                database,
                stores,
                manifest,
                target,
                io=io,
                io_workers=io_workers,
                memory_bytes=memory_bytes // max(1, workers),
                expected_scopes=expected_scopes,
            )
        report["checked"] = [
            {"position": "publications", "count": summary["publications"]},
        ]
        report["fast_summary"] = summary
    except VERIFY_ERRORS as error:
        raise_shared_failure(error)
        report["blockers"].append(
            {"position": "source", "detail": str(error)},
        )
    report["passed"] = not report["blockers"]


async def _verification_context(
    database,
    bundles,
    manifest,
    inventory,
    target,
):
    validate_inventory(inventory)
    if inventory.get("shares") or manifest.data.get("shares"):
        raise ValueError(
            "historical share records are excluded from migration",
        )
    from pathlib import Path

    stores = bundle_stores(bundles, manifest)
    binding = {
        "schema": target.schema,
        "nas_roots": {
            key: str(store.root.resolve()) for key, store in stores.items()
        },
        "migration_id": manifest.migration_id,
    }
    if manifest.data.get("target") != binding or manifest.data[
        "source_boundary"
    ] != inventory.get("source_boundary"):
        raise ValueError(
            "verification target or source boundary differs from manifest",
        )
    expected = [
        (
            item["service_unit_id"],
            item["tenant_id"],
            item["source_id"],
            item["agent_id"],
            str(Path(item["root"]).resolve()),
        )
        for item in manifest.data["workspaces"]
    ]
    actual = [
        (*item["scope"], item["root"]) for item in inventory["workspaces"]
    ]
    if expected != actual:
        raise ValueError(
            "verification workspace mapping differs from manifest",
        )
    await OfflineImportStore(
        database,
        next(iter(stores.values())),
        target,
        service_unit_id=next(iter(stores)),
    ).validate_target()
    return (
        ReadOnlyDatabase(
            database,
            SourceBoundary(**manifest.data["source_boundary"]),
        ),
        stores,
    )


async def _payload(
    database,
    bundles,
    row,
    offset,
    length,
    *,
    service_unit_id,
    io=None,
):
    service = service_unit_id.encode("utf-8")
    if row["service_unit_key"] != service:
        raise ValueError("referencing row service ownership differs")
    publication = await database.fetch_one(
        "SELECT * FROM swe_conversation_publications WHERE id=%s AND state='committed' AND gc_state='live'",
        (row["publication_id"],),
    )
    if publication is not None and publication["service_unit_key"] != service:
        raise ValueError("referenced publication service ownership differs")
    if publication is None:
        raise ValueError("referenced publication is not committed/live")
    arguments = (
        bundles.validate_publication_locator(publication),
        row[offset],
        row[length],
    )
    kwargs = {"expected_length": publication["byte_length"]}
    value = (
        await io.call(bundles.read_extent, *arguments, **kwargs)
        if io is not None
        else bundles.read_extent(*arguments, **kwargs)
    )
    return load_metadata_json(value)


async def _payloads(
    database,
    bundles,
    rows,
    offset,
    length,
    *,
    service_unit_id,
    io,
    io_workers,
):
    service = service_unit_id.encode("utf-8")
    publications = {}
    identifiers = list(dict.fromkeys(row["publication_id"] for row in rows))
    for start in range(0, len(identifiers), 128):
        chunk = identifiers[start : start + 128]
        placeholders = ",".join(["%s"] * len(chunk))
        found = await database.fetch_all(
            "SELECT * FROM swe_conversation_publications "
            "WHERE id IN (" + placeholders + ") "
            "AND state='committed' AND gc_state='live'",
            tuple(chunk),
        )
        for publication in found:
            if publication["service_unit_key"] != service:
                raise ValueError(
                    "referenced publication service ownership differs",
                )
            publications[publication["id"]] = publication
    if set(publications) != set(identifiers):
        raise ValueError("referenced publication is not committed/live")
    for row in rows:
        if row["service_unit_key"] != service:
            raise ValueError("referencing row service ownership differs")
    grouped = {}
    for position, row in enumerate(rows):
        grouped.setdefault(row["publication_id"], []).append((position, row))

    def read_group(publication_id):
        publication = publications[publication_id]
        path = bundles.validate_publication_locator(publication)
        with bundles.open_reader(
            path,
            expected_length=publication["byte_length"],
        ) as reader:
            result = []
            for position, row in grouped[publication_id]:
                block = next(
                    (
                        block
                        for block in reader.index.blocks.values()
                        if block.offset <= row[offset]
                        and row[offset] + row[length]
                        <= block.offset + block.length
                    ),
                    None,
                )
                if block is None:
                    raise ValueError(
                        "message extent is outside publication payload",
                    )

                extent = BlockExtent(block.kind, row[offset], row[length])
                raw = reader.read_extents((extent,))[0]
                result.append((position, load_metadata_json(raw)))
            return result

    result = [None] * len(rows)
    identifiers = list(grouped)
    for start in range(0, len(identifiers), io_workers):
        groups = await asyncio.gather(
            *(
                io.call(read_group, identity)
                for identity in identifiers[start : start + io_workers]
            ),
        )
        for group in groups:
            for position, value in group:
                result[position] = value
    return result


@isolated_verification
async def verify_import(
    database,
    bundles,
    manifest,
    inventory,
    target,
    *,
    io=None,
    io_workers=4,
    workers=1,
    memory_bytes=512 * 1024 * 1024,
    health_check=None,
    verification_level="full",
):
    if verification_level not in ("fast", "full"):
        raise ValueError("verification level must be fast or full")
    report = {
        "version": 2,
        "migration_id": manifest.migration_id,
        "excluded_scopes": ["historical_shares"],
        "verification_level": verification_level,
        "checked": [],
        "blockers": [],
        "passed": False,
    }
    try:
        database, stores = await _verification_context(
            database,
            bundles,
            manifest,
            inventory,
            target,
        )
    except VERIFY_ERRORS as error:
        raise_shared_failure(error)
        report["blockers"].append(
            {"position": "migration", "detail": str(error)},
        )
        return report
    if verification_level == "fast":
        await _verify_fast_level(
            database,
            stores,
            manifest,
            inventory,
            target,
            report,
            io=io,
            io_workers=io_workers,
            workers=workers,
            memory_bytes=memory_bytes,
        )
        return report
    if io is not None:
        await _parallel_message_checks(
            database,
            stores,
            manifest,
            inventory,
            report,
            io=io,
            workers=workers,
            io_workers=io_workers,
            memory_bytes=memory_bytes // workers,
            health_check=health_check,
        )
    if io is not None:
        await verify_auxiliary_bodies(
            database,
            stores,
            manifest,
            inventory,
            report,
            io=io,
            workers=workers,
            memory_bytes=memory_bytes // workers,
            health_check=health_check,
        )

    def merge_runtime_result(local):
        report["checked"].extend(local["checked"])
        report["blockers"].extend(local["blockers"])

    async def runtime_workspace(workspace, bundles):
        local = {"checked": [], "blockers": []}
        for session in workspace["sessions"]:
            await _checked(
                local,
                session["position"],
                _verify_session(
                    database,
                    bundles,
                    manifest,
                    workspace,
                    session,
                    io=io,
                    io_workers=io_workers,
                    messages_verified=io is not None,
                ),
            )
        for chat in workspace["chats"]:
            await _checked(
                local,
                chat["position"],
                _verify_chat(
                    database,
                    bundles,
                    manifest,
                    workspace,
                    chat,
                    io=io,
                    io_workers=io_workers,
                    messages_verified=io is not None,
                ),
            )

        return local

    if io is not None:
        from .runtime_prefetch import verify_prefetched_workspaces

        await verify_prefetched_workspaces(
            database,
            stores,
            inventory,
            runtime_workspace,
            io=io,
            workers=workers,
            allowance=memory_bytes // workers,
            health_check=health_check,
            merge_result=merge_runtime_result,
        )
    else:
        for workspace in inventory["workspaces"]:
            merge_runtime_result(
                await runtime_workspace(
                    workspace,
                    stores[workspace["scope"][0]],
                ),
            )

    for item in (() if io is not None else inventory.get("files", [])):
        from .importer import artifact_is_reconstructed

        workspace = inventory["workspaces"][item["workspace"]]
        if artifact_is_reconstructed(item, workspace):
            continue
        position = (
            "service:"
            + workspace["scope"][0]
            + "/source-artifact:"
            + str(item["workspace"])
            + "/"
            + item["path"]
        )
        await _checked(
            report,
            position,
            _verify_artifact(
                database,
                stores[workspace["scope"][0]],
                manifest,
                inventory,
                item,
                io=io,
            ),
        )
    report["passed"] = not report["blockers"]
    if report["passed"]:
        for position, state in list(manifest.data["batches"].items()):
            if state == "committed":
                manifest.set_batch_state(position, "verified")
    return report


async def _verify_artifact(
    database,
    bundles,
    manifest,
    inventory,
    item,
    *,
    io=None,
):
    from pathlib import Path

    position = (
        "service:"
        + inventory["workspaces"][item["workspace"]]["scope"][0]
        + "/source-artifact:"
        + str(item["workspace"])
        + "/"
        + item["path"]
    )
    assignment = manifest.data["assignments"]["publication"][position]
    publication = await database.fetch_one(
        "SELECT * FROM swe_conversation_publications WHERE id=%s AND state='committed' AND gc_state='live'",
        (assignment["target_id"],),
    )
    if (
        publication is None
        or publication["service_unit_key"]
        != inventory["workspaces"][item["workspace"]]["scope"][0].encode(
            "utf-8",
        )
        or publication["operation_key"].decode() != assignment["operation_key"]
    ):
        raise ValueError(
            "retained legacy artifact publication identity differs",
        )
    workspace = inventory["workspaces"][item["workspace"]]
    expected = {
        "version": 2,
        "workspace": item["workspace"],
        "scope": workspace["scope"],
        "relative_path": item["path"],
        "bytes": item["bytes"],
        "snapshot_id": inventory["source_boundary"]["snapshot_id"],
    }
    if io is None:
        index = bundles.inspect(
            assignment["relative_path"],
            expected_length=publication["byte_length"],
        )
    else:
        index = await io.call(
            bundles.inspect,
            assignment["relative_path"],
            expected_length=publication["byte_length"],
        )
    meta = index.blocks["legacy_artifact_metadata"]
    body = index.blocks["legacy_artifact"]
    metadata_raw, body_raw = await _read_extents(
        bundles,
        index.relative_path,
        (meta, body),
        io=io,
    )
    if load_metadata_json(metadata_raw) != expected:
        raise ValueError("retained legacy artifact source identity differs")
    source_path = Path(workspace["root"]) / item["path"]
    source = (
        source_path.read_bytes()
        if io is None
        else await io.call(source_path.read_bytes)
    )
    if len(source) != item["bytes"] or body_raw != source:
        raise ValueError("retained native legacy artifact bytes differ")


async def _read_extents(bundles, relative_path, extents, *, io):
    if len(extents) > 2:
        raise ValueError("verification reads at most two extents")
    arguments = (relative_path, extents)
    # Verification reads at most an artifact body and its metadata together.
    kwargs = {"max_bytes": 2 * MAX_READ_BYTES}
    if io is None:
        return bundles.read_extents(*arguments, **kwargs)
    return await io.call(bundles.read_extents, *arguments, **kwargs)


async def _checked(report, position, check):
    try:
        await check
        report["checked"].append(position)
    except VERIFY_ERRORS as error:
        raise_shared_failure(error)
        report["blockers"].append({"position": position, "detail": str(error)})


async def _verify_session(
    database,
    bundles,
    manifest,
    workspace,
    session,
    *,
    io=None,
    io_workers=4,
    messages_verified=False,
):
    scope = WorkspaceScope.from_values(workspace["scope"])
    identity = session["identity"]
    adapter = MySQLSessionAdapter(
        database,
        scope,
        bundles,
        channel=identity[5],
    )
    read_only_adapter(adapter)
    actual = await adapter.get_session_state_dict(
        identity[6],
        identity[4],
        False,
    )
    expected = session["legacy"]["state"]
    if actual != {**expected, "revision": expected.get("revision", 0)}:
        raise ValueError("complete Session recovery modules differ")
    await _verify_legacy_session_root(
        database,
        bundles,
        manifest,
        workspace,
        session,
        io=io,
    )
    sid = manifest.data["assignments"]["session"][session["position"]][
        "target_id"
    ]
    if not messages_verified:
        await _verify_session_messages(
            database,
            bundles,
            workspace,
            session,
            sid,
            io=io,
            io_workers=io_workers,
        )
    await _verify_turns(adapter, identity, expected)


async def _verify_legacy_session_root(
    database,
    bundles,
    manifest,
    workspace,
    session,
    *,
    io=None,
):
    """Validate canonical export evidence as well as runtime recovery state."""
    scope = WorkspaceScope.from_values(workspace["scope"])
    assignment = manifest.data["assignments"]["publication"][
        session["position"] + "/recovery"
    ]
    publication = await database.fetch_one(
        "SELECT * FROM swe_conversation_publications WHERE id=%s AND state='committed' AND gc_state='live'",
        (assignment["target_id"],),
    )
    if (
        publication is None
        or publication["scope_kind"] != "workspace"
        or WorkspaceScope.from_row(publication) != scope
        or publication["operation_key"].decode() != assignment["operation_key"]
    ):
        raise ValueError("canonical Session publication identity differs")
    path = bundles.validate_publication_locator(publication)
    if path != assignment["relative_path"]:
        raise ValueError("canonical Session publication path differs")
    retention = ReadOnlyRetention(database, scope)
    batch = await retention.pin([publication["id"]], kind="reader")
    try:
        index = (
            bundles.inspect(path, expected_length=publication["byte_length"])
            if io is None
            else await io.call(
                bundles.inspect,
                path,
                expected_length=publication["byte_length"],
            )
        )
        block = index.blocks["legacy_root"]
        if block.kind != "legacy_root":
            raise ValueError("canonical Session root block kind differs")
        (body,) = await _read_extents(bundles, path, (block,), io=io)
        if load_metadata_json(body) != session["legacy"]["root"]:
            raise ValueError("complete canonical Session root differs")
    finally:
        await retention.finish_reader(batch)


async def _verify_turns(adapter, identity, expected):
    for key, value in expected.get("turn_states", {}).items():
        if value.get("chat_id") is not None:
            actual_turn = await adapter.get_turn_state(
                identity[6],
                identity[4],
                {},
                key,
            )
            if actual_turn != value:
                raise ValueError("runtime cold Turn state differs")


async def _verify_session_messages(
    database,
    bundles,
    workspace,
    session,
    sid,
    *,
    io=None,
    io_workers=4,
):
    identity = session["identity"]
    expected = session["legacy"]["state"]
    rows = await database.fetch_all(
        "SELECT * FROM swe_conversation_messages WHERE session_id=%s AND layer<>%s ORDER BY session_order",
        (sid, "archive"),
    )
    from .importer import display_order_messages, extract_messages

    messages = extract_messages(
        expected,
        context_epoch=expected.get("context_epoch", 0),
    )
    session_chats = [
        item
        for item in workspace["chats"]
        if item["spec"]["session_id"] == identity[6]
        and item["spec"]["user_id"] == identity[4]
        and item["spec"]["channel"] == identity[5]
    ]
    if any(
        item["spec"]["meta"].get("session_kind") == "task"
        for item in session_chats
    ):
        task_projections(messages, expected)
    messages = display_order_messages(messages)
    if len(rows) != len(messages):
        raise ValueError("Session Message occurrence count differs")
    if io is None:
        bodies = [
            await _payload(
                database,
                bundles,
                row,
                "byte_offset",
                "byte_length",
                service_unit_id=workspace["scope"][0],
            )
            for row in rows
        ]
    else:
        bodies = await _payloads(
            database,
            bundles,
            rows,
            "byte_offset",
            "byte_length",
            service_unit_id=workspace["scope"][0],
            io=io,
            io_workers=io_workers,
        )
    for row, message, body in zip(rows, messages, bodies):
        if (
            body != message_body(message)
            or row["layer"] != message["layer"]
            or row["source_occurrence_no"] != message["source_occurrence_no"]
        ):
            raise ValueError("Message role/body/order/occurrence differs")


async def _verify_chat_projection(database, scope, spec):
    projection = await database.fetch_one(
        "SELECT c.external_session_key,c.metadata_text,c.status,"
        "s.external_session_key AS session_external_key "
        "FROM swe_conversation_chats c JOIN swe_conversation_sessions s "
        "ON s.id=c.session_id AND s.service_unit_key=c.service_unit_key "
        "WHERE c.service_unit_key=%s AND c.tenant_key=%s AND c.source_key=%s "
        "AND c.agent_key=%s AND c.external_chat_key=%s",
        (*scope.sql_values, spec["id"].encode("utf-8")),
    )
    expected_light, _ = split_metadata(spec["meta"])
    if (
        projection is None
        or projection["external_session_key"]
        != projection["session_external_key"]
        or projection["external_session_key"]
        != spec["session_id"].encode("utf-8")
        or validate_light_metadata(projection["metadata_text"])
        != expected_light
        or projection["status"] != "idle"
    ):
        raise ValueError("Chat summary SQL projection differs from source")


async def _verify_chat(
    database,
    bundles,
    manifest,
    workspace,
    chat,
    *,
    io=None,
    io_workers=4,
    messages_verified=False,
):
    scope = WorkspaceScope.from_values(workspace["scope"])
    await _verify_chat_projection(database, scope, chat["spec"])
    actual = await read_only_adapter(
        MySQLChatRepository(database, scope, bundles),
    ).get_chat(
        chat["spec"]["id"],
    )
    if chat["archive"]["deleted"]:
        if actual is not None:
            raise ValueError("deleted Chat was resurrected")
    elif actual is None or actual.model_dump(mode="json") != {
        **chat["spec"],
        "status": "idle",
    }:
        raise ValueError("Chat metadata/binding/identity/time differs")
    if not messages_verified:
        await _verify_archive_rows(
            database,
            bundles,
            manifest,
            chat,
            scope,
            io=io,
            io_workers=io_workers,
        )
    if not messages_verified:
        await _verify_epochs(database, bundles, manifest, chat, scope, io=io)
    if not chat["archive"]["deleted"]:
        await _verify_runtime_chat(database, bundles, scope, chat, workspace)


async def _verify_archive_rows(
    database,
    bundles,
    manifest,
    chat,
    scope,
    *,
    io=None,
    io_workers=4,
):
    cid = manifest.data["assignments"]["chat"][chat["position"]]["target_id"]
    rows = await database.fetch_all(
        "SELECT * FROM swe_conversation_messages WHERE archive_chat_id=%s ORDER BY archive_order",
        (cid,),
    )
    expected = [
        message
        for batch in archive_batches(chat["archive"])
        for message in batch["messages"]
    ]
    if len(rows) != len(expected):
        raise ValueError("archive occurrence count differs")
    if io is None:
        bodies = [
            await _payload(
                database,
                bundles,
                row,
                "byte_offset",
                "byte_length",
                service_unit_id=scope.service_unit_id,
            )
            for row in rows
        ]
    else:
        bodies = await _payloads(
            database,
            bundles,
            rows,
            "byte_offset",
            "byte_length",
            service_unit_id=scope.service_unit_id,
            io=io,
            io_workers=io_workers,
        )
    for body, message in zip(bodies, expected):
        if body != message:
            raise ValueError("archive message order/body differs")


async def _verify_epochs(database, bundles, manifest, chat, scope, *, io=None):
    for epoch in chat["archive"]["epochs"]:
        position = chat["position"] + "/epoch:" + str(epoch["epoch"])
        assignment = manifest.data["assignments"]["publication"][position]
        publication = await database.fetch_one(
            "SELECT * FROM swe_conversation_publications WHERE id=%s",
            (assignment["target_id"],),
        )
        if (
            publication is None
            or WorkspaceScope.from_row(publication) != scope
            or publication["checkpoint_revision"]
            != epoch["record"]["revision"]
            or publication["checkpoint_event_watermark"]
            != epoch["record"]["applied_event_sequence"]
        ):
            raise ValueError("checkpoint epoch/revision/watermark differs")
        index = (
            bundles.inspect(assignment["relative_path"])
            if io is None
            else await io.call(bundles.inspect, assignment["relative_path"])
        )
        extent = index.blocks["legacy_epoch"]
        (raw_epoch,) = await _read_extents(
            bundles,
            index.relative_path,
            (extent,),
            io=io,
        )
        actual_epoch = load_metadata_json(raw_epoch)
        if actual_epoch != epoch:
            raise ValueError("full checkpoint/event/epoch semantics differ")


async def _verify_runtime_chat(database, bundles, scope, chat, workspace):
    from types import SimpleNamespace
    from swe.app.runner import api
    from swe.app.runner.models import ChatSpec
    from swe.app.runner.turn_ledger import TurnHistorySnapshot

    spec = ChatSpec.model_validate(chat["spec"])
    history = HistoryStore(
        database,
        scope,
        bundles,
        cursor_secret=b"offline-verification",
    )
    read_only_adapter(history)
    actual = await history.current(spec.id)
    session = next(
        item
        for item in workspace["sessions"]
        if item["identity"][4:]
        == [spec.user_id, spec.channel, spec.session_id]
    )
    expected = await api._build_chat_history(
        spec,
        session=None,
        workspace=SimpleNamespace(workspace_dir=None),
        state=TurnHistorySnapshot(session["legacy"]["state"], spec.id),
        status_override="idle",
    )
    if [item.model_dump(mode="json") for item in actual.messages] != [
        item.model_dump(mode="json") for item in expected.messages
    ]:
        raise ValueError("runtime History current display semantics differ")
    await _verify_answer_turns(history, spec, expected.messages)
    await _verify_archived_questions(history, spec, expected.messages, chat)
    await _verify_archive_page(history, spec, chat)
    await _verify_checkpoint(database, bundles, scope, spec.id, chat)


async def _verify_answer_turns(history, spec, messages):
    from swe.app.runner import api

    questions = {
        api._message_original_id(message)
        for message in messages
        if message.role == "user"
    }
    for question in questions:
        if not question:
            continue
        expected = api._slice_answer_turn(messages, msgid=question)
        if expected is None:
            continue
        actual = await history.answer_turn(
            question,
            chat_id=spec.id,
            user_id=spec.user_id,
        )
        if [
            message.model_dump(mode="json") for message in actual.messages
        ] != [message.model_dump(mode="json") for message in expected]:
            raise ValueError(
                "runtime answer Turn source/fragment semantics differ",
            )


async def _verify_archived_questions(history, spec, messages, chat):
    from swe.app.runner import api

    current = {
        api._message_original_id(message)
        for message in messages
        if message.role == "user"
    }
    archived = {
        message.get("id")
        for batch in archive_batches(chat["archive"])
        for message in batch["messages"]
        if message.get("role") == "user"
    }
    for question in archived - current - {None, ""}:
        try:
            await history.answer_turn(
                question,
                chat_id=spec.id,
                user_id=spec.user_id,
            )
        except KeyError:
            continue
        raise ValueError(
            "fully archived question was selectable as current answer Turn",
        )


async def _verify_archive_page(history, spec, chat):
    from swe.app.runner import api

    observed = []
    cursor = None
    while True:
        page = await history.archive_page(spec.id, before=cursor, limit=50)
        observed[0:0] = page.messages
        if not page.has_more:
            break
        cursor = page.next_cursor
    rows = [
        message
        for batch in archive_batches(chat["archive"])
        for message in batch["messages"]
    ]
    converted = []
    for index, message in enumerate(rows):
        from agentscope.message import Msg

        converted.extend(
            api._history_msg_to_messages(
                [Msg.from_dict(message)],
                session_id=spec.id,
                position_offset=index,
            ),
        )
    converted = api._redact_hidden_context_messages(converted)
    if [item.model_dump(mode="json") for item in observed] != [
        item.model_dump(mode="json") for item in converted
    ]:
        raise ValueError("runtime History archive page semantics differ")


async def _verify_checkpoint(database, bundles, scope, chat_id, chat):
    if not chat["archive"]["epochs"]:
        return
    current = chat["archive"]["epochs"][0]
    reader = read_only_adapter(ArchiveReader(database, scope, bundles))
    events = (
        event
        for event in current["events"]
        if event["epoch"] == current["epoch"]
        and event["sequence"] > current["record"]["applied_event_sequence"]
    )
    missing = object()
    observed = False
    async for page in reader.iter_checkpoint_pages(chat_id):
        observed = True
        if page.record.to_dict() != current["record"]:
            raise ValueError("runtime checkpoint/event state differs")
        for event in page.events:
            if event.to_dict() != next(events, missing):
                raise ValueError("runtime checkpoint/event state differs")
    if not observed or next(events, missing) is not missing:
        raise ValueError("runtime checkpoint/event state differs")
