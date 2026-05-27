# -*- coding: utf-8 -*-
"""Hook runtime 内部消息构造工具。"""

from agentscope.message import Msg

HOOK_ADDITIONAL_CONTEXT_PREFIX = "[Hook additional context]"
HOOK_CONTEXT_ROLE = "developer"


def build_hook_additional_context_msg(content: str) -> Msg:
    """构造用于持久化 hook 附加上下文的 developer 消息。"""
    msg = Msg(
        name="system",
        role="system",
        content=content,
    )
    msg.role = HOOK_CONTEXT_ROLE
    return msg
