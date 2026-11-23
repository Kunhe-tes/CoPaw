# -*- coding: utf-8 -*-
"""Import a frozen Chat registry while leaving the original NAS files in place."""

from hashlib import sha256
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path
import json
from uuid import UUID, uuid4

from mysql.connector.errorcode import ER_CHECK_CONSTRAINT_VIOLATED
from mysql.connector.errors import (
    DatabaseError,
    DataError,
    IntegrityError as SQLIntegrityError,
)

from ...runner.expert_binding import (
    EXPERT_BINDING_META_KEY,
    read_expert_binding,
)
from ...runner.models import ChatsFile
from ...runner.session import session_filename
from ..chat_mutations import (
    CHAT_INSERT,
    chat_insert_values,
    highest_registry_order,
    load_metadata_json,
)
from ..metadata_catalog import _utc, SCOPE_WHERE
from ..errors import ConflictError
from ..paths import existing_root
from ..runtime import require_empty_conversation
from ..identity import (
    WorkspaceScope,
    SessionIdentity,
    chat_key_bytes,
    identity_bytes,
)
from .legacy import read_archive, read_session
from ..metadata_repository import (
    MySQLMetadataRepository,
    SOURCES,
    WORKSPACES,
    SOURCE_PREDICATE,
    SCOPE_PREDICATE,
    SESSION_INSERT,
    metadata_fields,
    metadata_install,
    session_filename_key,
)

MODE = "mysql-metadata"
BATCH_SIZE = 100
VERIFY_PAGE_SIZE = 100
EMPTY_REGISTRY_DIGEST = sha256(b"missing chats.json").hexdigest()
WORKSPACE_ERRORS = (
    ConflictError,
    ValueError,
    OSError,
    TypeError,
    DataError,
    SQLIntegrityError,
)


def _workspace(item):
    scope = WorkspaceScope.from_values(item["scope"])
    root = existing_root(item["root"])
    if root.resolve(strict=True) != root:
        raise ValueError("workspace root must be canonical")
    identity_bytes(str(root), 1024)
    return scope, root


def _registry_bytes(root):
    path = root / "chats.json"
    if not path.exists() and not path.is_symlink():
        require_empty_conversation(root)
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"expected a regular Chat registry at {path}")
    return path.read_bytes()


def _registry_digest(raw):
    return EMPTY_REGISTRY_DIGEST if raw is None else sha256(raw).hexdigest()


def _parse_registry(root, raw):
    if raw is None:
        return ChatsFile(version=1, chats=[])
    path = root / "chats.json"
    document = load_metadata_json(raw)
    if (
        not isinstance(document, dict)
        or type(document.get("version")) is not int
        or document["version"] != 1
    ):
        raise ValueError(f"unsupported Chat registry version at {path}")
    return ChatsFile.model_validate(document)


def _validate_chats(scope, chats):
    keys = set()
    sessions = {}
    for chat in chats:
        if str(UUID(chat.id)) != chat.id:
            raise ValueError(f"noncanonical Chat UUID {chat.id}")
        key = chat_key_bytes(chat.id)
        if key in keys:
            raise ValueError(f"duplicate Chat identity {chat.id}")
        keys.add(key)
        session = SessionIdentity(
            scope,
            chat.user_id,
            chat.channel,
            chat.session_id,
        )
        filename = session_filename(chat.session_id, chat.user_id)
        identity_bytes(filename, 255)
        if sessions.setdefault(filename, session) != session:
            raise ValueError(f"multiple Session identities map to {filename}")
        if len(chat.name.encode("utf-8")) > 65_535:
            raise ValueError(f"Chat {chat.id} title exceeds the SQL TEXT size")
        metadata_fields(chat.meta)
        binding = read_expert_binding(chat)
        if binding.expert_id is not None:
            identity_bytes(binding.expert_id, 256)


def prepare(workspaces, schema, manifest):
    bindings = []
    roots, scopes = set(), set()
    output = Path(manifest).resolve()
    for item in workspaces:
        scope = WorkspaceScope.from_values(item["scope"])
        root = Path(item["root"])
        if output.is_relative_to(root.resolve()):
            raise ValueError("manifest must be outside the Chat workspace")
        if root in roots or scope in scopes:
            raise ValueError("duplicate Chat workspace scope or path")
        roots.add(root)
        scopes.add(scope)
        binding = {"root": str(root), "scope": scope.values}
        try:
            _, root = _workspace(item)
            raw = _registry_bytes(root)
            binding["registry_sha256"] = _registry_digest(raw)
            if raw is None:
                binding["registry_missing"] = True
        except WORKSPACE_ERRORS as error:
            binding["prepare_error"] = str(error)
        bindings.append(binding)
    if not bindings:
        raise ValueError("at least one workspace is required")
    data = {
        "version": 1,
        "mode": MODE,
        "migration_id": str(uuid4()),
        "schema": schema,
        "workspaces": sorted(bindings, key=lambda item: item["scope"]),
    }
    _write_new_json(output, data)
    return data


def _write_new_json(path, data):
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with path.open("x", encoding="utf-8") as target:
        target.write(payload)


def read_manifest(path, schema):
    raw = Path(path).read_bytes()
    data = load_metadata_json(raw)
    if (
        not isinstance(data, dict)
        or data.get("mode") != MODE
        or data.get("version") != 1
    ):
        raise ValueError("invalid MySQL metadata manifest")
    if (
        data["schema"] != schema
        or str(UUID(data["migration_id"])) != data["migration_id"]
    ):
        raise ValueError("configured database or migration identity differs")
    bindings = data["workspaces"]
    if not bindings or len({tuple(item["scope"]) for item in bindings}) != len(
        bindings,
    ):
        raise ValueError(
            "migration manifest contains invalid workspace scopes",
        )
    return data, sha256(raw).digest()


def _verify_nas(root, registry, *, full_audit=False):
    sessions, dialog = root / "sessions", root / "dialog"
    for directory in (sessions, dialog):
        if directory.is_symlink() or (
            directory.exists() and not directory.is_dir()
        ):
            raise ValueError(f"invalid legacy storage directory {directory}")
    seen = set()
    for chat in registry.chats:
        session = sessions / session_filename(chat.session_id, chat.user_id)
        if session not in seen:
            seen.add(session)
            if session.is_symlink() or (
                session.exists() and not session.is_file()
            ):
                raise ValueError(f"invalid legacy Session file {session}")
            if full_audit and session.exists():
                _audit_legacy(read_session, session, trusted_root=root)
        if full_audit and dialog.exists():
            _audit_legacy(read_archive, dialog, chat.id, trusted_root=root)


def _audit_legacy(reader, path, *args, trusted_root):
    try:
        reader(path, *args, trusted_root=trusted_root)
    except (KeyError, IndexError, AttributeError) as error:
        location = path.joinpath(*args)
        raise ValueError(
            f"invalid legacy data at {location}: {error}",
        ) from error


def _frozen_registry(item, scope, root):
    raw = _registry_bytes(root)
    if (raw is None) != item.get("registry_missing", False) or (
        _registry_digest(raw) != item["registry_sha256"]
    ):
        raise ConflictError(
            f"Chat registry changed after preparation at {root}",
        )
    registry = _parse_registry(root, raw)
    _validate_chats(scope, registry.chats)
    return registry


def _verify_workspace(item, *, full_audit):
    if "prepare_error" in item:
        raise ValueError(item["prepare_error"])
    scope, root = _workspace(item)
    registry = _frozen_registry(item, scope, root)
    _verify_nas(root, registry, full_audit=full_audit)


async def migrate(
    database,
    manifest,
    manifest_digest,
    *,
    apply,
    full_audit=False,
    resume_from=None,
):
    def by_source(item):
        return tuple(item["scope"][:3])

    published, skipped, failed = [], [], []
    for key, group in groupby(
        sorted(manifest["workspaces"], key=by_source),
        key=by_source,
    ):
        workspaces = list(group)
        try:
            state, errors = await _migrate_source(
                database,
                manifest["migration_id"],
                manifest_digest,
                workspaces,
                apply=apply,
                full_audit=full_audit,
                resume_from=resume_from,
            )
        except (ConflictError, DataError, SQLIntegrityError) as error:
            failed.append({"source": key, "detail": str(error)})
            continue
        failed.extend(errors)
        if state == "skipped":
            skipped.append(key)
        elif state == "ready":
            published.append(key)
    return {
        "mode": MODE,
        "migration_id": manifest["migration_id"],
        "status": (
            "partial_success" if failed else ("ready" if apply else "preview")
        ),
        "published" if apply else "validated": published,
        "already_published": skipped,
        "failed": failed,
    }


def _workspace_failure(item, phase, error):
    return {
        "source": tuple(item["scope"][:3]),
        "scope": tuple(item["scope"]),
        "root": item["root"],
        "phase": phase,
        "detail": str(error),
    }


async def _check_resume_bindings(
    database,
    source_key,
    workspaces,
    row,
    resume_from,
):
    if resume_from is None:
        raise ConflictError(
            "source is bound to a different metadata migration",
        )
    original, original_digest = resume_from
    if (row["migration_id"], row["manifest_digest"]) != (
        original["migration_id"],
        original_digest,
    ):
        raise ConflictError(
            "resume manifest does not match the source binding",
        )
    source = tuple(workspaces[0]["scope"][:3])
    original_scopes = {
        tuple(item["scope"])
        for item in original["workspaces"]
        if tuple(item["scope"][:3]) == source
    }
    if {tuple(item["scope"]) for item in workspaces} != original_scopes:
        raise ConflictError(
            "resume manifest changes source workspace membership",
        )
    if row["published"]:
        raise ConflictError(
            "published source must retain its original manifest",
        )
    expected = {
        WorkspaceScope.from_values(item["scope"]).sql_values[-1]: item
        for item in workspaces
    }
    rows = await database.fetch_all(
        f"SELECT agent_key,workspace_root,registry_digest FROM {WORKSPACES} WHERE "
        + SOURCE_PREDICATE,
        source_key,
    )
    for binding in rows:
        item = expected.get(bytes(binding["agent_key"]))
        if (
            item is None
            or bytes(binding["workspace_root"]) != item["root"].encode()
            or bytes(binding["registry_digest"]).hex()
            != item.get("registry_sha256")
        ):
            raise ConflictError("resume manifest changes a bound workspace")


async def _migrate_source(
    database,
    migration_id,
    digest,
    workspaces,
    *,
    apply,
    full_audit,
    resume_from,
):
    source_key = WorkspaceScope.from_values(workspaces[0]["scope"]).sql_values[
        :3
    ]
    row = None
    replace_binding = False
    if apply:
        row = await database.fetch_one(
            f"SELECT migration_id,manifest_digest,published FROM {SOURCES} WHERE "
            + SOURCE_PREDICATE,
            source_key,
        )
        if row is not None:
            original_identity = (row["migration_id"], row["manifest_digest"])
            replace_binding = original_identity != (migration_id, digest)
            if replace_binding:
                await _check_resume_bindings(
                    database,
                    source_key,
                    workspaces,
                    row,
                    resume_from,
                )
            elif row["published"]:
                return "skipped", []

    eligible, failures = [], []
    for item in workspaces:
        try:
            _verify_workspace(item, full_audit=full_audit)
        except WORKSPACE_ERRORS as error:
            failures.append(_workspace_failure(item, "preflight", error))
        else:
            eligible.append(item)
    if not apply or not eligible:
        return ("failed" if failures else "ready"), failures

    if row is None:
        await database.execute(
            f"INSERT INTO {SOURCES} (service_unit_key,tenant_key,source_key,migration_id,manifest_digest) "
            "VALUES (%s,%s,%s,%s,%s)",
            (*source_key, migration_id, digest),
        )
    elif replace_binding:
        changed = await database.execute(
            f"UPDATE {SOURCES} SET migration_id=%s,manifest_digest=%s WHERE "
            + SOURCE_PREDICATE
            + " AND migration_id=%s AND manifest_digest=%s AND published=0",
            (migration_id, digest, *source_key, *original_identity),
        )
        if changed != 1:
            raise ConflictError("source binding changed during resume")
    for item in eligible:
        try:
            await _import_workspace(database, item)
            _verify_workspace(item, full_audit=full_audit)
        except WORKSPACE_ERRORS as error:
            failures.append(_workspace_failure(item, "import", error))
        except DatabaseError as error:
            if error.errno != ER_CHECK_CONSTRAINT_VIOLATED:
                raise
            failures.append(_workspace_failure(item, "import", error))
    if failures:
        return "failed", failures
    changed = await database.execute(
        f"UPDATE {SOURCES} SET published=1 WHERE "
        + SOURCE_PREDICATE
        + " AND migration_id=%s AND manifest_digest=%s AND published=0",
        (*source_key, migration_id, digest),
    )
    if changed != 1:
        raise ConflictError("source binding changed before publication")
    return "ready", []


async def _import_workspace(database, item):
    scope, root = _workspace(item)
    registry = _frozen_registry(item, scope, root)
    root_key = identity_bytes(str(root), 1024)
    digest = bytes.fromhex(item["registry_sha256"])
    repo = MySQLMetadataRepository(database, scope, importing=True)
    await database.execute(
        f"INSERT INTO {WORKSPACES} "
        "(service_unit_key,tenant_key,source_key,agent_key,workspace_root,registry_digest) "
        "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE imported_count=imported_count",
        (*scope.sql_values, root_key, digest),
    )
    while await _import_batch(repo, registry, root_key, digest):
        pass
    if not await _verify_import(repo, registry.chats):
        raise ConflictError(
            f"SQL Chat registry verification failed for {root}",
        )


def _normalized_chat(chat):
    meta = dict(chat.meta)
    binding = read_expert_binding(chat)
    meta.pop(EXPERT_BINDING_META_KEY, None)
    if binding.revision or binding.expert_id is not None:
        meta[EXPERT_BINDING_META_KEY] = binding.model_dump()
    return chat.model_copy(
        update={
            "meta": meta,
            "status": "idle",
            "created_at": _utc(chat.created_at),
            "updated_at": _utc(chat.updated_at),
        },
    )


async def _verify_import(repo, chats):
    index = 0
    order, row_id = 0, 0
    while True:
        rows = await repo.db.fetch_all(
            repo.select_chat + SCOPE_WHERE + " AND c.deleted_at IS NULL "
            "AND (c.registry_order>%s OR (c.registry_order=%s AND c.id>%s)) "
            "ORDER BY c.registry_order,c.id LIMIT %s",
            (*repo.scope.sql_values, order, order, row_id, VERIFY_PAGE_SIZE),
        )
        for row in rows:
            if index >= len(chats) or repo._spec(row) != _normalized_chat(
                chats[index],
            ):
                return False
            index += 1
        if len(rows) < VERIFY_PAGE_SIZE:
            return index == len(chats)
        order, row_id = rows[-1]["registry_order"], rows[-1]["id"]


async def _import_batch(repo, registry, root_key, digest):
    database, scope = repo.db, repo.scope
    async with database.transaction():
        await repo._assert_writes_allowed()
        row = await database.fetch_one(
            f"SELECT workspace_root,registry_digest,imported_count FROM {WORKSPACES} WHERE "
            + SCOPE_PREDICATE
            + " FOR UPDATE",
            scope.sql_values,
        )
        if (
            row["workspace_root"] != root_key
            or row["registry_digest"] != digest
        ):
            raise ConflictError(
                "workspace is bound to a different Chat registry",
            )
        start = row["imported_count"]
        if start > len(registry.chats):
            raise ConflictError(
                "workspace progress exceeds the frozen registry",
            )
        chats = registry.chats[start : start + BATCH_SIZE]
        if not chats:
            return False
        await _insert_chats(repo, chats)
        await database.execute(
            f"UPDATE {WORKSPACES} SET imported_count=%s WHERE "
            + SCOPE_PREDICATE,
            (start + len(chats), *scope.sql_values),
        )
        return True


async def _insert_chats(repo, chats):
    db, scope = repo.db, repo.scope
    keys = tuple(chat_key_bytes(chat.id) for chat in chats)
    placeholders = ",".join(["%s"] * len(keys))
    existing = await db.fetch_one(
        "SELECT external_chat_key FROM swe_conversation_chats WHERE "
        + SCOPE_PREDICATE
        + f" AND external_chat_key IN ({placeholders}) LIMIT 1",
        (*scope.sql_values, *keys),
    )
    if existing is not None:
        key = bytes(existing["external_chat_key"]).decode()
        raise ConflictError(
            f"target Chat {key} already exists outside the committed batch",
        )
    high = await highest_registry_order(db, scope)
    identities = [
        SessionIdentity(scope, chat.user_id, chat.channel, chat.session_id)
        for chat in chats
    ]
    sessions = await _insert_sessions(db, scope, identities)

    def rows():
        for order, (chat, identity) in enumerate(
            zip(chats, identities),
            high + 1,
        ):
            plan, extended = metadata_install(chat, chat.meta)
            yield (
                *chat_insert_values(scope, plan, sessions[identity], order),
                extended,
            )

    await db.insert_prepared(CHAT_INSERT, rows())


async def _insert_sessions(db, scope, identities):
    keys = {
        identity: session_filename_key(identity)
        for identity in dict.fromkeys(identities)
    }
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.insert_prepared(
        SESSION_INSERT,
        (
            (*identity.sql_values, name, now, now)
            for identity, name in keys.items()
        ),
    )
    names = tuple(dict.fromkeys(keys.values()))
    placeholders = ",".join(["%s"] * len(names))
    rows = await db.fetch_all(
        "SELECT id,user_key,channel_key,external_session_key,nas_filename "
        "FROM swe_conversation_sessions WHERE "
        + SCOPE_PREDICATE
        + f" AND nas_filename IN ({placeholders})",
        (*scope.sql_values, *names),
    )
    by_identity = {
        (row["user_key"], row["channel_key"], row["external_session_key"]): row
        for row in rows
    }
    sessions = {}
    for identity, name in keys.items():
        row = by_identity.get(identity.sql_values[4:])
        if row is None or row["nas_filename"] != name:
            raise ConflictError(
                "NAS Session filename belongs to another identity",
            )
        sessions[identity] = row
    return sessions


async def export(database, manifest, manifest_digest, destination):
    root = Path(destination).resolve()
    ready = []
    source_keys = sorted(
        {
            WorkspaceScope.from_values(item["scope"]).sql_values[:3]
            for item in manifest["workspaces"]
        },
    )
    async with database.transaction():
        for source_key in source_keys:
            source = await database.fetch_one(
                f"SELECT published,migration_id,manifest_digest FROM {SOURCES} WHERE "
                + SOURCE_PREDICATE,
                source_key,
            )
            if source is None or not source["published"]:
                continue
            if (
                source["migration_id"] != manifest["migration_id"]
                or source["manifest_digest"] != manifest_digest
            ):
                raise ConflictError(
                    "published source belongs to a different manifest",
                )
            bindings = await database.fetch_all(
                f"SELECT * FROM {WORKSPACES} WHERE "
                + SOURCE_PREDICATE
                + " ORDER BY agent_key",
                source_key,
            )
            for binding in bindings:
                scope = WorkspaceScope.from_row(binding)
                workspace_root = Path(
                    bytes(binding["workspace_root"]).decode(),
                )
                if root.is_relative_to(workspace_root):
                    raise ValueError(
                        "export must be outside the live workspace",
                    )
                data = await MySQLMetadataRepository(database, scope).load()
                ready.append((scope, workspace_root, data))
    if not ready:
        raise ConflictError("no published directory is available for export")
    root.mkdir()
    exported = []
    for index, (scope, workspace_root, data) in enumerate(ready):
        relative = Path(str(index)) / "chats.json"
        path = root / relative
        path.parent.mkdir()
        _write_new_json(path, data.model_dump(mode="json"))
        exported.append(
            {
                "scope": scope.values,
                "root": str(workspace_root),
                "registry": str(relative),
            },
        )
    _write_new_json(root / "report.json", {"workspaces": exported})
    return exported
