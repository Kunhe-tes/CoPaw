# -*- coding: utf-8 -*-
"""RetryChatModel 空输出重试的回归测试。

覆盖非流式与流式共用的空输出重试辅助方法：重试时发送
``model.retry_scheduled`` 回调，重试耗尽时只抛异常、不发送回调。
"""

import pytest

from swe.providers.retry_chat_model import (
    EmptyModelOutputError,
    RetryChatModel,
)


class _FakeInnerModel:
    """最小化的内部模型替身。

    ``RetryChatModel.__init__`` 只读取 ``model_name`` 与 ``stream`` 两个属性，
    因此无需实现完整的 ``ChatModelBase`` 接口即可真实构造外层包装器。
    """

    def __init__(self, model_name: str = "fake-model", stream: bool = True):
        self.model_name = model_name
        self.stream = stream


def _make_model(on_retry):
    """用最小替身构造 RetryChatModel，避免依赖真实 Provider。"""
    return RetryChatModel(inner=_FakeInnerModel(), on_retry=on_retry)


@pytest.mark.asyncio
async def test_empty_output_retry_notifies_callback():
    """重试未被耗尽时应回调 (attempt, attempt + 1, error, 0)。"""
    calls = []

    async def on_retry(attempt, max_attempts, error, delay):
        calls.append((attempt, max_attempts, error, delay))

    model = _make_model(on_retry)

    remaining = await model._consume_empty_output_retry(
        1,
        attempt=2,
        stream=True,
        message="LLM stream returned empty model output",
    )

    assert remaining == 0
    assert len(calls) == 1
    attempt, max_attempts, error, delay = calls[0]
    assert (attempt, max_attempts, delay) == (2, 3, 0)
    assert isinstance(error, EmptyModelOutputError)
    assert str(error) == "LLM stream returned empty model output"


@pytest.mark.asyncio
async def test_exhausted_retry_raises_without_notification():
    """重试耗尽时应抛 EmptyModelOutputError，且不发送回调。"""
    calls = []

    async def on_retry(*args):
        calls.append(args)

    model = _make_model(on_retry)

    with pytest.raises(EmptyModelOutputError):
        await model._consume_empty_output_retry(
            0,
            attempt=3,
            stream=True,
            message="LLM stream returned empty model output",
        )

    assert calls == []


@pytest.mark.asyncio
async def test_callback_failure_does_not_affect_return():
    """回调自身抛异常时应被吞掉，不影响重试返回值。"""

    async def on_retry(*args):
        raise RuntimeError("callback failed")

    model = _make_model(on_retry)

    remaining = await model._consume_empty_output_retry(
        1,
        attempt=1,
        stream=True,
        message="LLM stream returned empty model output",
    )

    assert remaining == 0
