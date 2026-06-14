# -*- coding: utf-8 -*-
"""Hook runtime 内部消息构造工具。"""

from agentscope.message import Msg

HOOK_ADDITIONAL_CONTEXT_PREFIX = "[Hook additional context]"


def build_hook_additional_context_msg(content: str) -> Msg:
    """构造用于持久化 hook 附加上下文的 system 消息。"""
    return Msg(
        name="system",
        role="system",
        content=content,
    )
