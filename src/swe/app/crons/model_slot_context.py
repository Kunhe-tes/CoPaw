# -*- coding: utf-8 -*-
"""cron 执行模型覆盖的上下文工具。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Generator

from ...providers.models import ModelSlotConfig

_current_model_slot_override: ContextVar[ModelSlotConfig | None] = ContextVar(
    "swe_cron_model_slot_override",
    default=None,
)


def get_current_model_slot_override() -> ModelSlotConfig | None:
    """返回当前请求作用域内绑定的 cron 模型覆盖。"""
    return _current_model_slot_override.get()


@contextmanager
def bind_model_slot_override(
    model_slot: ModelSlotConfig,
) -> Generator[None, None, None]:
    """在当前上下文中临时绑定 cron 执行模型覆盖。"""
    token = _current_model_slot_override.set(model_slot)
    try:
        yield
    finally:
        _current_model_slot_override.reset(token)
