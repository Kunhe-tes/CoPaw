# -*- coding: utf-8 -*-
"""market admin 端点 POST /market/admin/skills/init-swe-skills 单元测试.

覆盖场景：
- user_ids=None：遍历 source_id 下所有用户目录（回归测试）
- user_ids 指定：仅处理指定用户
- source_ids=[]：直接返回
- dry_run=True：透传 dry_run 参数、不写库
- 单租户失败被吞到 errors，不影响其他租户

注意：process_tenant_skills 走 monkeypatch 替身，不真写数据库，避免依赖 MySQL。
_find_tenant_dirs_for_source_id 调用真实函数，确保目录遍历逻辑有测试兜底。
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app(tmp_path):
    """构造带路由的 FastAPI 应用，swe_root 指向 tmp_path。"""
    from market.app.routers.skills_market import router
    from market.database.connection import DatabaseConnection
    from market.marketplace.service import MarketplaceService

    mock_db = MagicMock(spec=DatabaseConnection)
    mock_db.is_connected = True
    mock_db.execute = AsyncMock(return_value=1)
    mock_db.fetch_one = AsyncMock(return_value=None)
    mock_db.fetch_all = AsyncMock(return_value=[])

    svc = MarketplaceService(
        db=mock_db,
        marketplace_root=tmp_path / "market",
        swe_root=tmp_path,
    )

    app = FastAPI()
    app.state.marketplace = svc
    app.include_router(router, prefix="/api")
    return app


def _write_skill(tenant_dir, skill_name: str = "demo") -> None:
    """在 tenant_dir/workspaces/default/skills/<skill_name> 下写入最小 SKILL.md + manifest。"""
    skill_dir = tenant_dir / "workspaces" / "default" / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\n---\n# demo",
        encoding="utf-8",
    )

    manifest_path = skill_dir.parent.parent / "skill.json"
    manifest_path.write_text(
        json.dumps(
            {
                "skills": {
                    skill_name: {"source": "customized", "enabled": True},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _capture_process(mp, return_value=None):
    """构造 monkeypatch 的 process_tenant_skills 替身。"""
    from market.marketplace import skill_sync

    captured: dict = {"calls": []}

    async def fake(tenant_dir, **kwargs):
        captured["calls"].append(
            {
                "tenant_dir_name": tenant_dir.name,
                "source_id": kwargs.get("source_id"),
                "force": kwargs.get("force"),
                "dry_run": kwargs.get("dry_run"),
                "write_manifest_back": kwargs.get("write_manifest_back", True),
            },
        )
        return return_value or {
            "tenant_id": tenant_dir.name,
            "total_workspaces": 1,
            "total_skills": 1,
            "synced": 1,
            "errors": [],
            "details": [],
        }

    mp.setattr(skill_sync, "process_tenant_skills", fake)
    return captured


def test_init_swe_skills_user_ids_none_returns_all_users_for_source(tmp_path):
    """回归测试：不传 user_ids 时，应遍历 swe_root 下属于该 source 的全部用户目录。

    覆盖 2bc40e98a 重构引入的隐藏 bug——原本 _find_tenant_dirs_for_source_id
    在 user_ids 为空时丢了遍历 swe_root 的逻辑，被错放到 init_swe_skills 末尾
    成为死代码，已在 f6aa49fc9 修复。
    """
    from market.runtime.context import encode_scope_id

    # 属于 paasuat source 的用户目录
    (tmp_path / "default_paasuat").mkdir()
    _write_skill(tmp_path / "default_paasuat")
    (tmp_path / encode_scope_id("alice", "paasuat")).mkdir()
    _write_skill(tmp_path / encode_scope_id("alice", "paasuat"))
    (tmp_path / encode_scope_id("bob", "paasuat")).mkdir()
    _write_skill(tmp_path / encode_scope_id("bob", "paasuat"))
    # 属于 other source 的用户目录——不应被匹配
    (tmp_path / encode_scope_id("carol", "other")).mkdir()
    _write_skill(tmp_path / encode_scope_id("carol", "other"))

    app = _make_app(tmp_path)
    client = TestClient(app)

    with pytest.MonkeyPatch.context() as mp:
        captured = _capture_process(mp)
        resp = client.post(
            "/api/market/admin/skills/init-swe-skills",
            json={"source_ids": ["paasuat"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    # 应匹配 3 个用户目录：default_paasuat + 2 个 encode_scope_id 用户
    assert data["total_users"] == 3
    assert data["processed"] == 3
    assert data["inserted_db"] == 3

    # carol 应被排除，其他 source 不在本次处理范围
    called_names = sorted(c["tenant_dir_name"] for c in captured["calls"])
    assert "default_paasuat" in called_names
    assert encode_scope_id("alice", "paasuat") in called_names
    assert encode_scope_id("bob", "paasuat") in called_names
    assert encode_scope_id("carol", "other") not in called_names
    assert len(captured["calls"]) == 3


def test_init_swe_skills_user_ids_filtered_returns_named_tenants_only(
    tmp_path,
):
    """指定 user_ids 时，仅处理该 user_ids 与 source_id 联合匹配的目录。"""
    from market.runtime.context import encode_scope_id

    (tmp_path / encode_scope_id("alice", "paasuat")).mkdir()
    _write_skill(tmp_path / encode_scope_id("alice", "paasuat"))
    (tmp_path / encode_scope_id("bob", "paasuat")).mkdir()
    _write_skill(tmp_path / encode_scope_id("bob", "paasuat"))

    app = _make_app(tmp_path)
    client = TestClient(app)

    with pytest.MonkeyPatch.context() as mp:
        captured = _capture_process(mp)
        resp = client.post(
            "/api/market/admin/skills/init-swe-skills",
            json={
                "source_ids": ["paasuat"],
                "user_ids": ["alice"],
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_users"] == 1
    assert data["processed"] == 1
    assert len(captured["calls"]) == 1
    assert captured["calls"][0]["tenant_dir_name"] == encode_scope_id(
        "alice",
        "paasuat",
    )


def test_init_swe_skills_empty_source_ids_returns_immediately(tmp_path):
    """source_ids=[] 时直接返回 results，不调用任何处理逻辑。"""
    app = _make_app(tmp_path)
    client = TestClient(app)

    with pytest.MonkeyPatch.context() as mp:
        captured = _capture_process(mp)
        resp = client.post(
            "/api/market/admin/skills/init-swe-skills",
            json={"source_ids": []},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_users"] == 0
    assert data["processed"] == 0
    assert data["inserted_db"] == 0
    assert captured["calls"] == []


def test_init_swe_skills_dry_run_skips_inserted_db(tmp_path):
    """dry_run=True 时 process_tenant_skills 应被以 dry_run=True 调用，且 inserted_db 不累加。"""
    from market.runtime.context import encode_scope_id

    (tmp_path / encode_scope_id("alice", "paasuat")).mkdir()
    _write_skill(tmp_path / encode_scope_id("alice", "paasuat"))

    app = _make_app(tmp_path)
    client = TestClient(app)

    # mock 即使 dry_run=True 也返回 synced=1，验证 init_swe_skills 不累加 inserted_db
    with pytest.MonkeyPatch.context() as mp:
        captured = _capture_process(
            mp,
            return_value={
                "tenant_id": "alice",
                "total_workspaces": 1,
                "total_skills": 1,
                "synced": 1,  # 即使 mock 返回 synced，dry_run 也应阻止写入累计
                "errors": [],
                "details": [],
            },
        )
        resp = client.post(
            "/api/market/admin/skills/init-swe-skills",
            json={"source_ids": ["paasuat"], "dry_run": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert data["processed"] == 1
    # dry_run=True 时不应累加 inserted_db，即使子函数返回 synced>0
    assert data["inserted_db"] == 0
    # dry_run 应作为 kwarg 透传给 process_tenant_skills
    assert captured["calls"][0]["dry_run"] is True


def test_init_swe_skills_one_tenant_failure_does_not_block_others(tmp_path):
    """单个租户失败被吞到 errors，不阻断其他租户处理。"""
    from market.marketplace import skill_sync
    from market.runtime.context import encode_scope_id

    alice_dir = tmp_path / encode_scope_id("alice", "paasuat")
    bob_dir = tmp_path / encode_scope_id("bob", "paasuat")
    alice_dir.mkdir()
    _write_skill(alice_dir)
    bob_dir.mkdir()
    _write_skill(bob_dir)

    app = _make_app(tmp_path)
    client = TestClient(app)

    with pytest.MonkeyPatch.context() as mp:

        async def selective_fake(tenant_dir, **kwargs):
            # alice 失败，bob 成功；用完整路径比较（encode_scope_id 是 base64
            # 形式，目录名是 "YWxpY2U.cGFhc3VhdA" 不含字面 "alice"）
            if tenant_dir == alice_dir:
                raise RuntimeError("mock failure for alice")
            return {
                "tenant_id": tenant_dir.name,
                "total_workspaces": 1,
                "total_skills": 1,
                "synced": 1,
                "errors": [],
                "details": [],
            }

        mp.setattr(skill_sync, "process_tenant_skills", selective_fake)
        resp = client.post(
            "/api/market/admin/skills/init-swe-skills",
            json={"source_ids": ["paasuat"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    # 两个用户都被遍历到
    assert data["total_users"] == 2
    # bob 成功处理
    assert data["processed"] == 1
    assert data["inserted_db"] == 1
    # alice 失败被记录到 errors，不抛异常
    assert len(data["errors"]) == 1
    assert (
        encode_scope_id("alice", "paasuat") in data["errors"][0]["tenant_id"]
    )
    assert "mock failure for alice" in data["errors"][0]["error"]


def test_init_swe_skills_logs_manifest_before_and_after_at_info_level(
    tmp_path,
    caplog,
):
    """验证 init_swe_skills 在每个 tenant 处理前后各打一条 info 日志，含 manifest 内容。

    日志是排查"为什么 swe_skills 与 skill.json 不一致"的关键入口，必须稳定输出。
    """
    from market.runtime.context import encode_scope_id

    tenant = tmp_path / encode_scope_id("alice", "paasuat")
    _write_skill(tenant, "demo")

    app = _make_app(tmp_path)
    client = TestClient(app)

    with pytest.MonkeyPatch.context() as mp:
        _capture_process(mp)
        with caplog.at_level(
            "INFO",
            logger="market.app.routers.skills_market",
        ):
            resp = client.post(
                "/api/market/admin/skills/init-swe-skills",
                json={"source_ids": ["paasuat"]},
            )

    assert resp.status_code == 200

    before_logs = [r for r in caplog.records if "manifest 之前" in r.message]
    after_logs = [r for r in caplog.records if "manifest 之后" in r.message]

    # 1 个 tenant → 1 条 before + 1 条 after
    assert len(before_logs) == 1, [r.message for r in caplog.records]
    assert len(after_logs) == 1

    # 两条日志都是 info 级别（不为 warning/error）
    assert before_logs[0].levelname == "INFO"
    assert after_logs[0].levelname == "INFO"

    # 日志内容含 tenant 名和 source_id
    assert encode_scope_id("alice", "paasuat") in before_logs[0].message
    assert "paasuat" in before_logs[0].message
    assert encode_scope_id("alice", "paasuat") in after_logs[0].message

    # 单 workspace 时不应再包一层 workspace 名，content 应是可解析的标准 JSON
    before_content = before_logs[0].message.split("content=", 1)[1]
    after_content = after_logs[0].message.split("content=", 1)[1]
    before_manifest = json.loads(before_content)
    after_manifest = json.loads(after_content)

    assert "default" not in before_manifest
    assert "default" not in after_manifest
    assert "demo" in before_manifest["skills"]
    assert "demo" in after_manifest["skills"]
