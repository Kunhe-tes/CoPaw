# -*- coding: utf-8 -*-
"""bootstrap 流程调用 sync_skills_to_db 的集成测试."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest


@pytest.fixture(name="mock_working_dir")
def _mock_working_dir(tmp_path, monkeypatch):
    """Mock WORKING_DIR to use tmp_path for isolation."""
    from swe import constant

    monkeypatch.setattr(constant, "WORKING_DIR", tmp_path / "swe")
    return tmp_path / "swe"


@pytest.mark.asyncio
async def test_bootstrap_calls_skill_sync(mock_working_dir):
    """ensure_bootstrap 完成后应触发 sync_skills_to_db。"""
    from swe.app.workspace.tenant_pool import TenantWorkspacePool

    pool = TenantWorkspacePool(mock_working_dir)

    with patch(
        "swe.app.workspace.tenant_pool.sync_skills_to_db",
        new=AsyncMock(),
    ) as mock_sync:
        await pool.ensure_bootstrap(tenant_id="alice")
        mock_sync.assert_awaited_once_with("alice")


@pytest.mark.asyncio
async def test_bootstrap_succeeds_when_skill_sync_fails(mock_working_dir):
    """sync 抛异常时 ensure_bootstrap 仍返回成功。"""
    from swe.app.workspace.tenant_pool import TenantWorkspacePool

    pool = TenantWorkspacePool(mock_working_dir)

    with patch(
        "swe.app.workspace.tenant_pool.sync_skills_to_db",
        new=AsyncMock(side_effect=ConnectionError("market down")),
    ):
        # 不应抛异常
        await pool.ensure_bootstrap(tenant_id="bob")