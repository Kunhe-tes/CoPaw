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
