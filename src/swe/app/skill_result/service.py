# -*- coding: utf-8 -*-
"""技能执行结果业务服务。"""

from typing import Optional

from .models import SkillResultCreate
from .store import SkillResultStore


class SkillResultService:
    """封装技能执行结果保存逻辑。"""

    def __init__(self, store: SkillResultStore):
        """初始化服务。

        Args:
            store: 存储实例
        """
        self.store = store

    async def create(
        self,
        payload: SkillResultCreate,
        *,
        source_id: Optional[str] = None,
    ) -> tuple[Optional[int], Optional[str]]:
        """保存一条技能执行结果。"""
        return await self.store.create(payload, source_id=source_id)
