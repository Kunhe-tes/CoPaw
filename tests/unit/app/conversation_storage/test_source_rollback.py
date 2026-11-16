# -*- coding: utf-8 -*-
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.conversation_storage.errors import IntegrityError
from swe.app.conversation_storage.migration import tenant_rollback as rollback

JOB = "00000000-0000-4000-8000-000000000001"


def fixture(tmp_path):
    service = {"service_unit_id": "svc", "nas_root": str(tmp_path / "nas")}
    workspaces = []
    for name in ("A", "B"):
        root = tmp_path / name
        root.mkdir()
        (root / "agent.json").write_text('{"id":"agent"}')
        (root / "chats.json").write_text('{"chats":[]}')
        workspaces.append(
            {
                "service_unit_id": "svc",
                "tenant_id": "alice",
                "source_id": name,
                "agent_id": "agent",
                "root": str(root),
                "runtime_root": str(root),
            },
        )
    data = {
        "tenant_isolation": True,
        "source_isolation": True,
        "services": [service],
        "shares": [],
        "workspaces": workspaces,
        "tenants": [
            {
                "service_unit_id": "svc",
                "tenant_id": "alice",
                "source_id": name,
                "state": "discovered",
            }
            for name in ("A", "B")
        ],
    }
    rows = []
    for workspace in workspaces:
        name = workspace["source_id"]
        evidence = {
            "service": service,
            "workspaces": [workspace],
            "shares": [],
        }
        proof = {
            "version": 1,
            "migration_id": JOB,
            "services": {
                "svc": {
                    "nas_root": service["nas_root"],
                    "workspaces": [
                        {
                            "root": workspace["runtime_root"],
                            "scope": ["svc", "alice", name, "agent"],
                        },
                    ],
                },
            },
        }
        rows.append(
            {
                "service_unit_key": b"svc",
                "tenant_key": b"alice",
                "source_key": name.encode(),
                "state": "published" if name == "A" else "imported",
                "evidence_text": json.dumps(evidence),
                "verification_text": json.dumps(proof),
            },
        )
    return SimpleNamespace(migration_id=JOB, data=data), rows


async def test_source_authorities_do_not_promote_sibling_sql(
    tmp_path,
    monkeypatch,
):
    manifest, rows = fixture(tmp_path)
    binding = {
        "root": manifest.data["workspaces"][0]["root"],
        "scope": ["svc", "alice", "A", "agent"],
    }
    monkeypatch.setattr(
        rollback,
        "validate_current_config",
        lambda *_: [binding],
    )

    async def fetch(query, params=None):
        if "migration_sources" in query:
            return rows
        assert "SELECT DISTINCT" in query
        return [
            {
                "service_unit_key": b"svc",
                "tenant_key": b"alice",
                "source_key": source,
                "agent_key": b"agent",
            }
            for source in (b"A", b"B")
        ]

    db = SimpleNamespace(fetch_all=AsyncMock(side_effect=fetch))
    context = SimpleNamespace(
        data=manifest.data,
        manifest=manifest,
        database=db,
        current_configs=[{}],
    )
    registered, by_scope, published = await rollback._select_authorities(
        context,
    )
    assert registered == {("svc", "alice", "A"), ("svc", "alice", "B")}
    assert published == {("svc", "alice", "A")}
    assert set(by_scope) == {("svc", "alice", "A", "agent")}
    assert "migration_sources" in db.fetch_all.call_args_list[0].args[0]


@pytest.mark.parametrize(
    "change",
    ["evidence", "receipt_scope", "receipt_job", "missing", "duplicate"],
)
async def test_source_state_requires_exact_evidence(tmp_path, change):
    manifest, rows = fixture(tmp_path)
    if change == "evidence":
        evidence = json.loads(rows[0]["evidence_text"])
        evidence["workspaces"][0]["source_id"] = "B"
        rows[0]["evidence_text"] = json.dumps(evidence)
    elif change.startswith("receipt"):
        proof = json.loads(rows[0]["verification_text"])
        if change == "receipt_scope":
            proof["services"]["svc"]["workspaces"][0]["scope"][2] = "B"
        else:
            proof["migration_id"] = "00000000-0000-4000-8000-000000000002"
        rows[0]["verification_text"] = json.dumps(proof)
    elif change == "missing":
        del rows[0]["evidence_text"]
    else:
        rows.append(deepcopy(rows[0]))
    db = SimpleNamespace(fetch_all=AsyncMock(return_value=rows))
    with pytest.raises(IntegrityError, match="evidence|duplicated"):
        await rollback._publication_states(db, manifest)


def test_digest_checks_only_unpublished_source_and_custom_registry(
    tmp_path,
    monkeypatch,
):
    from pathlib import Path

    manifest, _ = fixture(tmp_path)
    a, b = manifest.data["workspaces"]
    root = Path(b["root"])
    b["registry_path"] = "custom.json"
    (root / "custom.json").write_text('{"chats":[]}')
    monkeypatch.setattr(rollback, "_frozen_configs", lambda *_: [])
    published = {("svc", "alice", "A")}
    before = rollback._rollback_input_digest(manifest.data, published, [])
    assert all(not path.startswith(a["root"]) for path, *_ in before)
    assert any(path.endswith("custom.json") for path, *_ in before)
    (root / "custom.json").write_text('{"chats":[1]}')
    assert before != rollback._rollback_input_digest(
        manifest.data,
        published,
        [],
    )


def test_share_authority_is_exact_source():
    share = {
        "token": "b",
        "tenant_id": "alice",
        "chat_id": "chat",
        "creator_id": "alice",
        "snapshot_key": "b.json",
        "created_at": None,
        "last_access_at": None,
        "access_count": 7,
    }
    context = SimpleNamespace(
        data={
            "source_isolation": True,
            "shares": [{**share, "service_unit_id": "svc", "source_id": "B"}],
            "source_shares": [share],
        },
        published={("svc", "alice", "A")},
        registered={("svc", "alice", "A"), ("svc", "alice", "B")},
        service_roots={"svc": object()},
    )
    actual = {**share, "service_unit_key": b"svc", "source_key": b"B"}
    owners, merged = rollback._select_share_records(context, [actual])
    assert owners == {"b": ("svc", "alice", "B")}
    assert merged == {"svc": {}}
    with pytest.raises(IntegrityError, match="ownership"):
        rollback._select_share_records(
            context,
            [{**actual, "source_key": b"A"}],
        )
    context.published.add(("svc", "alice", "B"))
    with pytest.raises(IntegrityError, match="missing"):
        rollback._select_share_records(
            context,
            [{**actual, "source_key": None}],
        )


def test_unpublished_copy_does_not_copy_published_sibling(
    tmp_path,
    monkeypatch,
):
    from pathlib import Path

    manifest, _ = fixture(tmp_path)
    service = manifest.data["services"][0]
    service["source_root"] = str(tmp_path)
    configs = []
    for name in ("A", "B"):
        path = tmp_path / name / "config.json"
        path.write_text("{}")
        path.chmod(0o444)
        configs.append((path, ("svc", "alice", name)))
    monkeypatch.setattr(rollback, "_frozen_configs", lambda *_: configs)
    seen = []
    monkeypatch.setattr(
        rollback,
        "_copy_workspace_inputs",
        lambda workspace, output: seen.append(workspace["source_id"]) or [],
    )
    output = tmp_path / "output"
    output.mkdir()
    context = SimpleNamespace(
        data=manifest.data,
        registered={("svc", "alice", "A"), ("svc", "alice", "B")},
        published={("svc", "alice", "A")},
        service_roots={"svc": output},
    )
    rollback._copy_unpublished(context)
    assert seen == ["B"]
    assert not (output / "A/config.json").exists()
    assert (output / "B/config.json").read_bytes() == b"{}"


async def test_share_query_resolves_only_live_committed_publication(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    db = SimpleNamespace(fetch_all=AsyncMock(return_value=[]))
    context = SimpleNamespace(
        database=db,
        data={"source_isolation": True, "shares": [], "services": []},
        registered=set(),
        published=set(),
        service_roots={"svc": output},
        by_scope={},
    )
    await rollback._merge_shares(context)
    query = db.fetch_all.call_args.args[0]
    assert "p.source_key" in query
    assert "p.id=s.publication_id" in query
    assert "p.service_unit_key=s.service_unit_key" in query
    assert "p.tenant_key=s.tenant_id" in query
    assert "p.state='committed'" in query and "p.gc_state='live'" in query


async def test_plan_requires_published_source_mapping_not_sibling(
    tmp_path,
    monkeypatch,
):
    from swe.app.conversation_storage.migration.exporter import OldFormatTarget
    from swe.app.conversation_storage.migration.manifest import SourceBoundary

    manifest, rows = fixture(tmp_path)
    monkeypatch.setattr(
        rollback,
        "validate_current_config",
        lambda *_: [
            {"root": "/current/B", "scope": ["svc", "alice", "B", "agent"]},
        ],
    )
    target = OldFormatTarget("old@sha256:" + "a" * 64, 2, 1)
    evidence = rollback.TenantRollbackEvidence(
        SourceBoundary(
            "stop",
            "2026-11-16T00:00:00Z",
            target.image_digest,
            ("review",),
        ),
        "stop",
        "drain",
        "review",
    )
    destination = tmp_path / "output"
    result = await rollback.plan_tenant_rollback(
        SimpleNamespace(fetch_all=AsyncMock(return_value=rows)),
        manifest,
        destination,
        target,
        evidence,
        current_configs=[{}],
    )
    assert (
        "published_tenant_current_config_missing"
        in result["unresolved_blockers"]
    )
    assert result["published_tenants"] == 1
    assert not result["passed"] and not result["mutated"]
    assert not destination.exists()


def test_frozen_config_ownership_retains_source_and_legacy_boundary(tmp_path):
    from swe.config.context import encode_scope_id

    for source in ("A", "B"):
        home = tmp_path / encode_scope_id("alice", source)
        home.mkdir()
        (home / "config.json").write_text("{}")
    service = {"service_unit_id": "svc", "config_root": str(tmp_path)}
    found = list(rollback._frozen_configs({"source_isolation": True}, service))
    assert {key for _, key in found} == {
        ("svc", "alice", "A"),
        ("svc", "alice", "B"),
    }
    legacy = list(rollback._frozen_configs({}, service))
    assert {key for _, key in legacy} == {("svc", "alice")}


@pytest.mark.parametrize("published", [False, True])
def test_legacy_share_empty_source_uses_frozen_token_owner(published):
    share = {
        "token": "legacy",
        "tenant_id": "alice",
        "chat_id": "chat",
        "creator_id": "alice",
        "snapshot_key": "legacy.json",
        "created_at": None,
        "last_access_at": None,
        "access_count": 7,
    }
    key = ("svc", "alice", "B")
    context = SimpleNamespace(
        data={
            "source_isolation": True,
            "shares": [{**share, "service_unit_id": "svc", "source_id": "B"}],
        },
        published={key} if published else {("svc", "alice", "A")},
        registered={key, ("svc", "alice", "A")},
        service_roots={"svc": object()},
    )
    actual = {
        **share,
        "service_unit_key": b"svc",
        "source_key": b"",
        "scope_kind": "legacy_share",
    }
    owners, merged = rollback._select_share_records(context, [actual])
    assert owners == {"legacy": key}
    assert ("legacy" in merged["svc"]) is published
    with pytest.raises(IntegrityError, match="ownership"):
        rollback._select_share_records(
            context,
            [{**actual, "source_key": b"A"}],
        )
    with pytest.raises(IntegrityError, match="ownership"):
        rollback._select_share_records(
            context,
            [{**actual, "token": "unmapped"}],
        )
    context.data["shares"].append(
        {**share, "service_unit_id": "svc", "source_id": "A"},
    )
    with pytest.raises(IntegrityError, match="ambiguous"):
        rollback._select_share_records(context, [actual])
