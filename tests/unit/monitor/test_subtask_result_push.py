# -*- coding: utf-8 -*-
"""Tests for result-index user push after execution sync."""

import asyncio

from monitor.app.services.subtask import sync_service as sync_service_module
from monitor.app.services.subtask.sync_service import SyncService


class FakePushResponse:
    status_code = 200


class FakePushClient:
    def __init__(self):
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, url, headers=None, json=None):
        self.post_calls.append((url, headers, json))
        return FakePushResponse()


def test_push_result_index_users_deduplicates_and_posts(monkeypatch):
    client = FakePushClient()
    monkeypatch.setattr(
        sync_service_module,
        "RESULT_INDEX_PUSH_URL",
        "https://example.test/push",
    )
    monkeypatch.setattr(
        sync_service_module,
        "RESULT_INDEX_PUSH_PLUGIN_ID",
        "1",
    )
    monkeypatch.setattr(
        sync_service_module,
        "RESULT_INDEX_PUSH_PLUGIN_NAME",
        "skill-name",
    )
    monkeypatch.setattr(
        sync_service_module,
        "RESULT_INDEX_PUSH_QUESTION",
        "sample question",
    )
    monkeypatch.setattr(
        sync_service_module.httpx,
        "AsyncClient",
        lambda timeout: client,
    )

    asyncio.run(
        SyncService()._push_result_index_users(
            [
                {"custUid": "cust1", "bbkId": "110"},
                {"custUid": "cust1", "bbkId": "110"},
                {"custUid": "cust2", "bbkId": "121"},
            ],
        ),
    )

    assert client.post_calls == [
        (
            "https://example.test/push",
            {"Content-Type": "application/json"},
            {
                "pluginId": "1",
                "pluginName": "skill-name",
                "question": "sample question",
                "userInfoList": [
                    {"custUid": "cust1", "bbkId": "110"},
                    {"custUid": "cust2", "bbkId": "121"},
                ],
            },
        ),
    ]
