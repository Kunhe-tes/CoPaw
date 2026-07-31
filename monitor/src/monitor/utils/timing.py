# -*- coding: utf-8 -*-
"""耗时日志工具类."""

import time
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MethodTimer:
    """方法耗时计时器.

    用于记录方法的总耗时，支持分步骤计时。

    使用示例：
        with MethodTimer("get_sessions", source_id=source_id) as timer:
            step = timer.step("count查询")
            count_row = await self._db.fetch_one(count_query, params)
            step.done(total=count_row["total"])

            step = timer.step("主查询")
            rows = await self._db.fetch_all(main_query, params)
            step.done(返回=len(rows))
    """

    def __init__(self, method_name: str, **kwargs: Any):
        """初始化方法计时器.

        Args:
            method_name: 方法名称（用于日志标识）
            **kwargs: 方法参数（用于日志输出）
        """
        self.method_name = method_name
        self.params = kwargs
        self.start_time: Optional[float] = None

    def __enter__(self) -> "MethodTimer":
        """进入上下文，开始计时."""
        self.start_time = time.time()
        if self.params:
            param_str = ", ".join(f"{k}={v}" for k, v in self.params.items())
            logger.info("[%s] 开始处理: %s", self.method_name, param_str)
        else:
            logger.info("[%s] 开始处理", self.method_name)
        return self

    def __exit__(self, *args: Any) -> None:
        """退出上下文，记录总耗时."""
        assert self.start_time is not None  # __enter__ guarantees this
        elapsed = (time.time() - self.start_time) * 1000
        logger.info("[%s] 方法总耗时: %.3fms", self.method_name, elapsed)

    def step(self, step_name: str) -> "StepTimer":
        """创建步骤计时器.

        Args:
            step_name: 步骤名称

        Returns:
            StepTimer 实例
        """
        return StepTimer(self.method_name, step_name)


class StepTimer:
    """步骤耗时计时器.

    用于记录方法内各步骤的耗时。
    """

    def __init__(self, method_name: str, step_name: str):
        """初始化步骤计时器.

        Args:
            method_name: 所属方法名称
            step_name: 步骤名称
        """
        self.method_name = method_name
        self.step_name = step_name
        self.start_time = time.time()

    def done(self, **extra_info: Any) -> None:
        """记录步骤完成.

        Args:
            **extra_info: 额外信息（如查询结果数量等）
        """
        elapsed = (time.time() - self.start_time) * 1000
        if extra_info:
            info_str = ", ".join(f"{k}={v}" for k, v in extra_info.items())
            logger.info(
                "[%s] %s耗时: %.3fms, %s",
                self.method_name,
                self.step_name,
                elapsed,
                info_str,
            )
        else:
            logger.info(
                "[%s] %s耗时: %.3fms",
                self.method_name,
                self.step_name,
                elapsed,
            )


def log_method_time(method_name: str, **params: Any) -> MethodTimer:
    """创建方法计时器的便捷函数.

    Args:
        method_name: 方法名称
        **params: 方法参数

    Returns:
        MethodTimer 实例
    """
    return MethodTimer(method_name, **params)
