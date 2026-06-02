# -*- coding: utf-8 -*-
"""Source 系统配置请求上下文。"""

import logging
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Generator

from swe.config.config import ToolResultCompactConfig

from .registry import (
    FILE_READ_TRUNCATION_ENABLED_SETTING,
    FILE_READ_TRUNCATION_MAX_BYTES_SETTING,
    SourceSystemConfigSetting,
    normalize_registered_setting_values,
)
from .models import EffectiveSourceSystemConfig

_current_source_system_config: ContextVar[
    EffectiveSourceSystemConfig | None
] = ContextVar("current_source_system_config", default=None)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImmediateTruncationConfig:
    """运行时即时截断解析结果。"""

    enabled: bool
    max_bytes: int
    explicit: bool


@contextmanager
def bind_source_system_config(
    config: EffectiveSourceSystemConfig,
) -> Generator[None, None, None]:
    """在当前执行上下文绑定 source 系统配置。"""
    token = _current_source_system_config.set(config)
    try:
        yield
    finally:
        _current_source_system_config.reset(token)


def set_current_source_system_config(
    config: EffectiveSourceSystemConfig,
) -> Token[EffectiveSourceSystemConfig | None]:
    """设置当前 source 系统配置并返回 reset token。"""
    return _current_source_system_config.set(config)


def reset_current_source_system_config(
    token: Token[EffectiveSourceSystemConfig | None],
) -> None:
    """使用 token 还原当前 source 系统配置。"""
    _current_source_system_config.reset(token)


def get_current_source_system_config() -> EffectiveSourceSystemConfig | None:
    """读取当前上下文中的 source 系统配置。"""
    return _current_source_system_config.get()


def resolve_tool_result_compact_config(
    base_config: ToolResultCompactConfig,
    source_config: Any | None = None,
) -> ToolResultCompactConfig:
    """合成 Agent 运行配置和当前 source 的显式工具结果压缩覆盖。"""
    source_payload = _extract_tool_result_compact_override(source_config)
    if not source_payload:
        return base_config.model_copy(deep=True)

    payload = base_config.model_dump(mode="python")
    payload.update(source_payload)
    if payload["recent_max_bytes"] < payload["old_max_bytes"]:
        logger.warning(
            "Invalid source tool_result_compact thresholds resolved for "
            "source %s: recent_max_bytes=%s, old_max_bytes=%s; adjusted "
            "recent_max_bytes to old_max_bytes",
            _get_source_config_id(source_config),
            payload["recent_max_bytes"],
            payload["old_max_bytes"],
        )
        payload["recent_max_bytes"] = payload["old_max_bytes"]
    return ToolResultCompactConfig.model_validate(payload)


def resolve_file_read_truncation_config(
    tool_result_compact: ToolResultCompactConfig,
    source_config: Any | None = None,
) -> ImmediateTruncationConfig:
    """解析文件读取即时截断配置，缺失时兼容继承历史近期阈值。"""
    source_payload = _extract_immediate_truncation_override(
        "file_read_truncation",
        source_config,
    )
    if source_payload is None:
        return ImmediateTruncationConfig(
            enabled=True,
            max_bytes=tool_result_compact.recent_max_bytes,
            explicit=False,
        )
    return ImmediateTruncationConfig(
        enabled=bool(
            _get_immediate_truncation_value(
                source_payload,
                FILE_READ_TRUNCATION_ENABLED_SETTING,
            ),
        ),
        max_bytes=int(
            _get_immediate_truncation_value(
                source_payload,
                FILE_READ_TRUNCATION_MAX_BYTES_SETTING,
            ),
        ),
        explicit=True,
    )


def _get_source_config_id(source_config: Any | None) -> str:
    """尽量提取 source 标识，日志缺少上下文时回退为 unknown。"""
    config = (
        get_current_source_system_config()
        if source_config is None
        else source_config
    )
    source_id = getattr(config, "source_id", None)
    if isinstance(source_id, str) and source_id:
        return source_id
    return "unknown"


def _extract_tool_result_compact_override(
    source_config: Any | None,
) -> dict[str, Any]:
    """只读取 raw source 配置，避免 registered default 覆盖 Agent 配置。"""
    payload = _extract_raw_config_payload(source_config)
    if not payload:
        return {}

    tool_result_compact = payload.get("tool_result_compact")
    if not isinstance(tool_result_compact, dict):
        return {}
    normalized = normalize_registered_setting_values(
        {"tool_result_compact": tool_result_compact},
    )
    normalized_tool_result = normalized.get("tool_result_compact")
    if not isinstance(normalized_tool_result, dict):
        return {}
    return normalized_tool_result


def _extract_immediate_truncation_override(
    section: str,
    source_config: Any | None,
) -> dict[str, Any] | None:
    """读取即时截断 raw 配置对象，缺席时返回 None 以保留迁移语义。"""
    payload = _extract_raw_config_payload(source_config)
    raw_section = payload.get(section)
    if not isinstance(raw_section, dict):
        return None
    if "enabled" not in raw_section:
        return None
    normalized = normalize_registered_setting_values({section: raw_section})
    normalized_section = normalized.get(section)
    if not isinstance(normalized_section, dict):
        return None
    return normalized_section


def _get_immediate_truncation_value(
    payload: dict[str, Any],
    setting: SourceSystemConfigSetting,
) -> Any:
    """读取即时截断字段，保存裁剪后的 marker-only 配置回退到字段默认值。"""
    return payload.get(setting.path[-1], setting.default_value)


def _extract_raw_config_payload(source_config: Any | None) -> dict[str, Any]:
    """从显式 raw 配置中提取 dict，避免 effective defaults 混入覆盖判断。"""
    config = (
        get_current_source_system_config()
        if source_config is None
        else source_config
    )
    if config is None:
        return {}
    if isinstance(config, EffectiveSourceSystemConfig):
        raw_config = config.raw_config
        if raw_config is None:
            return {}
        return _extract_raw_config_payload(raw_config)
    if hasattr(config, "raw_config"):
        raw_config = getattr(config, "raw_config")
        if raw_config is None:
            return {}
        return _extract_raw_config_payload(raw_config)
    if hasattr(config, "as_dict"):
        return config.as_dict()
    if hasattr(config, "config") and not isinstance(config, dict):
        return _extract_raw_config_payload(getattr(config, "config"))
    if isinstance(config, dict):
        return dict(config)
    return {}
