# -*- coding: utf-8 -*-
"""Monitor cron notification service tests."""

import inspect

from monitor.app.services.cron.notification_service import CronNotificationService


def test_claim_due_notifications_uses_skip_locked() -> None:
    """Claiming due notifications must skip rows locked by other workers."""
    source = inspect.getsource(
        CronNotificationService._claim_due_notification_ids,
    )

    assert "FOR UPDATE SKIP LOCKED" in source


def test_claim_due_notifications_requires_status_and_async_success() -> None:
    """领取待通知记录时必须同时满足主状态和异步状态成功。"""
    source = inspect.getsource(
        CronNotificationService._claim_due_notification_ids,
    )

    assert "e.status = 'success'" in source
    assert "e.async_status = 'success'" in source
    assert "e.need_notification = 1" in source


def test_fetch_claimed_notifications_rechecks_success_statuses() -> None:
    """发送前取回记录时也要复核主状态和异步状态。"""
    source = inspect.getsource(
        CronNotificationService._fetch_claimed_notifications,
    )

    assert "e.status = 'success'" in source
    assert "e.async_status = 'success'" in source
    assert "e.need_notification = 1" in source


def test_claim_due_notifications_filters_allowed_source_ids() -> None:
    """领取待通知记录时必须按配置的 source 范围过滤。"""
    source = inspect.getsource(
        CronNotificationService._claim_due_notification_ids,
    )

    assert "LEFT JOIN swe_cron_jobs" in source
    assert "j.source_id IN" in source


def test_claim_due_notifications_allows_empty_source_for_all_workers() -> None:
    """没有 source 的通知记录需要保留为所有实例都可领取。"""
    source = inspect.getsource(
        CronNotificationService._claim_due_notification_ids,
    )

    assert "j.source_id IS NULL" in source
    assert "j.source_id = ''" in source
