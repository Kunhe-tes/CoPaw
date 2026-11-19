# -*- coding: utf-8 -*-
"""Authorization before reporting oversized saved evidence."""

from unittest.mock import patch

import pytest

from swe.app.conversation_storage.history import HistoryStore
from tests.integrated.conversation_storage.test_archive_runtime_mysql import (
    setup,
    source,
)


@pytest.mark.asyncio
async def test_oversize_occurrence_authorizes_without_reading_message(
    conversation_test_database,
    tmp_path,
):
    database = conversation_test_database
    _, _, _, archive = await setup(database, tmp_path)
    message = source("large-evidence", "private " * 5000)
    await archive.append_message(
        "first",
        message,
        recovery_state={"revision": 0},
        authority=None,
    )
    history = HistoryStore(
        database,
        archive.scope,
        archive.reader.bundles,
        cursor_secret=b"evidence-truncation-test",
    )
    authorized = []

    def authorize(chat):
        authorized.append(chat.id)

    def deny(_chat):
        raise KeyError("not authorized")

    with patch.object(history, "_payloads", side_effect=AssertionError):
        result = await history.message_occurrence(
            "first",
            message.id,
            max_bytes=32 * 1024,
            authorize=authorize,
        )
        with pytest.raises(KeyError):
            await history.message_occurrence(
                "first",
                message.id,
                max_bytes=32 * 1024,
                authorize=deny,
            )

    assert result == {"status": "truncated", "message": None}
    assert authorized == ["first", "first"]
    pins = await database.fetch_one(
        "SELECT COUNT(*) AS total FROM swe_conversation_retentions "
        "WHERE kind='reader' AND state='active'",
    )
    assert pins["total"] == 0
