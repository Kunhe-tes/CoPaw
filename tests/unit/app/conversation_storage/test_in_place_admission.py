# -*- coding: utf-8 -*-
from pathlib import Path

import pytest

from swe.app.conversation_storage.errors import IntegrityError
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.in_place_admission import (
    require_workspace_boundary,
    tenant_write_boundaries,
)


def source(tmp_path):
    root = str(tmp_path)
    return {
        "services": [
            {
                "service_unit_id": "svc",
                "source_root": root,
                "original_root": root,
            },
        ],
        "workspaces": [
            {
                "service_unit_id": "svc",
                "tenant_id": tenant,
                "runtime_root": str(tmp_path / tenant / "workspace"),
                "evidence_refs": [str(tmp_path / tenant / "config.json")],
            }
            for tenant in ("alice", "bob")
        ],
    }


def test_separate_tenants_allow_shared_service_parent(tmp_path):
    data = source(tmp_path)
    boundaries = tenant_write_boundaries(data)
    assert len(boundaries) == 4
    require_workspace_boundary(
        data,
        WorkspaceScope("alice", "SRC", "new", service_unit_id="svc"),
        tmp_path / "alice" / "new",
    )
    # Parent mtime and writable bit are not tenant evidence ownership.
    (tmp_path / "ordinary-business-file").write_text("changed")
    assert tenant_write_boundaries(data) == boundaries


@pytest.mark.parametrize("conflict", ["workspace", "ancestor", "config"])
def test_cross_tenant_mutable_boundaries_are_rejected(tmp_path, conflict):
    data = source(tmp_path)
    a, b = data["workspaces"]
    if conflict == "workspace":
        b["runtime_root"] = a["runtime_root"]
    elif conflict == "ancestor":
        b["runtime_root"] = str(Path(a["runtime_root"]) / "child")
    else:
        b["evidence_refs"] = a["evidence_refs"]
    with pytest.raises(IntegrityError, match="share mutable"):
        tenant_write_boundaries(data)


def test_new_agent_cannot_join_other_tenant_frozen_workspace(tmp_path):
    data = source(tmp_path)
    scope = WorkspaceScope("alice", "SRC", "new", service_unit_id="svc")
    with pytest.raises(IntegrityError, match="another tenant"):
        require_workspace_boundary(data, scope, tmp_path / "bob" / "workspace")
    with pytest.raises(IntegrityError, match="another tenant"):
        require_workspace_boundary(data, scope, tmp_path / "bob")


def test_conflicting_b_c_does_not_block_unrelated_a(tmp_path):
    data = source(tmp_path)
    data["workspaces"].append(
        {
            **data["workspaces"][1],
            "tenant_id": "charlie",
        },
    )
    tenant_write_boundaries(data, tenant=("svc", "alice"))
    with pytest.raises(IntegrityError, match="share mutable"):
        tenant_write_boundaries(data, tenant=("svc", "bob"))
    with pytest.raises(IntegrityError, match="share mutable"):
        tenant_write_boundaries(data, tenant=("svc", "charlie"))


def test_real_tenant_evidence_conflicts_are_not_hidden_by_loop_variable(
    tmp_path,
):
    data = source(tmp_path)
    data["tenants"] = [
        {
            "service_unit_id": "svc",
            "tenant_id": tenant,
            "evidence_refs": [str(tmp_path / directory / "config.json")],
        }
        for tenant, directory in (
            ("alice", "alice"),
            ("bob", "shared"),
            ("charlie", "shared"),
        )
    ]
    tenant_write_boundaries(data, tenant=("svc", "alice"))
    for tenant in ("bob", "charlie"):
        with pytest.raises(IntegrityError, match="share mutable"):
            tenant_write_boundaries(data, tenant=("svc", tenant))
    with pytest.raises(IntegrityError, match="another tenant"):
        require_workspace_boundary(
            data,
            WorkspaceScope("alice", "SRC", "new", service_unit_id="svc"),
            tmp_path / "shared" / "new-agent",
        )
