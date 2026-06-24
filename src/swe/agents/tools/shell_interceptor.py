# -*- coding: utf-8 -*-
"""Shell 命令拦截器。

该模块负责在 Agent 执行特定 shell 命令前，按当前租户、来源和用户
上下文自动补充隔离参数，避免 cron 等命令落到错误的运行时范围。
"""

from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass
from typing import List, Tuple

from ...config.context import (
    get_current_source_id,
    get_current_tenant_id,
    get_current_user_id,
)

logger = logging.getLogger(__name__)


@dataclass
class InterceptRule:
    """描述一个 shell 命令拦截规则。"""

    command_prefix: str
    inject_params: List[str]
    inject_position: str = "after_subcommand"


# 更具体的规则放在前面，避免被通用前缀提前匹配。
INTERCEPT_RULES: List[InterceptRule] = [
    InterceptRule(
        command_prefix="swe cron create",
        inject_params=[
            "--tenant-id",
            "--source-id",
            "--target-user",
            "--creator-user",
        ],
        inject_position="at_end",
    ),
    InterceptRule(
        command_prefix="swe cron",
        inject_params=["--tenant-id", "--source-id"],
        inject_position="at_end",
    ),
]


def _has_param(tokens: List[str], param_name: str) -> bool:
    """检查命令中是否已经显式传入指定参数。"""

    for token in tokens:
        if token.startswith(f"{param_name}="):
            return True
        if token == param_name:
            return True
    return False


def _is_swe_cron_group_help(tokens: List[str]) -> bool:
    """cron 组级帮助命令不注入租户参数，避免破坏 help 输出。"""

    return (
        len(tokens) == 3
        and tokens[0] == "swe"
        and tokens[1] == "cron"
        and tokens[2] in {"-h", "--help"}
    )


def _split_by_shell_and(command: str) -> List[str]:
    """按未被引号包裹的 && 拆分命令，并保留分隔符用于原样拼回。"""

    parts: List[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote is not None:
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if (
            char == "&"
            and index + 1 < len(command)
            and command[index + 1] == "&"
        ):
            parts.append(command[start:index])
            parts.append("&&")
            index += 2
            start = index
            continue
        index += 1
    parts.append(command[start:])
    return parts


def _build_inject_parts(
    tokens: List[str],
    rule: InterceptRule,
    *,
    tenant_id: str | None,
    source_id: str | None,
    user_id: str | None,
) -> List[str]:
    """根据当前上下文构造需要追加的参数片段。"""

    inject_parts: List[str] = []
    for param in rule.inject_params:
        if _has_param(tokens, param):
            logger.debug(
                "Shell interceptor: skipping %s, already exists in command",
                param,
            )
            continue
        if param == "--tenant-id" and tenant_id:
            inject_parts.append(f"{param} {tenant_id}")
        elif param == "--source-id" and source_id:
            inject_parts.append(f"{param} {source_id}")
        elif param == "--target-user" and user_id:
            inject_parts.append(f"{param} {user_id}")
        elif param == "--creator-user" and user_id:
            inject_parts.append(f"{param} {user_id}")
        elif param == "--user-id" and user_id:
            inject_parts.append(f"{param} {user_id}")
    return inject_parts


def _intercept_command_segment(
    command: str,
    *,
    tenant_id: str | None,
    source_id: str | None,
    user_id: str | None,
) -> Tuple[str, bool]:
    """只处理单个 shell 命令段，避免把参数加到链式命令的错误位置。"""

    leading = command[: len(command) - len(command.lstrip())]
    trailing = command[len(command.rstrip()) :]
    command_body = command.strip()
    if not command_body:
        return command, False

    try:
        tokens = shlex.split(command_body)
    except ValueError:
        return command, False

    if not tokens or _is_swe_cron_group_help(tokens):
        return command, False

    for rule in INTERCEPT_RULES:
        prefix_tokens = rule.command_prefix.split()
        if tokens[: len(prefix_tokens)] != prefix_tokens:
            continue

        inject_parts = _build_inject_parts(
            tokens,
            rule,
            tenant_id=tenant_id,
            source_id=source_id,
            user_id=user_id,
        )
        if not inject_parts:
            return command, False

        if rule.inject_position == "at_end":
            modified_body = command_body + " " + " ".join(inject_parts)
        else:
            insert_pos = len(prefix_tokens)
            inject_tokens = shlex.split(" ".join(inject_parts))
            tokens = tokens[:insert_pos] + inject_tokens + tokens[insert_pos:]
            modified_body = shlex.join(tokens)
        return leading + modified_body + trailing, True

    return command, False


def intercept_command(command: str) -> Tuple[str, bool]:
    """按当前请求上下文为匹配的 shell 命令注入隔离参数。

    支持单条命令和 ``xxx && swe cron ...`` 形式的链式命令；只修改真正
    命中的命令段，不把参数追加到整条 shell 命令末尾。
    """

    tenant_id = get_current_tenant_id()
    source_id = get_current_source_id()
    user_id = get_current_user_id()

    if tenant_id is None and user_id is None:
        return command, False

    parts = _split_by_shell_and(command)
    modified_parts: List[str] = []
    was_intercepted = False
    for part in parts:
        if part == "&&":
            modified_parts.append(part)
            continue
        modified_part, part_intercepted = _intercept_command_segment(
            part,
            tenant_id=tenant_id,
            source_id=source_id,
            user_id=user_id,
        )
        modified_parts.append(modified_part)
        was_intercepted = was_intercepted or part_intercepted

    if not was_intercepted:
        return command, False

    modified_command = "".join(modified_parts)
    logger.info(
        "Shell command intercepted: %s -> %s",
        command,
        modified_command,
    )
    return modified_command, True
