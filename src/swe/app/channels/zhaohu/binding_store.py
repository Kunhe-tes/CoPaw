# -*- coding: utf-8 -*-
"""招乎渠道绑定信息数据库存储

持久化 (tenant_id, source_id) → (robot_id, open_id) 映射，
支持配置更新时保存、其他模块读取、推送时 robotId 查询。
"""

import logging
from typing import Any, Optional

from ....database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

_BINDING_TABLE = "swe_zhaohu_channel_binding"


class ZhaohuChannelBindingStore:
    """招乎渠道绑定信息存储"""

    def __init__(self):
        self._db: Optional[DatabaseConnection] = None

    def initialize(self, db: Optional[DatabaseConnection]):
        self._db = db

    def _use_db(self) -> Optional[DatabaseConnection]:
        if self._db is None:
            logger.warning("ZhaohuChannelBindingStore: 数据库未初始化")
            return None
        return self._db

    async def upsert_binding(
        self,
        tenant_id: str,
        source_id: str,
        robot_id: str,
        open_id: Optional[str] = None,
    ) -> bool:
        """插入或更新渠道绑定信息，(tenant_id, source_id) 冲突时更新"""
        db = self._use_db()
        if db is None:
            return False

        sql = f"""
            INSERT INTO {_BINDING_TABLE} (tenant_id, source_id, robot_id, open_id)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                robot_id = VALUES(robot_id),
                open_id = COALESCE(VALUES(open_id), open_id)
        """
        try:
            await db.execute(sql, (tenant_id, source_id, robot_id, open_id))
            return True
        except Exception:
            logger.exception(
                "upsert_binding 失败: tenant_id=%s, source_id=%s",
                tenant_id,
                source_id,
            )
            return False

    async def get_binding(
        self,
        tenant_id: str,
        source_id: str,
    ) -> Optional[dict[str, Any]]:
        """按 (tenant_id, source_id) 查询绑定记录"""
        db = self._use_db()
        if db is None:
            return None

        sql = f"""
            SELECT tenant_id, source_id, robot_id, open_id, created_at, updated_at
            FROM {_BINDING_TABLE}
            WHERE tenant_id = %s AND source_id = %s
        """
        try:
            return await db.fetch_one(sql, (tenant_id, source_id))
        except Exception:
            logger.exception(
                "get_binding 失败: tenant_id=%s, source_id=%s",
                tenant_id,
                source_id,
            )
            return None

    async def get_robot_id(
        self,
        tenant_id: str,
        source_id: str,
    ) -> Optional[str]:
        """按 (tenant_id, source_id) 查询 robot_id"""
        db = self._use_db()
        if db is None:
            return None

        sql = f"""
            SELECT robot_id FROM {_BINDING_TABLE}
            WHERE tenant_id = %s AND source_id = %s
        """
        try:
            row = await db.fetch_one(sql, (tenant_id, source_id))
            return row["robot_id"] if row else None
        except Exception:
            logger.exception(
                "get_robot_id 失败: tenant_id=%s, source_id=%s",
                tenant_id,
                source_id,
            )
            return None

    async def get_source_id_by_robot(
        self,
        tenant_id: str,
        robot_id: str,
    ) -> Optional[str]:
        """按 (tenant_id, robot_id) 查询 source_id"""
        db = self._use_db()
        if db is None:
            return None

        sql = f"""
            SELECT source_id FROM {_BINDING_TABLE}
            WHERE tenant_id = %s AND robot_id = %s
        """
        try:
            row = await db.fetch_one(sql, (tenant_id, robot_id))
            return row["source_id"] if row else None
        except Exception:
            logger.exception(
                "get_source_id_by_robot 失败: tenant_id=%s, robot_id=%s",
                tenant_id,
                robot_id,
            )
            return None

    async def get_binding_by_open_id(
        self,
        open_id: str,
    ) -> Optional[dict[str, Any]]:
        """按 open_id 查询绑定记录"""
        db = self._use_db()
        if db is None:
            return None

        sql = f"""
            SELECT tenant_id, source_id, robot_id, open_id, created_at, updated_at
            FROM {_BINDING_TABLE}
            WHERE open_id = %s
        """
        try:
            return await db.fetch_one(sql, (open_id,))
        except Exception:
            logger.exception(
                "get_binding_by_open_id 失败: open_id=%s",
                open_id,
            )
            return None


# 模块级单例
_store: Optional[ZhaohuChannelBindingStore] = None


def init_zhaohu_binding_module(db: Optional[DatabaseConnection]):
    """初始化招乎渠道绑定 Store 模块"""
    global _store
    if db is not None:
        _store = ZhaohuChannelBindingStore()
        _store.initialize(db)
        logger.info("ZhaohuChannelBindingStore 初始化完成")
    else:
        _store = None
        logger.info("ZhaohuChannelBindingStore 未初始化（数据库不可用）")


def get_zhaohu_binding_store() -> Optional[ZhaohuChannelBindingStore]:
    """获取招乎渠道绑定 Store 实例"""
    return _store
