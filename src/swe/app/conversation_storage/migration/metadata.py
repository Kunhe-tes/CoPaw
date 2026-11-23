# -*- coding: utf-8 -*-
"""Import a frozen Chat registry while leaving the original NAS files in place."""

from hashlib import sha256
from itertools import groupby
from pathlib import Path
import json
from uuid import UUID, uuid4

from ...runner.expert_binding import (
    EXPERT_BINDING_META_KEY,
    read_expert_binding,
)
from ...runner.models import ChatsFile
from ...runner.session import session_filename
from ..chat_mutations import load_metadata_json
from ..metadata_catalog import _utc
from ..errors import ConflictError
from ..paths import existing_root
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
    metadata_fields,
)

MODE = "mysql-metadata"
BATCH_SIZE = 100


def _workspace(item):
    scope = WorkspaceScope.from_values(item["scope"])
    root = existing_root(item["root"])
    if root.resolve(strict=True) != root:
        raise ValueError("workspace root must be canonical")
    identity_bytes(str(root), 1024)
    return scope, root


def _registry(root):
    path = root / "chats.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"expected a regular Chat registry at {path}")
    raw = path.read_bytes()
    document = load_metadata_json(raw)
    if (
        not isinstance(document, dict)
        or type(document.get("version")) is not int
        or document["version"] != 1
    ):
        raise ValueError(f"unsupported Chat registry version at {path}")
    return ChatsFile.model_validate(document), sha256(raw).hexdigest()


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
        metadata_fields(chat.meta)
        binding = read_expert_binding(chat)
        if binding.expert_id is not None:
            identity_bytes(binding.expert_id, 256)


def prepare(workspaces, schema, manifest):
    bindings = []
    roots, scopes = set(), set()
    output = Path(manifest).resolve()
    for item in workspaces:
        scope, root = _workspace(item)
        if output.is_relative_to(root):
            raise ValueError("manifest must be outside the Chat workspace")
        if root in roots or scope in scopes:
            raise ValueError("duplicate Chat workspace scope or path")
        roots.add(root)
        scopes.add(scope)
        registry, digest = _registry(root)
        _validate_chats(scope, registry.chats)
        bindings.append(
            {
                "root": str(root),
                "scope": scope.values,
                "registry_sha256": digest,
            },
        )
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
                read_session(session, trusted_root=root)
        if full_audit and dialog.exists():
            read_archive(dialog, chat.id, trusted_root=root)


def _frozen_registry(item, scope, root):
    registry, digest = _registry(root)
    if digest != item["registry_sha256"]:
        raise ConflictError(
            f"Chat registry changed after preparation at {root}",
        )
    _validate_chats(scope, registry.chats)
    return registry


def _verify_workspace(item, *, full_audit):
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
            if apply:
                changed = await _migrate_source(
                    database,
                    manifest["migration_id"],
                    manifest_digest,
                    workspaces,
                    full_audit=full_audit,
                )
                if not changed:
                    skipped.append(key)
                    continue
            else:
                for item in workspaces:
                    _verify_workspace(item, full_audit=full_audit)
        except (ConflictError, ValueError, OSError, TypeError) as error:
            failed.append({"source": key, "detail": str(error)})
        else:
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


async def _migrate_source(
    database,
    migration_id,
    digest,
    workspaces,
    *,
    full_audit,
):
    scope, _ = _workspace(workspaces[0])
    source_key = scope.sql_values[:3]
    row = await database.fetch_one(
        f"SELECT migration_id,manifest_digest,published FROM {SOURCES} WHERE "
        + SOURCE_PREDICATE,
        source_key,
    )
    if row is not None:
        if (
            row["migration_id"] != migration_id
            or row["manifest_digest"] != digest
        ):
            raise ConflictError(
                "source is bound to a different metadata migration",
            )
        if row["published"]:
            return False
    else:
        for item in workspaces:
            _verify_workspace(item, full_audit=full_audit)
        await database.execute(
            f"INSERT INTO {SOURCES} (service_unit_key,tenant_key,source_key,migration_id,manifest_digest) "
            "VALUES (%s,%s,%s,%s,%s)",
            (*source_key, migration_id, digest),
        )
    for item in workspaces:
        await _import_workspace(database, item)
    for item in workspaces:
        _verify_workspace(item, full_audit=full_audit)
    await database.execute(
        f"UPDATE {SOURCES} SET published=1 WHERE "
        + SOURCE_PREDICATE
        + " AND migration_id=%s AND manifest_digest=%s AND published=0",
        (*source_key, migration_id, digest),
    )
    return True


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
    expected = []
    for chat in registry.chats:
        normalized = chat.model_copy(
            deep=True,
            update={
                "status": "idle",
                "created_at": _utc(chat.created_at),
                "updated_at": _utc(chat.updated_at),
            },
        )
        binding = read_expert_binding(chat)
        normalized.meta.pop(EXPERT_BINDING_META_KEY, None)
        if binding.revision or binding.expert_id is not None:
            normalized.meta[EXPERT_BINDING_META_KEY] = binding.model_dump()
        expected.append(normalized)
    if await repo.list_chats() != expected:
        raise ConflictError(
            f"SQL Chat registry verification failed for {root}",
        )


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
        chats = registry.chats[start : start + BATCH_SIZE]
        for chat in chats:
            if await repo._raw_chat(chat.id) is not None:
                raise ConflictError(
                    f"target Chat {chat.id} already exists outside the committed batch",
                )
            session = await repo._session_for(chat)
            await repo._install(chat, session, None)
        if chats:
            await database.execute(
                f"UPDATE {WORKSPACES} SET imported_count=%s WHERE "
                + SCOPE_PREDICATE,
                (start + len(chats), *scope.sql_values),
            )
        return bool(chats)


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
