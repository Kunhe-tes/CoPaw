# -*- coding: utf-8 -*-
"""Source 系统配置注册表与默认值裁剪规则。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class SourceSystemConfigSetting:
    """描述一个受代码注册管理的 source 系统配置项。"""

    key: str
    path: tuple[str, ...]
    default_value: Any
    value_type: Literal["bool", "int", "str"]
    ge: int | None = None
    le: int | None = None


SourceSystemConfigSwitch = SourceSystemConfigSetting


CHAT_TASK_PROGRESS_ENABLED_SWITCH = SourceSystemConfigSwitch(
    key="feature_switches.chat_task_progress_enabled",
    path=("feature_switches", "chat_task_progress_enabled"),
    default_value=True,
    value_type="bool",
)

TOOL_RESULT_COMPACT_ENABLED_SETTING = SourceSystemConfigSetting(
    key="tool_result_compact.enabled",
    path=("tool_result_compact", "enabled"),
    default_value=True,
    value_type="bool",
)
TOOL_RESULT_COMPACT_RECENT_N_SETTING = SourceSystemConfigSetting(
    key="tool_result_compact.recent_n",
    path=("tool_result_compact", "recent_n"),
    default_value=2,
    value_type="int",
    ge=1,
    le=10,
)
TOOL_RESULT_COMPACT_OLD_MAX_BYTES_SETTING = SourceSystemConfigSetting(
    key="tool_result_compact.old_max_bytes",
    path=("tool_result_compact", "old_max_bytes"),
    default_value=3000,
    value_type="int",
    ge=100,
)
TOOL_RESULT_COMPACT_RECENT_MAX_BYTES_SETTING = SourceSystemConfigSetting(
    key="tool_result_compact.recent_max_bytes",
    path=("tool_result_compact", "recent_max_bytes"),
    default_value=50000,
    value_type="int",
    ge=1000,
)
TOOL_RESULT_COMPACT_RETENTION_DAYS_SETTING = SourceSystemConfigSetting(
    key="tool_result_compact.retention_days",
    path=("tool_result_compact", "retention_days"),
    default_value=5,
    value_type="int",
    ge=1,
    le=10,
)

DATABASE_ACCESS_GUARD_ENABLED_SWITCH = SourceSystemConfigSwitch(
    key="feature_switches.database_access_guard_enabled",
    path=("feature_switches", "database_access_guard_enabled"),
    default_value=True,
    value_type="bool",
)
APPROVAL_NOTIFICATIONS_ZHAOHU_TOOL_GUARD_ENABLED_SETTING = (
    SourceSystemConfigSetting(
        key="approval_notifications.zhaohu_tool_guard_enabled",
        path=("approval_notifications", "zhaohu_tool_guard_enabled"),
        default_value=False,
        value_type="bool",
    )
)
FILE_READ_TRUNCATION_ENABLED_SETTING = SourceSystemConfigSetting(
    key="file_read_truncation.enabled",
    path=("file_read_truncation", "enabled"),
    default_value=True,
    value_type="bool",
)
FILE_READ_TRUNCATION_MAX_BYTES_SETTING = SourceSystemConfigSetting(
    key="file_read_truncation.max_bytes",
    path=("file_read_truncation", "max_bytes"),
    default_value=50000,
    value_type="int",
    ge=1000,
)

CRON_UNREAD_AUTO_PAUSE_ENABLED_SETTING = SourceSystemConfigSetting(
    key="cron_unread_auto_pause.enabled",
    path=("cron_unread_auto_pause", "enabled"),
    default_value=True,
    value_type="bool",
)
CRON_UNREAD_AUTO_PAUSE_THRESHOLD_SETTING = SourceSystemConfigSetting(
    key="cron_unread_auto_pause.threshold",
    path=("cron_unread_auto_pause", "threshold"),
    default_value=10,
    value_type="int",
    ge=1,
)
CRON_TASK_SESSION_CLEANUP_ENABLED_SETTING = SourceSystemConfigSetting(
    key="cron_task_session_cleanup.enabled",
    path=("cron_task_session_cleanup", "enabled"),
    default_value=False,
    value_type="bool",
)
CRON_TASK_SESSION_CLEANUP_RETENTION_DAYS_SETTING = (
    SourceSystemConfigSetting(
        key="cron_task_session_cleanup.retention_days",
        path=("cron_task_session_cleanup", "retention_days"),
        default_value=30,
        value_type="int",
        ge=1,
    )
)
CRON_TASK_SESSION_CLEANUP_CRON_SETTING = SourceSystemConfigSetting(
    key="cron_task_session_cleanup.cron",
    path=("cron_task_session_cleanup", "cron"),
    default_value="0 1 * * *",
    value_type="str",
)
ARCHIVE_MAINTENANCE_ENABLED_SETTING = SourceSystemConfigSetting(
    key="archive_maintenance.enabled",
    path=("archive_maintenance", "enabled"),
    default_value=True,
    value_type="bool",
)
ARCHIVE_MAINTENANCE_CRON_SETTING = SourceSystemConfigSetting(
    key="archive_maintenance.cron",
    path=("archive_maintenance", "cron"),
    default_value="0 3 * * *",
    value_type="str",
)
ARCHIVE_MAINTENANCE_OLD_ORPHAN_DAYS_SETTING = SourceSystemConfigSetting(
    key="archive_maintenance.old_orphan_days",
    path=("archive_maintenance", "old_orphan_days"),
    default_value=3,
    value_type="int",
    ge=1,
)
ARCHIVE_MAINTENANCE_MAX_WORKSPACES_PER_RUN_SETTING = (
    SourceSystemConfigSetting(
        key="archive_maintenance.max_workspaces_per_run",
        path=("archive_maintenance", "max_workspaces_per_run"),
        default_value=200,
        value_type="int",
        ge=1,
    )
)
ARCHIVE_MAINTENANCE_MAX_FILES_PER_WORKSPACE_SETTING = (
    SourceSystemConfigSetting(
        key="archive_maintenance.max_files_per_workspace",
        path=("archive_maintenance", "max_files_per_workspace"),
        default_value=100,
        value_type="int",
        ge=1,
    )
)
ARCHIVE_MAINTENANCE_MAX_FILES_PER_RUN_SETTING = SourceSystemConfigSetting(
    key="archive_maintenance.max_files_per_run",
    path=("archive_maintenance", "max_files_per_run"),
    default_value=5000,
    value_type="int",
    ge=1,
)
ARCHIVE_MAINTENANCE_TIMEOUT_SECONDS_SETTING = SourceSystemConfigSetting(
    key="archive_maintenance.timeout_seconds",
    path=("archive_maintenance", "timeout_seconds"),
    default_value=900,
    value_type="int",
    ge=1,
)
SYSTEM_PROMPT_INJECTIONS_PATH = ("system_prompt_injections",)
SYSTEM_PROMPT_INJECTIONS_DEFAULT: list[str] = []

CURRENT_SOURCE_SYSTEM_CONFIG_SWITCHES: tuple[SourceSystemConfigSwitch, ...] = (
    CHAT_TASK_PROGRESS_ENABLED_SWITCH,
    DATABASE_ACCESS_GUARD_ENABLED_SWITCH,
)
CURRENT_SOURCE_SYSTEM_CONFIG_SETTINGS: tuple[
    SourceSystemConfigSetting,
    ...,
] = (
    CHAT_TASK_PROGRESS_ENABLED_SWITCH,
    DATABASE_ACCESS_GUARD_ENABLED_SWITCH,
    TOOL_RESULT_COMPACT_ENABLED_SETTING,
    TOOL_RESULT_COMPACT_RECENT_N_SETTING,
    TOOL_RESULT_COMPACT_OLD_MAX_BYTES_SETTING,
    TOOL_RESULT_COMPACT_RECENT_MAX_BYTES_SETTING,
    TOOL_RESULT_COMPACT_RETENTION_DAYS_SETTING,
    APPROVAL_NOTIFICATIONS_ZHAOHU_TOOL_GUARD_ENABLED_SETTING,
    FILE_READ_TRUNCATION_ENABLED_SETTING,
    FILE_READ_TRUNCATION_MAX_BYTES_SETTING,
    CRON_UNREAD_AUTO_PAUSE_ENABLED_SETTING,
    CRON_UNREAD_AUTO_PAUSE_THRESHOLD_SETTING,
    CRON_TASK_SESSION_CLEANUP_ENABLED_SETTING,
    CRON_TASK_SESSION_CLEANUP_RETENTION_DAYS_SETTING,
    CRON_TASK_SESSION_CLEANUP_CRON_SETTING,
    ARCHIVE_MAINTENANCE_ENABLED_SETTING,
    ARCHIVE_MAINTENANCE_CRON_SETTING,
    ARCHIVE_MAINTENANCE_OLD_ORPHAN_DAYS_SETTING,
    ARCHIVE_MAINTENANCE_MAX_WORKSPACES_PER_RUN_SETTING,
    ARCHIVE_MAINTENANCE_MAX_FILES_PER_WORKSPACE_SETTING,
    ARCHIVE_MAINTENANCE_MAX_FILES_PER_RUN_SETTING,
    ARCHIVE_MAINTENANCE_TIMEOUT_SECONDS_SETTING,
)

_MISSING = object()
_TRUE_STRINGS = frozenset({"true", "1", "yes", "on"})
_FALSE_STRINGS = frozenset({"false", "0", "no", "off"})
_IMMEDIATE_TRUNCATION_ENABLED_SETTINGS = (
    FILE_READ_TRUNCATION_ENABLED_SETTING,
)
_DEPRECATED_SYSTEM_SECTION_KEYS = frozenset(
    {
        "external_tool_output_truncation",
    },
)
_PRESERVED_DEFAULT_SETTING_PATHS = frozenset(
    setting.path for setting in _IMMEDIATE_TRUNCATION_ENABLED_SETTINGS
)


def build_default_source_system_config_payload() -> dict[str, Any]:
    """根据注册表生成默认 source 系统配置。"""
    payload: dict[str, Any] = {}
    for setting in CURRENT_SOURCE_SYSTEM_CONFIG_SETTINGS:
        payload = _deep_merge_dicts(
            payload,
            _build_nested_payload(setting.path, setting.default_value),
        )
    payload[SYSTEM_PROMPT_INJECTIONS_PATH[0]] = deepcopy(
        SYSTEM_PROMPT_INJECTIONS_DEFAULT,
    )
    return payload


def merge_source_system_config_with_defaults(
    raw_config: dict[str, Any],
) -> dict[str, Any]:
    """将原始配置与注册默认值做深度合并。"""
    return _deep_merge_dicts(
        build_default_source_system_config_payload(),
        raw_config,
    )


def prune_registered_default_overrides(
    raw_config: dict[str, Any],
) -> dict[str, Any]:
    """删除与注册默认值相同的显式覆盖，并清理空父节点。"""
    pruned = deepcopy(raw_config)
    for setting in CURRENT_SOURCE_SYSTEM_CONFIG_SETTINGS:
        value = _get_nested_value(pruned, setting.path)
        if value is _MISSING:
            continue
        if value == setting.default_value:
            if setting.path in _PRESERVED_DEFAULT_SETTING_PATHS:
                continue
            _delete_nested_path(pruned, setting.path)
    prompt_injections = pruned.get(SYSTEM_PROMPT_INJECTIONS_PATH[0], _MISSING)
    if prompt_injections is not _MISSING:
        normalized = normalize_system_prompt_injections(prompt_injections)
        if normalized == SYSTEM_PROMPT_INJECTIONS_DEFAULT:
            pruned.pop(SYSTEM_PROMPT_INJECTIONS_PATH[0], None)
        else:
            pruned[SYSTEM_PROMPT_INJECTIONS_PATH[0]] = normalized
    _drop_immediate_truncation_sections_without_enabled(pruned)
    return pruned


def is_chat_task_progress_enabled(config: Any | None) -> bool:
    """读取 task progress 开关，缺失时回退为默认启用。"""
    raw_config = _normalize_config_payload(config)
    merged = merge_source_system_config_with_defaults(raw_config)
    value = _get_nested_value(
        merged,
        CHAT_TASK_PROGRESS_ENABLED_SWITCH.path,
    )
    if value is _MISSING:
        return bool(CHAT_TASK_PROGRESS_ENABLED_SWITCH.default_value)
    return _coerce_registered_boolean_value(
        CHAT_TASK_PROGRESS_ENABLED_SWITCH.key,
        value,
        default=bool(CHAT_TASK_PROGRESS_ENABLED_SWITCH.default_value),
        strict=False,
    )


def is_database_access_guard_enabled(config: Any | None) -> bool:
    """读取数据库访问拦截开关，缺失时回退为默认启用。"""
    raw_config = _normalize_config_payload(config)
    merged = merge_source_system_config_with_defaults(raw_config)
    value = _get_nested_value(
        merged,
        DATABASE_ACCESS_GUARD_ENABLED_SWITCH.path,
    )
    if value is _MISSING:
        return bool(DATABASE_ACCESS_GUARD_ENABLED_SWITCH.default_value)
    return _coerce_registered_boolean_value(
        DATABASE_ACCESS_GUARD_ENABLED_SWITCH.key,
        value,
        default=bool(DATABASE_ACCESS_GUARD_ENABLED_SWITCH.default_value),
        strict=False,
    )


def normalize_system_prompt_injections(value: Any) -> list[str]:
    """规范化 source 级系统提示词注入列表。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("system_prompt_injections must be a list")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def get_system_prompt_injections(config: Any | None) -> list[str]:
    """读取合成后的 source 系统提示词注入配置。"""
    raw_config = _normalize_config_payload(config)
    merged = merge_source_system_config_with_defaults(raw_config)
    return normalize_system_prompt_injections(
        merged.get(SYSTEM_PROMPT_INJECTIONS_PATH[0], []),
    )


def normalize_registered_setting_values(
    raw_config: dict[str, Any],
    *,
    validate_cross_ranges: bool = True,
) -> dict[str, Any]:
    """规范化已注册配置项的值，避免脏值进入持久化配置。"""
    normalized = deepcopy(raw_config)
    _drop_deprecated_system_sections(normalized)
    prompt_injections = normalized.get(
        SYSTEM_PROMPT_INJECTIONS_PATH[0],
        _MISSING,
    )
    if prompt_injections is not _MISSING:
        normalized[SYSTEM_PROMPT_INJECTIONS_PATH[0]] = (
            normalize_system_prompt_injections(prompt_injections)
        )
    for setting in CURRENT_SOURCE_SYSTEM_CONFIG_SETTINGS:
        value = _get_nested_value(normalized, setting.path)
        if value is _MISSING:
            continue
        if setting.value_type == "bool":
            coerced = _coerce_registered_boolean_value(
                setting.key,
                value,
                default=bool(setting.default_value),
                strict=True,
            )
            _set_nested_value(normalized, setting.path, coerced)
            continue
        if setting.value_type == "int":
            coerced = _coerce_registered_int_value(setting, value)
            _set_nested_value(normalized, setting.path, coerced)
            continue
        if setting.value_type == "str":
            coerced = _coerce_registered_string_value(setting, value)
            if setting in (
                CRON_TASK_SESSION_CLEANUP_CRON_SETTING,
                ARCHIVE_MAINTENANCE_CRON_SETTING,
            ):
                coerced = _normalize_daily_cron_value(setting, coerced)
            _set_nested_value(normalized, setting.path, coerced)
    if validate_cross_ranges:
        _validate_explicit_tool_result_compact_ranges(raw_config, normalized)
    return normalized


def normalize_registered_switch_values(
    raw_config: dict[str, Any],
) -> dict[str, Any]:
    """兼容旧命名，统一委托到 typed setting 规范化逻辑。"""
    return normalize_registered_setting_values(raw_config)


def _normalize_config_payload(config: Any | None) -> dict[str, Any]:
    """兼容模型对象与普通 dict，统一提取配置对象。"""
    if config is None:
        return {}
    if hasattr(config, "config"):
        return _normalize_config_payload(getattr(config, "config"))
    if hasattr(config, "as_dict"):
        return config.as_dict()
    if isinstance(config, dict):
        return deepcopy(config)
    return {}


def _build_nested_payload(
    path: tuple[str, ...],
    value: Any,
) -> dict[str, Any]:
    """将点状路径构造成嵌套字典。"""
    nested: Any = deepcopy(value)
    for key in reversed(path):
        nested = {key: nested}
    return nested


def _deep_merge_dicts(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    """递归合并配置，保留未知键并允许局部覆盖。"""
    merged = deepcopy(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(current, value)
            continue
        merged[key] = deepcopy(value)
    return merged


def _get_nested_value(
    payload: dict[str, Any],
    path: tuple[str, ...],
) -> Any:
    """读取嵌套路径的值，缺失时返回哨兵对象。"""
    current: Any = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return _MISSING
        current = current[key]
    return current


def _delete_nested_path(
    payload: dict[str, Any],
    path: tuple[str, ...],
) -> None:
    """删除嵌套路径，并向上裁剪变为空对象的父节点。"""
    parents: list[tuple[dict[str, Any], str]] = []
    current: Any = payload
    for key in path[:-1]:
        if not isinstance(current, dict):
            return
        next_current = current.get(key)
        if not isinstance(next_current, dict):
            return
        parents.append((current, key))
        current = next_current
    if not isinstance(current, dict):
        return
    current.pop(path[-1], None)
    while parents:
        parent, key = parents.pop()
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            parent.pop(key, None)


def _set_nested_value(
    payload: dict[str, Any],
    path: tuple[str, ...],
    value: Any,
) -> None:
    """写入嵌套路径，保持原有父节点结构。"""
    current: dict[str, Any] = payload
    for key in path[:-1]:
        next_current = current.get(key)
        if not isinstance(next_current, dict):
            next_current = {}
            current[key] = next_current
        current = next_current
    current[path[-1]] = value


def _coerce_registered_boolean_value(
    key: str,
    value: Any,
    *,
    default: bool,
    strict: bool,
) -> bool:
    """将注册布尔开关收敛为真实布尔值。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_STRINGS:
            return True
        if normalized in _FALSE_STRINGS:
            return False
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if strict:
        raise ValueError(
            f"{key} must be a boolean-compatible value, got {value!r}",
        )
    return default


def _coerce_registered_int_value(
    setting: SourceSystemConfigSetting,
    value: Any,
) -> int:
    """将注册整数配置收敛并校验取值范围。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{setting.key} must be an integer, got {value!r}")
    if setting.ge is not None and value < setting.ge:
        raise ValueError(
            f"{setting.key} must be greater than or equal to {setting.ge}",
        )
    if setting.le is not None and value > setting.le:
        raise ValueError(
            f"{setting.key} must be less than or equal to {setting.le}",
        )
    return value


def _coerce_registered_string_value(
    setting: SourceSystemConfigSetting,
    value: Any,
) -> str:
    """将注册字符串配置收敛为去除首尾空白的字符串。"""
    if not isinstance(value, str):
        raise ValueError(f"{setting.key} must be a string, got {value!r}")
    return value.strip()


def _normalize_daily_cron_value(
    setting: SourceSystemConfigSetting,
    value: str,
) -> str:
    """仅允许每天一次的五段 cron，避免清理频率被误配。"""
    parts = [part for part in value.split() if part]
    if len(parts) != 5:
        raise ValueError(
            f"{setting.key} must be a daily 5-field cron expression",
        )
    minute, hour, day_of_month, month, day_of_week = parts
    if day_of_month != "*" or month != "*" or day_of_week != "*":
        raise ValueError(
            f"{setting.key} must run daily in '<minute> <hour> * * *' form",
        )
    if not minute.isdigit() or not hour.isdigit():
        raise ValueError(
            f"{setting.key} must use numeric minute and hour fields",
        )
    minute_int = int(minute)
    hour_int = int(hour)
    if not 0 <= minute_int <= 59 or not 0 <= hour_int <= 23:
        raise ValueError(
            f"{setting.key} minute/hour are out of range",
        )
    return f"{minute_int} {hour_int} * * *"


def _drop_immediate_truncation_sections_without_enabled(
    payload: dict[str, Any],
) -> None:
    """即时截断缺少 enabled 时视为未配置，避免空对象误判为显式接管。"""
    for setting in _IMMEDIATE_TRUNCATION_ENABLED_SETTINGS:
        section_key = setting.path[0]
        section = payload.get(section_key)
        if isinstance(section, dict) and "enabled" not in section:
            payload.pop(section_key, None)


def _drop_deprecated_system_sections(payload: dict[str, Any]) -> None:
    """移除已经下线的系统配置段，避免死配置在读写链路中回流。"""
    for key in _DEPRECATED_SYSTEM_SECTION_KEYS:
        payload.pop(key, None)


def _validate_explicit_tool_result_compact_ranges(
    raw_config: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    """只校验 source 原始输入中同时显式出现的阈值关系。"""
    raw_tool_result_compact = raw_config.get("tool_result_compact")
    if not isinstance(raw_tool_result_compact, dict):
        return
    if (
        "old_max_bytes" not in raw_tool_result_compact
        or "recent_max_bytes" not in raw_tool_result_compact
    ):
        return
    old_max_bytes = _get_nested_value(
        payload,
        TOOL_RESULT_COMPACT_OLD_MAX_BYTES_SETTING.path,
    )
    recent_max_bytes = _get_nested_value(
        payload,
        TOOL_RESULT_COMPACT_RECENT_MAX_BYTES_SETTING.path,
    )
    if recent_max_bytes < old_max_bytes:
        raise ValueError(
            "tool_result_compact.recent_max_bytes must be greater than "
            "or equal to tool_result_compact.old_max_bytes",
        )


__all__ = [
    "ARCHIVE_MAINTENANCE_CRON_SETTING",
    "ARCHIVE_MAINTENANCE_ENABLED_SETTING",
    "ARCHIVE_MAINTENANCE_MAX_FILES_PER_RUN_SETTING",
    "ARCHIVE_MAINTENANCE_MAX_FILES_PER_WORKSPACE_SETTING",
    "ARCHIVE_MAINTENANCE_MAX_WORKSPACES_PER_RUN_SETTING",
    "ARCHIVE_MAINTENANCE_OLD_ORPHAN_DAYS_SETTING",
    "ARCHIVE_MAINTENANCE_TIMEOUT_SECONDS_SETTING",
    "APPROVAL_NOTIFICATIONS_ZHAOHU_TOOL_GUARD_ENABLED_SETTING",
    "CHAT_TASK_PROGRESS_ENABLED_SWITCH",
    "CRON_TASK_SESSION_CLEANUP_CRON_SETTING",
    "CRON_TASK_SESSION_CLEANUP_ENABLED_SETTING",
    "CRON_TASK_SESSION_CLEANUP_RETENTION_DAYS_SETTING",
    "CRON_UNREAD_AUTO_PAUSE_ENABLED_SETTING",
    "CRON_UNREAD_AUTO_PAUSE_THRESHOLD_SETTING",
    "CURRENT_SOURCE_SYSTEM_CONFIG_SETTINGS",
    "CURRENT_SOURCE_SYSTEM_CONFIG_SWITCHES",
    "DATABASE_ACCESS_GUARD_ENABLED_SWITCH",
    "FILE_READ_TRUNCATION_ENABLED_SETTING",
    "FILE_READ_TRUNCATION_MAX_BYTES_SETTING",
    "SourceSystemConfigSwitch",
    "SourceSystemConfigSetting",
    "SYSTEM_PROMPT_INJECTIONS_DEFAULT",
    "SYSTEM_PROMPT_INJECTIONS_PATH",
    "TOOL_RESULT_COMPACT_ENABLED_SETTING",
    "TOOL_RESULT_COMPACT_OLD_MAX_BYTES_SETTING",
    "TOOL_RESULT_COMPACT_RECENT_MAX_BYTES_SETTING",
    "TOOL_RESULT_COMPACT_RECENT_N_SETTING",
    "TOOL_RESULT_COMPACT_RETENTION_DAYS_SETTING",
    "build_default_source_system_config_payload",
    "get_system_prompt_injections",
    "is_chat_task_progress_enabled",
    "is_database_access_guard_enabled",
    "merge_source_system_config_with_defaults",
    "normalize_registered_setting_values",
    "normalize_registered_switch_values",
    "normalize_system_prompt_injections",
    "prune_registered_default_overrides",
]
