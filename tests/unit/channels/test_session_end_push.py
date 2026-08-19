# -*- coding: utf-8 -*-
"""Unit tests for session-end push (_try_session_end_push)."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.channels.base import BaseChannel
from swe.config.config import ZhaohuConfig

PUSH_PREFIX = "https://wplus.example/detail"


def test_zhaohu_config_new_field_defaults():
    """New session-end push link fields have correct defaults."""
    cfg = ZhaohuConfig()
    assert cfg.session_end_push_link_prefix == ""
    assert cfg.session_end_push_link_id_type == "session_id"


def _build_zhaohu_cfg(
    *,
    enabled=True,
    prefix=PUSH_PREFIX,
    id_type="session_id",
):
    return SimpleNamespace(
        session_end_push_enabled=enabled,
        session_end_push_link_prefix=prefix,
        session_end_push_link_id_type=id_type,
    )


def _build_channel(zhaohu_cfg, chat_id="chat-1", raise_on_chat=False):
    zhaohu_ch = SimpleNamespace(send=AsyncMock())
    chat_mgr = AsyncMock()
    if raise_on_chat:
        chat_mgr.get_or_create_chat = AsyncMock(
            side_effect=RuntimeError("no chat"),
        )
    else:
        chat_mgr.get_or_create_chat = AsyncMock(
            return_value=SimpleNamespace(id=chat_id),
        )
    channel = object.__new__(BaseChannel)
    channel.channel = "console"
    channel._workspace = SimpleNamespace(
        _config=SimpleNamespace(
            channels=SimpleNamespace(zhaohu=zhaohu_cfg),
        ),
        channel_manager=AsyncMock(
            get_channel=AsyncMock(return_value=zhaohu_ch),
        ),
        chat_manager=chat_mgr,
    )
    return channel, zhaohu_ch


def _build_request(source_id="ruice", session_id="s1"):
    return SimpleNamespace(
        source_id=source_id,
        channel_meta={},
        session_id=session_id,
        user_id="u1",
        channel="console",
    )


@pytest.mark.asyncio
async def test_ruice_session_id_link_is_pushed():
    """ruice + prefix + session_id -> push with sessionId link."""
    zhaohu_cfg = _build_zhaohu_cfg(id_type="session_id")
    channel, zhaohu_ch = _build_channel(zhaohu_cfg)
    await channel._try_session_end_push(
        _build_request(),
        "user-1",
        reply_text="done",
    )
    zhaohu_ch.send.assert_called_once()
    meta = zhaohu_ch.send.call_args.args[2]
    assert meta["link_url"] == f"{PUSH_PREFIX}?sessionId=s1"
    assert meta["link_text"] == "点击查看详情"


@pytest.mark.asyncio
async def test_ruice_chat_id_link_is_pushed():
    """ruice + prefix + chat_id -> push with chatId link."""
    zhaohu_cfg = _build_zhaohu_cfg(id_type="chat_id")
    channel, zhaohu_ch = _build_channel(zhaohu_cfg, chat_id="chat-1")
    await channel._try_session_end_push(
        _build_request(),
        "user-1",
        reply_text="done",
    )
    zhaohu_ch.send.assert_called_once()
    meta = zhaohu_ch.send.call_args.args[2]
    assert meta["link_url"] == f"{PUSH_PREFIX}?chatId=chat-1"
    assert meta["link_text"] == "点击查看详情"


@pytest.mark.asyncio
async def test_ruice_chat_failure_falls_back_to_session_id():
    """chat lookup failure -> fall back to sessionId link."""
    zhaohu_cfg = _build_zhaohu_cfg(id_type="chat_id")
    channel, zhaohu_ch = _build_channel(
        zhaohu_cfg,
        raise_on_chat=True,
    )
    await channel._try_session_end_push(
        _build_request(),
        "user-1",
        reply_text="done",
    )
    zhaohu_ch.send.assert_called_once()
    meta = zhaohu_ch.send.call_args.args[2]
    assert meta["link_url"] == f"{PUSH_PREFIX}?sessionId=s1"


@pytest.mark.asyncio
async def test_ruice_without_any_link_is_skipped():
    """ruice + no prefix + no file link -> no push."""
    zhaohu_cfg = _build_zhaohu_cfg(prefix="")
    channel, zhaohu_ch = _build_channel(zhaohu_cfg)
    await channel._try_session_end_push(
        _build_request(),
        "user-1",
        reply_text="done",
    )
    zhaohu_ch.send.assert_not_called()


@pytest.mark.asyncio
async def test_ruice_with_file_link_pushes_without_jump_link():
    """ruice + no prefix + file link -> push link_items, no link_url."""
    os.environ["FILE_URL"] = "http://localhost:8088"
    zhaohu_cfg = _build_zhaohu_cfg(prefix="")
    channel, zhaohu_ch = _build_channel(zhaohu_cfg)
    reply = "see http://localhost:8088/static/scope/agent/report.pdf"
    await channel._try_session_end_push(
        _build_request(),
        "user-1",
        reply_text=reply,
    )
    zhaohu_ch.send.assert_called_once()
    meta = zhaohu_ch.send.call_args.args[2]
    assert "link_url" not in meta
    assert meta["link_items"] == [
        {
            "url": "http://localhost:8088/static/scope/agent/report.pdf",
            "text": "report.pdf",
        },
    ]


@pytest.mark.asyncio
async def test_non_ruice_without_link_is_pushed():
    """non-ruice (None source) + no link -> still pushed."""
    zhaohu_cfg = _build_zhaohu_cfg(prefix="")
    channel, zhaohu_ch = _build_channel(zhaohu_cfg)
    await channel._try_session_end_push(
        _build_request(source_id=None),
        "user-1",
        reply_text="done",
    )
    zhaohu_ch.send.assert_called_once()
    assert zhaohu_ch.send.call_args.args[2] is None


@pytest.mark.asyncio
async def test_invalid_id_type_falls_back_to_session_id():
    """invalid id_type -> treated as session_id."""
    zhaohu_cfg = _build_zhaohu_cfg(id_type="bad")
    channel, zhaohu_ch = _build_channel(zhaohu_cfg)
    await channel._try_session_end_push(
        _build_request(),
        "user-1",
        reply_text="done",
    )
    zhaohu_ch.send.assert_called_once()
    meta = zhaohu_ch.send.call_args.args[2]
    assert meta["link_url"] == f"{PUSH_PREFIX}?sessionId=s1"


@pytest.mark.asyncio
async def test_push_disabled_is_skipped():
    """session_end_push_enabled=False -> no push."""
    zhaohu_cfg = _build_zhaohu_cfg(enabled=False)
    channel, zhaohu_ch = _build_channel(zhaohu_cfg)
    await channel._try_session_end_push(
        _build_request(),
        "user-1",
        reply_text="done",
    )
    zhaohu_ch.send.assert_not_called()
