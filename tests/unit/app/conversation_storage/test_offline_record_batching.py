# -*- coding: utf-8 -*-
"""Offline publications store message batches in bundles, not SQL rows."""

import pytest

from swe.app.conversation_storage.errors import IntegrityError
from swe.app.conversation_storage.message_bundle import (
    decode_message_bodies,
    encode_message_bodies,
    split_message_batches,
)
from swe.app.conversation_storage.migration.install_records import (
    OfflineImportStore,
)
from tests.unit.app.conversation_storage.test_offline_commit_stages import (
    prepared,
)


@pytest.mark.parametrize("count", [0, 1, 100, 513])
def test_message_batches_round_trip_without_sql_rows(count):
    messages = [{"id": str(i), "content": "中文😀"} for i in range(count)]
    batches = list(split_message_batches(messages, max_bytes=4096))
    assert [message for batch in batches for message in batch] == messages
    assert [
        message
        for batch in batches
        for message in decode_message_bodies(encode_message_bodies(batch))
    ] == messages


def test_offline_plan_rejects_legacy_message_sql_record():
    with pytest.raises(
        IntegrityError,
        match="unknown typed field|not supported",
    ):
        OfflineImportStore._validate_typed_record(
            {"table": "messages", "values": {"id": 1}},
        )


async def test_failed_metadata_install_rolls_back_publication(tmp_path):
    store, operation, _ = await prepared(tmp_path)
    original = store._install

    async def fail(*args, **kwargs):
        await original(*args, **kwargs)
        raise IntegrityError("bad offline metadata")

    store._install = fail
    with pytest.raises(IntegrityError, match="bad offline metadata"):
        await store.commit(operation.operation_key)
    assert store.db.messages == []
    row = store.db.rows[operation.operation_key.encode()]
    assert row["state"] == "prepared"
