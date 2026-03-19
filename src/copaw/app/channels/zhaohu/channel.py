# -*- coding: utf-8 -*-
"""Built-in Zhaohu channel.

This first version only supports outbound push. CoPaw can proactively send
text messages to a Zhaohu push endpoint; inbound message handling is not
implemented yet.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional, Union

import httpx
from agentscope_runtime.engine.schemas.agent_schemas import (
    ContentType,
    TextContent,
)

from ....config.config import ZhaohuConfig as ZhaohuChannelConfig
from ..base import BaseChannel, OnReplySent, ProcessHandler

logger = logging.getLogger(__name__)

_TEXT_PART_LIMIT = 200
_SUMMARY_LIMIT = 50
_DEFAULT_CHANNEL = "ZH"
_DEFAULT_NET = "DMZ"
_DEFAULT_TIMEOUT = 15.0


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


def _normalize_text(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _chunk_text_values(text: str, limit: int = _TEXT_PART_LIMIT) -> list[str]:
    """Split text into text values under Zhaohu's 200-char limit."""
    normalized = _normalize_text(text)
    if not normalized:
        return [""]

    chunks: list[str] = []
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        if line:
            chunks.append(line)

    return chunks or [_truncate(normalized, limit)]


def _clean_payload(obj: Any) -> Any:
    """Remove None and empty-string values from nested payloads."""
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            cleaned = _clean_payload(value)
            if cleaned is None or cleaned == "" or cleaned == [] or cleaned == {}:
                continue
            out[key] = cleaned
        return out
    if isinstance(obj, list):
        out = []
        for item in obj:
            cleaned = _clean_payload(item)
            if cleaned is None or cleaned == {}:
                continue
            out.append(cleaned)
        return out
    return obj


class ZhaohuChannel(BaseChannel):
    """Official built-in Zhaohu channel (outbound push only)."""

    channel = "zhaohu"
    display_name = "Zhaohu"

    def __init__(
        self,
        process: ProcessHandler,
        enabled: bool,
        push_url: str,
        sys_id: str,
        robot_open_id: str,
        channel_code: str,
        net: str,
        request_timeout: float,
        bot_prefix: str,
        on_reply_sent: OnReplySent = None,
        show_tool_details: bool = True,
        filter_tool_messages: bool = False,
        filter_thinking: bool = False,
        dm_policy: str = "open",
        group_policy: str = "open",
        allow_from: Optional[list] = None,
        deny_message: str = "",
    ):
        super().__init__(
            process,
            on_reply_sent=on_reply_sent,
            show_tool_details=show_tool_details,
            filter_tool_messages=filter_tool_messages,
            filter_thinking=filter_thinking,
            dm_policy=dm_policy,
            group_policy=group_policy,
            allow_from=allow_from,
            deny_message=deny_message,
        )
        self.enabled = enabled
        self.push_url = push_url or ""
        self.sys_id = sys_id or ""
        self.robot_open_id = robot_open_id or ""
        self.channel_code = channel_code or _DEFAULT_CHANNEL
        self.net = net or _DEFAULT_NET
        self.request_timeout = max(float(request_timeout or 0), 1.0)
        self.bot_prefix = bot_prefix or ""

    @classmethod
    def from_env(
        cls,
        process: ProcessHandler,
        on_reply_sent: OnReplySent = None,
    ) -> "ZhaohuChannel":
        allow_from_env = os.getenv("ZHAOHU_ALLOW_FROM", "")
        allow_from = (
            [s.strip() for s in allow_from_env.split(",") if s.strip()]
            if allow_from_env
            else []
        )
        return cls(
            process=process,
            enabled=os.getenv("ZHAOHU_CHANNEL_ENABLED", "0") == "1",
            push_url=os.getenv("ZHAOHU_PUSH_URL", ""),
            sys_id=os.getenv("ZHAOHU_SYS_ID", ""),
            robot_open_id=os.getenv("ZHAOHU_ROBOT_OPEN_ID", ""),
            channel_code=os.getenv("ZHAOHU_CHANNEL", _DEFAULT_CHANNEL),
            net=os.getenv("ZHAOHU_NET", _DEFAULT_NET),
            request_timeout=float(
                os.getenv("ZHAOHU_REQUEST_TIMEOUT", str(_DEFAULT_TIMEOUT)),
            ),
            bot_prefix=os.getenv("ZHAOHU_BOT_PREFIX", ""),
            on_reply_sent=on_reply_sent,
            dm_policy=os.getenv("ZHAOHU_DM_POLICY", "open"),
            group_policy=os.getenv("ZHAOHU_GROUP_POLICY", "open"),
            allow_from=allow_from,
            deny_message=os.getenv("ZHAOHU_DENY_MESSAGE", ""),
        )

    @classmethod
    def from_config(
        cls,
        process: ProcessHandler,
        config: Union[ZhaohuChannelConfig, dict],
        on_reply_sent: OnReplySent = None,
        show_tool_details: bool = True,
        filter_tool_messages: bool = False,
        filter_thinking: bool = False,
    ) -> "ZhaohuChannel":
        c = config if isinstance(config, dict) else config.model_dump()

        def _get_str(key: str) -> str:
            return (c.get(key) or "").strip()

        return cls(
            process=process,
            enabled=bool(c.get("enabled", False)),
            push_url=_get_str("push_url"),
            sys_id=_get_str("sys_id"),
            robot_open_id=_get_str("robot_open_id"),
            channel_code=_get_str("channel") or _DEFAULT_CHANNEL,
            net=_get_str("net") or _DEFAULT_NET,
            request_timeout=float(
                c.get("request_timeout") or _DEFAULT_TIMEOUT,
            ),
            bot_prefix=_get_str("bot_prefix"),
            on_reply_sent=on_reply_sent,
            show_tool_details=show_tool_details,
            filter_tool_messages=filter_tool_messages,
            filter_thinking=filter_thinking,
            dm_policy=c.get("dm_policy") or "open",
            group_policy=c.get("group_policy") or "open",
            allow_from=c.get("allow_from") or [],
            deny_message=c.get("deny_message") or "",
        )

    def build_agent_request_from_native(self, native_payload: Any) -> Any:
        """Placeholder for future inbound support."""
        payload = native_payload if isinstance(native_payload, dict) else {}
        channel_id = payload.get("channel_id") or self.channel
        sender_id = payload.get("sender_id") or ""
        meta = payload.get("meta") or {}
        session_id = self.resolve_session_id(sender_id, meta)
        content_parts = payload.get("content_parts") or []

        if not content_parts:
            content_parts = [
                TextContent(
                    type=ContentType.TEXT,
                    text=payload.get("text", ""),
                ),
            ]

        request = self.build_agent_request_from_user_content(
            channel_id=channel_id,
            sender_id=sender_id,
            session_id=session_id,
            content_parts=content_parts,
            channel_meta=meta,
        )
        request.channel_meta = meta
        return request

    async def start(self) -> None:
        if not self.enabled:
            logger.debug("zhaohu channel disabled")
            return
        logger.info("zhaohu channel started (outbound push only)")

    async def stop(self) -> None:
        if not self.enabled:
            return
        logger.info("zhaohu channel stopped")

    async def send(
        self,
        to_handle: str,
        text: str,
        meta: Optional[dict] = None,
    ) -> None:
        """POST a Zhaohu push payload to the configured endpoint."""
        if not self.enabled:
            return
        if not self.push_url:
            logger.warning(
                "zhaohu send skipped: push_url not configured for %s",
                to_handle,
            )
            return
        if not self.sys_id or not self.robot_open_id:
            logger.warning(
                "zhaohu send skipped: sys_id or robot_open_id missing",
            )
            return

        payload = self._build_push_payload(to_handle, text, meta or {})
        timeout = httpx.Timeout(self.request_timeout, connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(self.push_url, json=payload)
            response.raise_for_status()
            try:
                data = response.json() if response.content else {}
            except ValueError:
                data = {}

        body = data.get("body") or []
        exp_msg_ids = [
            str(item.get("expMsgId"))
            for item in body
            if isinstance(item, dict) and item.get("expMsgId")
        ]
        logger.info(
            "zhaohu push ok: to=%s returnCode=%s expMsgIds=%s",
            to_handle,
            str(data.get("returnCode") or "(empty)"),
            exp_msg_ids,
        )

    def _build_push_payload(
        self,
        to_handle: str,
        text: str,
        meta: dict,
    ) -> dict:
        send_addr = str(meta.get("send_addr") or to_handle or "").strip()
        session_id = str(meta.get("session_id") or "").strip()
        send_pk = str(
            meta.get("send_pk")
            or f"{session_id}_{send_addr}".strip("_")
            or send_addr
        ).strip()

        normalized_text = _normalize_text(text)
        summary_line = (
            normalized_text.split("\n", 1)[0] if normalized_text else ""
        )
        summary = _truncate(summary_line or normalized_text, _SUMMARY_LIMIT)
        text_values = [{"text": chunk} for chunk in _chunk_text_values(text)]

        payload = {
            "baseInfo": {
                "sysId": self.sys_id,
                "ssnId": meta.get("ssn_id") or session_id,
                "ssnNo": meta.get("ssn_no"),
                "msgBigCls": meta.get("msg_big_cls"),
                "msgSmlCls": meta.get("msg_sml_cls"),
                "channel": self.channel_code,
                "robotOpenId": self.robot_open_id,
                "sendAddrs": [
                    {
                        "sendAddr": send_addr,
                        "sendPk": send_pk,
                    },
                ],
                "net": self.net,
            },
            "msgCtlInfo": {
                "configId": meta.get("config_id"),
                "batchId": meta.get("batch_id"),
            },
            "msgContent": {
                "summary": summary,
                "pushContent": summary,
                "message": [
                    {
                        "type": "txt",
                        "value": text_values,
                    },
                ],
            },
        }
        return _clean_payload(payload)
