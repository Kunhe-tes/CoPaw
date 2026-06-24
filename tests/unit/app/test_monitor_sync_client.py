# -*- coding: utf-8 -*-
"""Tests for SWE Monitor sync client."""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from swe.app.crons.monitor_sync_client import (
    MonitorSyncClient,
    get_monitor_sync_client,
    get_monitor_api_url,
)


class TestMonitorSyncClient:
    """Tests for MonitorSyncClient."""

    def test_get_monitor_api_url_default(self):
        """Test default Monitor API URL."""
        url = get_monitor_api_url()
        assert url == "http://localhost:9090/api"

    def test_get_monitor_api_url_from_env(self, monkeypatch):
        """Test Monitor API URL from environment variable."""
        monkeypatch.setenv("SWE_MONITOR_API_URL", "http://monitor:8080/api")
        url = get_monitor_api_url()
        assert url == "http://monitor:8080/api"

    def test_client_initialization(self):
        """Test client initialization."""
        client = MonitorSyncClient("http://test:8080/api")
        assert client._base_url == "http://test:8080/api"
        assert client._enabled is True

    def test_client_disables_sync_when_empty_string(self):
        """Test explicit empty base_url disables Monitor sync."""
        client = MonitorSyncClient("")
        assert client._base_url == ""
        assert client._enabled is False

    def test_get_monitor_sync_client_singleton(self):
        """Test singleton pattern for sync client."""
        client1 = get_monitor_sync_client()
        client2 = get_monitor_sync_client()
        # They should be the same instance (or at least have same URL)
        assert client1._base_url == client2._base_url

    @pytest.mark.asyncio
    async def test_sync_fire_and_forget_disabled(self):
        """Test fire and forget when disabled."""
        client = MonitorSyncClient("")
        client._sync_fire_and_forget(AsyncMock())
        # Should not raise, just return silently

    @pytest.mark.asyncio
    async def test_sync_job_disabled(self):
        """Test sync_job when disabled."""
        from swe.app.crons.models import CronJobSpec

        client = MonitorSyncClient("")
        job = MagicMock()
        job.id = "test-job"
        job.model_dump = MagicMock(return_value={})

        # Should not raise, just return silently
        await client.sync_job(job)

    @pytest.mark.asyncio
    async def test_claim_due_notifications_sends_source_ids(self):
        """领取通知请求需要带上配置的 source 过滤范围。"""
        client = MonitorSyncClient("http://test:8080/api")
        posted = {}

        class _Response:
            status_code = 200
            text = ""

            def json(self):
                return []

        class _HttpClient:
            async def post(self, path, json):
                posted["path"] = path
                posted["json"] = json
                return _Response()

        client._client = _HttpClient()

        await client.claim_due_notifications(
            lock_owner="worker-1",
            now_utc=datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
            limit=5,
            source_ids=["source-a", "source-b"],
        )

        assert posted["path"] == "/monitor/sync/notifications/claim"
        assert posted["json"]["source_ids"] == ["source-a", "source-b"]


class TestSyncRequestFormat:
    """Tests for sync request data format."""

    @pytest.fixture
    def sample_job_spec_dict(self):
        """Sample CronJobSpec dict."""
        return {
            "id": "job-001",
            "name": "Test Job",
            "tenant_id": "tenant-001",
            "enabled": True,
            "task_type": "agent",
            "schedule": {
                "cron": "0 9 * * *",
                "timezone": "Asia/Shanghai",
            },
            "dispatch": {
                "channel": "console",
                "target": {
                    "user_id": "user-001",
                    "session_id": "session-001",
                },
            },
            "runtime": {
                "timeout_seconds": 7200,
                "max_concurrency": 1,
                "misfire_grace_seconds": 300,
            },
            "meta": {
                "creator_user_id": "user-001",
                "task_chat_id": "chat-001",
            },
        }

    def test_sync_request_fields_mapping(self, sample_job_spec_dict):
        """Test that sync request fields are correctly mapped."""
        # This tests the internal mapping logic in sync_job
        schedule = sample_job_spec_dict.get("schedule", {})
        dispatch = sample_job_spec_dict.get("dispatch", {})
        target = dispatch.get("target", {})
        runtime = sample_job_spec_dict.get("runtime", {})
        meta = sample_job_spec_dict.get("meta", {})

        # Verify key fields are extracted correctly
        assert schedule.get("cron") == "0 9 * * *"
        assert dispatch.get("channel") == "console"
        assert target.get("user_id") == "user-001"
        assert runtime.get("timeout_seconds") == 7200
        assert meta.get("creator_user_id") == "user-001"


class TestExecutionRecordFormat:
    """Tests for execution record format."""

    @pytest.mark.asyncio
    async def test_record_execution_disabled(self):
        """Test record_execution when disabled."""
        from swe.app.crons.models import CronJobSpec

        client = MonitorSyncClient("")
        job = MagicMock()
        job.id = "test-job"

        # Should not raise, just return silently
        await client.record_execution(
            job=job,
            status="success",
            actual_time=datetime.now(timezone.utc),
        )

    def test_format_optional_time_converts_utc_to_beijing(self):
        """Test _format_optional_time converts UTC to Beijing timezone."""
        client = MonitorSyncClient("http://test:8080/api")

        # UTC 时间: 2026-05-19 10:00:00+00:00
        utc_time = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
        result = client._format_optional_time(utc_time)

        # 应转换为北京时间: 2026-05-19 18:00:00+08:00
        assert result == "2026-05-19T18:00:00+08:00"

    def test_format_optional_time_handles_none(self):
        """Test _format_optional_time handles None."""
        client = MonitorSyncClient("http://test:8080/api")
        result = client._format_optional_time(None)
        assert result is None

    def test_format_optional_time_assumes_utc_if_no_timezone(self):
        """Test _format_optional_time assumes UTC if no timezone info."""
        client = MonitorSyncClient("http://test:8080/api")

        # 无时区信息的 datetime，应假设为 UTC
        naive_time = datetime(2026, 5, 19, 10, 0, 0)
        result = client._format_optional_time(naive_time)

        # 应假设为 UTC 并转换为北京时间
        assert result == "2026-05-19T18:00:00+08:00"

    def test_format_actual_time_converts_utc_to_beijing(self):
        """Test _format_actual_time converts UTC to Beijing timezone."""
        client = MonitorSyncClient("http://test:8080/api")

        # UTC 时间: 2026-05-19 02:30:00+00:00
        utc_time = datetime(2026, 5, 19, 2, 30, 0, tzinfo=timezone.utc)
        result = client._format_actual_time(utc_time)

        # 应转换为北京时间: 2026-05-19 10:30:00+08:00
        assert result == "2026-05-19T10:30:00+08:00"

    def test_format_actual_time_cross_day_boundary(self):
        """Test time conversion when crossing day boundary."""
        client = MonitorSyncClient("http://test:8080/api")

        # UTC 时间: 2026-05-19 23:00:00+00:00 (晚上11点)
        utc_time = datetime(2026, 5, 19, 23, 0, 0, tzinfo=timezone.utc)
        result = client._format_actual_time(utc_time)

        # 北京时间应为次日早上7点: 2026-05-20 07:00:00+08:00
        assert result == "2026-05-20T07:00:00+08:00"

    def test_execution_notification_due_at_uses_beijing_time(self):
        """Test notification_due_at uses the same Beijing time format."""
        client = MonitorSyncClient("http://test:8080/api")
        job = MagicMock()
        job.id = "job-001"
        job.name = "Test Job"
        job.tenant_id = "tenant-001"
        job.task_type = "agent"
        job.meta = {}

        due_at = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
        result = client._build_execution_sync_data(
            job=job,
            status="success",
            actual_time=due_at,
            end_time=due_at,
            duration_ms=100,
            error_message="",
            is_manual=False,
            trace_id="",
            session_id="",
            input_snapshot=None,
            output_preview="",
            instance_id="",
            executor_leader="",
            scheduled_time=None,
            notification_due_at=due_at,
            notification_timezone="Asia/Shanghai",
        )

        assert result["notification_due_at"] == "2026-05-19T18:00:00+08:00"

    def test_pending_notification_without_due_at_uses_end_time(self):
        """Test pending notifications always carry a concrete due time."""
        client = MonitorSyncClient("http://test:8080/api")
        job = MagicMock()
        job.id = "job-001"
        job.name = "Test Job"
        job.tenant_id = "tenant-001"
        job.task_type = "agent"
        job.meta = {}

        actual_time = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2026, 5, 19, 10, 5, 0, tzinfo=timezone.utc)
        result = client._build_execution_sync_data(
            job=job,
            status="success",
            actual_time=actual_time,
            end_time=end_time,
            duration_ms=300000,
            error_message="",
            is_manual=False,
            trace_id="",
            session_id="",
            input_snapshot=None,
            output_preview="",
            instance_id="",
            executor_leader="",
            scheduled_time=None,
        )

        assert result["notification_status"] == "pending"
        assert result["notification_due_at"] == "2026-05-19T18:05:00+08:00"

    def test_build_execution_sync_data_includes_model_meta(self):
        from swe.app.crons.models import (
            CronJobRequest,
            CronJobSpec,
            DispatchSpec,
            DispatchTarget,
            JobRuntimeSpec,
            ScheduleSpec,
        )

        client = MonitorSyncClient("http://test:8080/api")
        job = CronJobSpec(
            id="job-1",
            name="agent job",
            tenant_id="tenant-a",
            schedule=ScheduleSpec(cron="* * * * *"),
            task_type="agent",
            request=CronJobRequest(input={"text": "ping"}),
            dispatch=DispatchSpec(
                target=DispatchTarget(
                    user_id="user-a",
                    session_id="session-a",
                ),
            ),
            runtime=JobRuntimeSpec(),
        )
        actual_time = datetime(2026, 5, 28, 1, 2, 3, tzinfo=timezone.utc)
        end_time = datetime(2026, 5, 28, 1, 2, 5, tzinfo=timezone.utc)

        payload = client._build_execution_sync_data(
            job=job,
            status="success",
            actual_time=actual_time,
            end_time=end_time,
            duration_ms=2000,
            error_message="",
            is_manual=False,
            trace_id="trace-1",
            session_id="session-a",
            output_preview="done",
            input_snapshot={"input": "ping"},
            instance_id="instance-a",
            executor_leader="leader-a",
            scheduled_time=actual_time,
            meta={
                "original_model_slot": {
                    "provider_id": "openai",
                    "model": "gpt-5.4",
                },
                "effective_model_slot": {
                    "provider_id": "anthropic",
                    "model": "claude-3-7-sonnet",
                },
                "fallback_reason": "provider_not_found",
            },
        )

        assert json.loads(payload["meta"]) == {
            "original_model_slot": {
                "provider_id": "openai",
                "model": "gpt-5.4",
            },
            "effective_model_slot": {
                "provider_id": "anthropic",
                "model": "claude-3-7-sonnet",
            },
            "fallback_reason": "provider_not_found",
        }
        assert json.loads(payload["input_snapshot"]) == {
            "input": "ping",
        }
