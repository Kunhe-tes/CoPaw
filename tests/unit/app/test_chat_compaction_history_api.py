# -*- coding: utf-8 -*-
from types import SimpleNamespace
import uuid

import pytest
from agentscope.message import Msg

from swe.app.runner.api import _archive_metadata, _archive_page, _archive_store


def _message(index: int) -> Msg:
    message = Msg(
        name="user",
        role="user",
        content=f"old-{index}",
        timestamp=f"2026-08-01T12:00:{index:02d}+00:00",
    )
    message.id = f"old-{index}"
    return message


@pytest.mark.asyncio
async def test_archive_metadata_keeps_only_the_latest_adjacent_boundary(
    tmp_path,
) -> None:
    workspace = SimpleNamespace(workspace_dir=tmp_path)
    chat_id = str(uuid.uuid4())
    store = _archive_store(workspace)
    assert store is not None
    first = await store.commit(chat_id, [_message(1)])
    second = await store.commit(chat_id, [_message(2)])

    metadata = await _archive_metadata(workspace, chat_id)

    assert metadata.has_more is True
    assert [boundary.id for boundary in metadata.boundaries] == [second.id]
    assert metadata.boundaries[0].last_message_id == "old-2"
    assert first.id != second.id


@pytest.mark.asyncio
async def test_archive_page_returns_display_messages_and_respects_limit(
    tmp_path,
) -> None:
    workspace = SimpleNamespace(workspace_dir=tmp_path)
    chat_id = str(uuid.uuid4())
    store = _archive_store(workspace)
    assert store is not None
    await store.commit(chat_id, [_message(index) for index in range(55)])

    page = await _archive_page(workspace, chat_id, None, 50)

    assert [message.metadata["original_id"] for message in page.messages] == [
        f"old-{index}" for index in range(5, 55)
    ]
    assert page.has_more is True
    assert page.next_cursor is not None


@pytest.mark.asyncio
async def test_workspace_without_archive_root_preserves_empty_legacy_metadata() -> (
    None
):
    workspace = SimpleNamespace()

    assert (
        await _archive_metadata(workspace, str(uuid.uuid4()))
    ).model_dump() == {
        "has_more": False,
        "boundaries": [],
    }
