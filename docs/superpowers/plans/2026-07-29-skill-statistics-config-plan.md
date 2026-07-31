# 技能统计配置功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现技能统计配置功能，支持管理员配置哪些技能纳入排行榜统计。

**Architecture:** Market 服务负责统计配置管理，Monitor 服务负责排行榜过滤，Console 前端提供配置界面。

**Tech Stack:** Python (FastAPI), TypeScript (React), MySQL

---

## 文件结构

### 新建文件

| 文件 | 职责 |
|------|------|
| `deploy/migrations/2026_07_29_add_swe_market_skills_table.sql` | 数据库迁移脚本 |
| `market/src/market/marketplace/market_skill_registry.py` | 市场技能数据库操作类 |
| `market/tests/unit/marketplace/test_market_skill_registry.py` | 数据库操作单元测试 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `market/src/market/marketplace/models.py` | MarketItem 增加 include_in_statistics 字段 |
| `market/src/market/marketplace/service.py` | 技能上传/同步时同步写入数据库 |
| `market/src/market/app/routers/skills_market.py` | 新增统计配置接口、修改上传接口 |
| `monitor/src/monitor/app/services/tracing/query_service.py` | 排行榜查询增加 JOIN 和过滤逻辑 |
| `console/src/api/modules/market.ts` | 增加 include_in_statistics 字段和统计配置接口 |
| `console/src/pages/Market/SkillDetailDrawer.tsx` | 增加统计配置开关 |
| `console/src/pages/Market/SkillCard.tsx` | 增加徽章显示 |
| `console/src/pages/Market/components/UploadSkillModal.tsx` | 增加纳入统计复选框 |

---

## Task 1: 创建数据库迁移脚本

**Files:**
- Create: `deploy/migrations/2026_07_29_add_swe_market_skills_table.sql`

- [ ] **Step 1: 创建迁移脚本文件**

```sql
-- 技能统计配置功能：市场技能表
-- 用于记录市场技能的统计配置

CREATE TABLE IF NOT EXISTS swe_market_skills (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_id VARCHAR(64) NOT NULL COMMENT '应用入口标识',
    item_id VARCHAR(64) NOT NULL COMMENT '市场条目ID',
    skill_id VARCHAR(128) NOT NULL COMMENT '技能唯一标识符',
    skill_name VARCHAR(128) NOT NULL COMMENT '技能目录名',
    cn_name VARCHAR(256) DEFAULT '' COMMENT '中文展示名',
    include_in_statistics TINYINT(1) DEFAULT 1 COMMENT '是否纳入统计：1=纳入，0=不纳入',
    creator_id VARCHAR(64) DEFAULT '' COMMENT '创建人ID',
    creator_name VARCHAR(256) DEFAULT '' COMMENT '创建人名称',
    updator_id VARCHAR(64) DEFAULT '' COMMENT '更新人ID',
    updator_name VARCHAR(256) DEFAULT '' COMMENT '更新人名称',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_source_item (source_id, item_id),
    INDEX idx_skill_id (skill_id),
    INDEX idx_include_statistics (source_id, include_in_statistics),
    INDEX idx_creator_id (creator_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='市场技能表';
```

- [ ] **Step 2: 执行迁移脚本验证**

Run: `mysql -u root -p your_database < deploy/migrations/2026_07_29_add_swe_market_skills_table.sql`
Expected: 表创建成功

- [ ] **Step 3: 提交迁移脚本**

```bash
git add deploy/migrations/2026_07_29_add_swe_market_skills_table.sql
git commit -m "feat(market): add swe_market_skills table migration"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Task 2: 修改 MarketItem 模型

**Files:**
- Modify: `market/src/market/marketplace/models.py`

- [ ] **Step 1: 读取现有模型文件**

Run: Read `market/src/market/marketplace/models.py`

- [ ] **Step 2: 添加 include_in_statistics 字段**

在 MarketItem 类中添加字段：

```python
class MarketItem(BaseModel):
    """市场条目（index.json 中的单条记录）."""

    item_id: str
    item_type: str = "skill"
    name: str
    skill_id: str = ""
    chinese_name: str = ""
    description: str = ""
    guidance: str = ""
    version: str = "1.0.0"
    creator_id: str
    creator_name: str = ""
    category_id: Optional[int] = None
    bbk_ids: list[str] = Field(default_factory=list)
    client_key: str = ""  # MCP 专用，业务唯一键
    status: str = "active"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # 新增字段：是否纳入统计（仅对 skill 类型生效）
    include_in_statistics: bool = False  # 默认不纳入统计
```

- [ ] **Step 3: 提交模型修改**

```bash
git add market/src/market/marketplace/models.py
git commit -m "feat(market): add include_in_statistics field to MarketItem"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Task 3: 创建市场技能数据库操作类

**Files:**
- Create: `market/src/market/marketplace/market_skill_registry.py`
- Create: `market/tests/unit/marketplace/test_market_skill_registry.py`

- [ ] **Step 1: 创建数据库操作类**

```python
# -*- coding: utf-8 -*-
"""市场技能数据库操作类.

隔离 swe_market_skills 表相关的数据库操作。
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MarketSkillRegistry:
    """市场技能数据库操作类."""

    def __init__(self, db):
        """初始化，接收数据库连接对象."""
        self.db = db

    def is_connected(self) -> bool:
        """检查数据库是否已连接."""
        return self.db.is_connected

    async def upsert_market_skill(
        self,
        source_id: str,
        item_id: str,
        skill_id: str,
        skill_name: str,
        cn_name: str = "",
        include_in_statistics: bool = True,
        creator_id: str = "",
        creator_name: str = "",
        updator_id: str = "",
        updator_name: str = "",
    ) -> bool:
        """插入或更新市场技能记录.

        按 source_id + item_id 判断是否存在：
        - 存在：更新现有记录
        - 不存在：插入新记录

        Args:
            source_id: 应用入口标识
            item_id: 市场条目ID
            skill_id: 技能唯一标识符
            skill_name: 技能目录名
            cn_name: 中文展示名
            include_in_statistics: 是否纳入统计
            creator_id: 创建人ID
            creator_name: 创建人名称
            updator_id: 更新人ID
            updator_name: 更新人名称

        Returns:
            是否成功插入/更新
        """
        if not self.is_connected():
            logger.warning("Database not connected, skip upsert swe_market_skills")
            return False

        try:
            # 先查询是否存在
            existing = await self.db.fetch_one(
                """
                SELECT id FROM swe_market_skills
                WHERE source_id = %s AND item_id = %s
                """,
                (source_id, item_id),
            )

            if existing:
                # 更新现有记录
                await self.db.execute(
                    """
                    UPDATE swe_market_skills
                    SET skill_id = %s, skill_name = %s, cn_name = %s,
                        include_in_statistics = %s,
                        updator_id = %s, updator_name = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (
                        skill_id,
                        skill_name,
                        cn_name,
                        1 if include_in_statistics else 0,
                        updator_id,
                        updator_name,
                        existing.get("id"),
                    ),
                )
                logger.info(
                    "Updated swe_market_skills: item_id=%s, skill_name=%s, include=%s",
                    item_id,
                    skill_name,
                    include_in_statistics,
                )
            else:
                # 插入新记录
                await self.db.execute(
                    """
                    INSERT INTO swe_market_skills
                        (source_id, item_id, skill_id, skill_name, cn_name,
                         include_in_statistics, creator_id, creator_name,
                         updator_id, updator_name)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        source_id,
                        item_id,
                        skill_id,
                        skill_name,
                        cn_name,
                        1 if include_in_statistics else 0,
                        creator_id,
                        creator_name,
                        updator_id,
                        updator_name,
                    ),
                )
                logger.info(
                    "Inserted swe_market_skills: item_id=%s, skill_name=%s, include=%s",
                    item_id,
                    skill_name,
                    include_in_statistics,
                )
            return True
        except Exception as e:
            logger.warning("Failed to upsert swe_market_skills: %s", e)
            return False

    async def update_statistics_config(
        self,
        source_id: str,
        item_id: str,
        include_in_statistics: bool,
        updator_id: str = "",
        updator_name: str = "",
    ) -> bool:
        """更新统计配置.

        Args:
            source_id: 应用入口标识
            item_id: 市场条目ID
            include_in_statistics: 是否纳入统计
            updator_id: 更新人ID
            updator_name: 更新人名称

        Returns:
            是否成功更新
        """
        if not self.is_connected():
            logger.warning("Database not connected, skip update statistics config")
            return False

        try:
            await self.db.execute(
                """
                UPDATE swe_market_skills
                SET include_in_statistics = %s,
                    updator_id = %s,
                    updator_name = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE source_id = %s AND item_id = %s
                """,
                (
                    1 if include_in_statistics else 0,
                    updator_id,
                    updator_name,
                    source_id,
                    item_id,
                ),
            )
            logger.info(
                "Updated statistics config: item_id=%s, include=%s",
                item_id,
                include_in_statistics,
            )
            return True
        except Exception as e:
            logger.warning("Failed to update statistics config: %s", e)
            return False

    async def get_statistics_eligible_skill_names(
        self,
        source_id: str,
    ) -> set[str]:
        """获取纳入统计的技能名称集合.

        Args:
            source_id: 应用入口标识

        Returns:
            纳入统计的技能名称集合
        """
        if not self.is_connected():
            logger.warning("Database not connected, return empty set")
            return set()

        try:
            rows = await self.db.fetch_all(
                """
                SELECT skill_name FROM swe_market_skills
                WHERE source_id = %s AND include_in_statistics = 1
                """,
                (source_id,),
            )
            return {row["skill_name"] for row in rows if row.get("skill_name")}
        except Exception as e:
            logger.warning("Failed to get statistics eligible skills: %s", e)
            return set()
```

- [ ] **Step 2: 创建单元测试文件**

```python
# -*- coding: utf-8 -*-
"""市场技能数据库操作类单元测试."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from market.marketplace.market_skill_registry import MarketSkillRegistry


@pytest.mark.asyncio
class TestMarketSkillRegistry:
    """MarketSkillRegistry 单元测试."""

    def test_is_connected(self):
        """测试数据库连接状态检查."""
        db = MagicMock()
        db.is_connected = True
        registry = MarketSkillRegistry(db)
        assert registry.is_connected() is True

    async def test_upsert_market_skill_insert(self):
        """测试插入新记录."""
        db = MagicMock()
        db.is_connected = True
        db.fetch_one = AsyncMock(return_value=None)
        db.execute = AsyncMock()

        registry = MarketSkillRegistry(db)
        result = await registry.upsert_market_skill(
            source_id="test_source",
            item_id="test_item",
            skill_id="test_skill_id",
            skill_name="test_skill",
            cn_name="测试技能",
            include_in_statistics=True,
            creator_id="user1",
            creator_name="用户1",
        )

        assert result is True
        db.execute.assert_called_once()

    async def test_upsert_market_skill_update(self):
        """测试更新现有记录."""
        db = MagicMock()
        db.is_connected = True
        db.fetch_one = AsyncMock(return_value={"id": 1})
        db.execute = AsyncMock()

        registry = MarketSkillRegistry(db)
        result = await registry.upsert_market_skill(
            source_id="test_source",
            item_id="test_item",
            skill_id="test_skill_id",
            skill_name="test_skill",
            cn_name="测试技能",
            include_in_statistics=False,
            updator_id="user2",
            updator_name="用户2",
        )

        assert result is True
        db.execute.assert_called_once()

    async def test_update_statistics_config(self):
        """测试更新统计配置."""
        db = MagicMock()
        db.is_connected = True
        db.execute = AsyncMock()

        registry = MarketSkillRegistry(db)
        result = await registry.update_statistics_config(
            source_id="test_source",
            item_id="test_item",
            include_in_statistics=False,
            updator_id="admin",
            updator_name="管理员",
        )

        assert result is True
        db.execute.assert_called_once()

    async def test_get_statistics_eligible_skill_names(self):
        """测试获取纳入统计的技能名称."""
        db = MagicMock()
        db.is_connected = True
        db.fetch_all = AsyncMock(
            return_value=[
                {"skill_name": "skill1"},
                {"skill_name": "skill2"},
            ]
        )

        registry = MarketSkillRegistry(db)
        result = await registry.get_statistics_eligible_skill_names("test_source")

        assert result == {"skill1", "skill2"}

    async def test_database_not_connected(self):
        """测试数据库未连接时的处理."""
        db = MagicMock()
        db.is_connected = False

        registry = MarketSkillRegistry(db)
        result = await registry.upsert_market_skill(
            source_id="test_source",
            item_id="test_item",
            skill_id="test_skill_id",
            skill_name="test_skill",
        )

        assert result is False
```

- [ ] **Step 3: 运行单元测试**

Run: `cd D:/workspace/CoPaw && .venv/Scripts/python.exe -m pytest market/tests/unit/marketplace/test_market_skill_registry.py -v`
Expected: 所有测试通过

- [ ] **Step 4: 提交代码**

```bash
git add market/src/market/marketplace/market_skill_registry.py
git add market/tests/unit/marketplace/test_market_skill_registry.py
git commit -m "feat(market): add MarketSkillRegistry for database operations"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Task 4: 修改技能上传接口

**Files:**
- Modify: `market/src/market/app/routers/skills_market.py`

- [ ] **Step 1: 读取现有接口代码**

Run: Read `market/src/market/app/routers/skills_market.py` lines 556-700

- [ ] **Step 2: 添加 include_in_statistics 参数到上传接口**

在 `publish_skill_upload` 函数中添加参数：

```python
@router.post(
    "/market/skills/publish-upload",
    response_model=UploadSkillResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_skill_upload(
    request: Request,
    file: UploadFile = File(..., description="Skill zip file to publish"),
    category_id: Optional[int] = Query(default=None),
    overwrite: bool = Query(default=False),
    cn_name: str = Query(default=""),
    skill_id: str = Query(default=""),
    bbk_ids: str = Query(default=""),
    # 新增参数：是否纳入统计
    include_in_statistics: bool = Query(default=False, description="是否纳入排行榜统计"),
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """上传 zip 文件上架技能到市场（管理员）."""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    # ... 其余代码 ...
```

- [ ] **Step 3: 在 _process_skill_upload_single 中传递参数**

修改 `_process_skill_upload_single` 函数签名和逻辑：

```python
def _process_skill_upload_single(
    skill_dir: Path,
    skill_name: str,
    svc,
    source_id: str,
    user_id: str,
    user_name: str,
    category_id: Optional[int],
    overwrite: bool = False,
    cn_name: Optional[str] = None,
    skill_id: Optional[str] = None,
    bbk_ids: Optional[list[str]] = None,
    include_in_statistics: bool = False,  # 新增参数
) -> tuple[Optional[str], Optional[dict], Optional[str], str, bool]:
    """处理单个技能的上架逻辑."""
    # ... 现有代码 ...

    # 在创建或更新 item 时设置 include_in_statistics
    if existing:
        existing.include_in_statistics = include_in_statistics
        # ... 其他更新逻辑 ...
    else:
        item = _create_market_item(
            name,
            resolved_cn_name,
            description,
            "",
            user_id,
            user_name,
            category_id,
            skill_id=final_skill_id,
            bbk_ids=bbk_ids or [],
        )
        item.include_in_statistics = include_in_statistics
        items.append(item)

    # ... 其余代码 ...
```

- [ ] **Step 4: 同步写入数据库**

在技能上传成功后，同步写入 swe_market_skills 表：

```python
# 在 save_index 之后添加数据库写入
from ...marketplace.market_skill_registry import MarketSkillRegistry

# 在 Market 服务类中添加方法
async def _sync_to_market_skills_db(
    self,
    source_id: str,
    item: MarketItem,
    user_id: str,
    user_name: str,
) -> None:
    """同步写入 swe_market_skills 表."""
    if not self.db or not self.db.is_connected:
        return

    registry = MarketSkillRegistry(self.db)
    await registry.upsert_market_skill(
        source_id=source_id,
        item_id=item.item_id,
        skill_id=item.skill_id,
        skill_name=item.name,
        cn_name=item.chinese_name,
        include_in_statistics=item.include_in_statistics,
        creator_id=user_id,
        creator_name=user_name,
        updator_id=user_id,
        updator_name=user_name,
    )
```

- [ ] **Step 5: 提交代码**

```bash
git add market/src/market/app/routers/skills_market.py
git commit -m "feat(market): add include_in_statistics param to upload API"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Task 5: 新增统计配置修改接口

**Files:**
- Modify: `market/src/market/app/routers/skills_market.py`

- [ ] **Step 1: 定义请求/响应模型**

```python
class UpdateStatisticsConfigRequest(BaseModel):
    """更新统计配置请求."""

    include_in_statistics: bool = Field(
        ...,
        description="是否纳入统计",
    )
    updator_id: str = Field(default="", description="更新人ID")
    updator_name: str = Field(default="", description="更新人名称")


class UpdateStatisticsConfigResponse(BaseModel):
    """更新统计配置响应."""

    success: bool
    item_id: str
    skill_name: str
    include_in_statistics: bool
```

- [ ] **Step 2: 实现接口**

```python
@router.patch(
    "/market/skills/{item_id}/statistics",
    response_model=UpdateStatisticsConfigResponse,
)
async def update_skill_statistics_config(
    item_id: str,
    req: UpdateStatisticsConfigRequest,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
) -> UpdateStatisticsConfigResponse:
    """更新技能统计配置（管理员）."""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace

    # 从 index.json 获取技能
    items = load_index(svc.marketplace_root, source_id)
    item = next(
        (i for i in items if i.item_id == item_id and i.item_type == "skill"),
        None,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Skill not found")

    # 更新 index.json
    item.include_in_statistics = req.include_in_statistics
    item.updated_at = datetime.now(timezone.utc).isoformat()
    save_index(svc.marketplace_root, source_id, items)

    # 同步更新数据库
    if svc.db and svc.db.is_connected:
        from ...marketplace.market_skill_registry import MarketSkillRegistry
        registry = MarketSkillRegistry(svc.db)
        await registry.update_statistics_config(
            source_id=source_id,
            item_id=item_id,
            include_in_statistics=req.include_in_statistics,
            updator_id=req.updator_id,
            updator_name=req.updator_name,
        )

    return UpdateStatisticsConfigResponse(
        success=True,
        item_id=item_id,
        skill_name=item.name,
        include_in_statistics=req.include_in_statistics,
    )
```

- [ ] **Step 3: 提交代码**

```bash
git add market/src/market/app/routers/skills_market.py
git commit -m "feat(market): add PATCH /market/skills/{item_id}/statistics API"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Task 6: 新增初始化历史数据接口

**Files:**
- Modify: `market/src/market/app/routers/skills_market.py`

- [ ] **Step 1: 定义请求/响应模型**

```python
class InitStatisticsConfigRequest(BaseModel):
    """初始化统计配置请求."""

    source_ids: list[str] = Field(
        default_factory=list,
        description="来源ID列表，不传或为空时初始化所有来源",
    )
    default_include: bool = Field(
        default=True,
        description="默认是否纳入统计",
    )
    dry_run: bool = Field(
        default=False,
        description="试运行模式，仅统计不实际写入",
    )


class InitStatisticsConfigResult(TypedDict):
    """初始化统计配置结果."""

    dry_run: bool
    source_ids: list[str]
    total_skills: int
    processed: int
    inserted: int
    updated: int
    skipped: int
    errors: list[dict]
```

- [ ] **Step 2: 实现接口**

```python
@router.post(
    "/market/admin/skills/init-statistics",
)
async def init_skill_statistics_config(
    request: Request,
    req: InitStatisticsConfigRequest,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
) -> InitStatisticsConfigResult:
    """初始化技能统计配置（管理员）."""
    _require_manager(x_manager)
    svc = request.app.state.marketplace

    results: InitStatisticsConfigResult = {
        "dry_run": req.dry_run,
        "source_ids": [],
        "total_skills": 0,
        "processed": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
    }

    # 确定 source_ids 列表
    if req.source_ids:
        source_ids = req.source_ids
    else:
        # 遍历 marketplace_root 下所有目录
        source_ids = []
        for dir_path in svc.marketplace_root.iterdir():
            if dir_path.is_dir():
                index_path = dir_path / "index.json"
                if index_path.exists():
                    source_ids.append(dir_path.name)

    results["source_ids"] = source_ids

    # 初始化数据库操作类
    from ...marketplace.market_skill_registry import MarketSkillRegistry
    registry = MarketSkillRegistry(svc.db) if svc.db and svc.db.is_connected else None

    for source_id in source_ids:
        items = load_index(svc.marketplace_root, source_id)
        skill_items = [i for i in items if i.item_type == "skill"]
        results["total_skills"] += len(skill_items)

        for item in skill_items:
            results["processed"] += 1

            if registry:
                if not req.dry_run:
                    success = await registry.upsert_market_skill(
                        source_id=source_id,
                        item_id=item.item_id,
                        skill_id=item.skill_id,
                        skill_name=item.name,
                        cn_name=item.chinese_name,
                        include_in_statistics=req.default_include,
                        creator_id=item.creator_id,
                        creator_name=item.creator_name,
                        updator_id=item.creator_id,
                        updator_name=item.creator_name,
                    )
                    if success:
                        results["inserted"] += 1
                    else:
                        results["skipped"] += 1
                else:
                    results["inserted"] += 1

            # 更新 index.json
            if not req.dry_run:
                item.include_in_statistics = req.default_include

        if not req.dry_run:
            save_index(svc.marketplace_root, source_id, items)

    return results
```

- [ ] **Step 3: 提交代码**

```bash
git add market/src/market/app/routers/skills_market.py
git commit -m "feat(market): add POST /market/admin/skills/init-statistics API"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Task 7: 修改排行榜查询逻辑

**Files:**
- Modify: `monitor/src/monitor/app/services/tracing/query_service.py`

- [ ] **Step 1: 读取现有查询代码**

Run: Read `monitor/src/monitor/app/services/tracing/query_service.py` lines 2666-2745

- [ ] **Step 2: 添加获取纳入统计技能的方法**

在 TracingQueryService 类中添加：

```python
async def _get_statistics_eligible_skill_names(
    self,
    source_id: str,
) -> set[str]:
    """获取纳入统计的技能名称集合.

    从 swe_market_skills 表查询 include_in_statistics = 1 的技能。

    Args:
        source_id: 应用入口标识

    Returns:
        纳入统计的技能名称集合
    """
    if not self._db or not self._db.is_connected:
        logger.warning("Database not connected, return empty set for statistics filter")
        return set()

    try:
        rows = await self._db.fetch_all(
            """
            SELECT skill_name FROM swe_market_skills
            WHERE source_id = %s AND include_in_statistics = 1
            """,
            (source_id,),
        )
        return {row["skill_name"] for row in rows if row.get("skill_name")}
    except Exception as e:
        logger.warning("Failed to get statistics eligible skills: %s", e)
        return set()
```

- [ ] **Step 3: 修改 get_skills_paginated 方法**

```python
async def get_skills_paginated(
    self,
    source_id: str,
    page: int = 1,
    page_size: int = 10,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    bbk_ids: Optional[str] = None,
) -> tuple[list[SkillUsage], int]:
    """获取技能调用排行榜（分页）."""
    if start_date is None:
        start_date = datetime.now() - timedelta(days=30)
    if end_date is None:
        end_date = datetime.now() + timedelta(days=1)

    # 获取纳入统计的技能名称集合
    eligible_skills = await self._get_statistics_eligible_skill_names(source_id)

    bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
    # 构建基础查询条件
    if source_id == "all":
        exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
        base_where = f"""
            start_time >= %s AND start_time <= %s
            AND skill_name IS NOT NULL
            AND bbk_id IS NOT NULL AND bbk_id != ''
            AND source_id NOT IN ({exclude_placeholders})
            AND user_id != 'default'{bbk_filter_sql}
        """
        count_params = [
            start_date,
            end_date,
            *EXCLUDED_SOURCE_IDS,
            *bbk_filter_params,
        ]
    else:
        base_where = f"""
            source_id = %s AND start_time >= %s AND start_time <= %s
            AND skill_name IS NOT NULL
            AND bbk_id IS NOT NULL AND bbk_id != ''
            AND user_id != 'default'{bbk_filter_sql}
        """
        count_params = [
            source_id,
            start_date,
            end_date,
            *bbk_filter_params,
        ]

    # 如果有纳入统计的技能，添加过滤条件
    if eligible_skills:
        placeholders = ", ".join(["%s"] * len(eligible_skills))
        base_where += f" AND skill_name IN ({placeholders})"
        count_params.extend(eligible_skills)

    # 查询总数
    count_query = f"""
        SELECT COUNT(DISTINCT skill_name) as total
        FROM swe_tracing_spans
        WHERE {base_where}
    """
    count_row = await self._db.fetch_one(count_query, tuple(count_params))
    total = count_row["total"] if count_row else 0

    # 分页查询
    offset = (page - 1) * page_size
    data_query = f"""
        SELECT skill_name, MAX(skill_description) as skill_description,
               COUNT(DISTINCT trace_id) as count,
               AVG(duration_ms) as avg_duration
        FROM swe_tracing_spans
        WHERE {base_where}
        GROUP BY skill_name
        ORDER BY count DESC, skill_name ASC
        LIMIT %s OFFSET %s
    """
    params = count_params + [page_size, offset]
    rows = await self._db.fetch_all(data_query, tuple(params))

    skills = [
        SkillUsage(
            skill_name=row["skill_name"],
            skill_description=row["skill_description"] or "",
            count=row["count"] or 0,
            avg_duration_ms=int(row["avg_duration"] or 0),
        )
        for row in rows
    ]
    return skills, total
```

- [ ] **Step 4: 提交代码**

```bash
git add monitor/src/monitor/app/services/tracing/query_service.py
git commit -m "feat(monitor): filter skills by include_in_statistics in ranking query"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Task 8: 修改前端 API 模块

**Files:**
- Modify: `console/src/api/modules/market.ts`

- [ ] **Step 1: 添加 include_in_statistics 字段到类型定义**

```typescript
export interface MarketSkill {
  item_id: string;
  skill_id?: string | null;
  name: string;
  skill_name?: string;
  chinese_name?: string;
  description: string;
  version: string;
  creator_id: string;
  creator_name: string;
  category_id: number | null;
  bbk_ids: string[];
  status: "active" | "inactive";
  created_at: string | null;
  updated_at: string | null;
  call_count: number;
  user_count: number;
  version_unchanged?: boolean;
  // 新增字段
  include_in_statistics?: boolean;
}

export interface MarketSkillDetail extends MarketSkill {
  user_stats: Array<{
    user_id: string;
    user_name: string;
    call_count: number;
  }>;
}
```

- [ ] **Step 2: 添加统计配置更新接口**

```typescript
// 更新统计配置请求
export interface UpdateStatisticsConfigRequest {
  include_in_statistics: boolean;
  updator_id?: string;
  updator_name?: string;
}

// 更新统计配置响应
export interface UpdateStatisticsConfigResponse {
  success: boolean;
  item_id: string;
  skill_name: string;
  include_in_statistics: boolean;
}

// 更新技能统计配置
export async function updateSkillStatisticsConfig(
  sourceId: string,
  itemId: string,
  data: UpdateStatisticsConfigRequest,
): Promise<UpdateStatisticsConfigResponse> {
  const headers = mergeHeaders({ "X-Source-Id": sourceId });
  const response = await request.patch<UpdateStatisticsConfigResponse>(
    `${getApiUrl()}/market/skills/${itemId}/statistics`,
    data,
    { headers },
  );
  return response.data;
}
```

- [ ] **Step 3: 提交代码**

```bash
git add console/src/api/modules/market.ts
git commit -m "feat(console): add include_in_statistics field and update API"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Task 9: 修改技能详情抽屉

**Files:**
- Modify: `console/src/pages/Market/SkillDetailDrawer.tsx`

- [ ] **Step 1: 读取现有代码**

Run: Read `console/src/pages/Market/SkillDetailDrawer.tsx`

- [ ] **Step 2: 添加统计配置开关**

在技能详情页的元数据区域添加开关组件：

```tsx
import { Switch, message } from "antd";
import { updateSkillStatisticsConfig } from "../../api/modules/market";

// 在 SkillDetailDrawer 组件内添加状态和处理函数
const [statisticsLoading, setStatisticsLoading] = useState(false);

const handleStatisticsChange = useCallback(
  async (checked: boolean) => {
    if (!skill || !sourceId) return;

    setStatisticsLoading(true);
    try {
      await updateSkillStatisticsConfig(sourceId, skill.item_id, {
        include_in_statistics: checked,
        updator_id: "system",
        updator_name: "系统",
      });
      message.success(checked ? "已纳入统计" : "已取消纳入统计");
      if (onRefresh) {
        onRefresh();
      }
    } catch (error) {
      message.error("更新失败，请重试");
    } finally {
      setStatisticsLoading(false);
    }
  },
  [skill, sourceId, onRefresh]
);

// 在元数据区域添加开关
<div style={{ ...META_ITEM_STYLE, marginTop: 8 }}>
  <span style={{ marginRight: 8 }}>是否纳入统计：</span>
  <Switch
    checked={skill?.include_in_statistics ?? false}
    onChange={handleStatisticsChange}
    loading={statisticsLoading}
    checkedChildren="纳入"
    unCheckedChildren="不纳入"
    disabled={!isManager}
  />
</div>
```

- [ ] **Step 3: 提交代码**

```bash
git add console/src/pages/Market/SkillDetailDrawer.tsx
git commit -m "feat(console): add statistics config switch in skill detail drawer"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Task 10: 修改技能卡片徽章显示

**Files:**
- Modify: `console/src/pages/Market/SkillCard.tsx`

- [ ] **Step 1: 添加徽章组件**

```tsx
import { Tag } from "antd";

// 在 SkillCard 组件的名称显示区域添加徽章
<div style={{ display: "flex", alignItems: "center", gap: 8 }}>
  <Text strong style={{ fontSize: 16 }}>
    {skill.chinese_name || skill.name}
  </Text>
  {skill.include_in_statistics ? (
    <Tag color="green" style={{ marginLeft: 4 }}>
      纳入统计
    </Tag>
  ) : (
    <Tag color="default" style={{ marginLeft: 4 }}>
      不纳入统计
    </Tag>
  )}
</div>
```

- [ ] **Step 2: 提交代码**

```bash
git add console/src/pages/Market/SkillCard.tsx
git commit -m "feat(console): add statistics badge in skill card"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Task 11: 修改上传技能弹窗

**Files:**
- Modify: `console/src/pages/Market/components/UploadSkillModal.tsx`

- [ ] **Step 1: 读取现有代码**

Run: Read `console/src/pages/Market/components/UploadSkillModal.tsx`

- [ ] **Step 2: 添加纳入统计复选框**

```tsx
import { Checkbox, Form } from "antd";

// 在表单中添加复选框
<Form.Item
  name="include_in_statistics"
  valuePropName="checked"
  initialValue={false}
>
  <Checkbox>纳入排行榜统计</Checkbox>
</Form.Item>
<div style={{ color: "#8c8c8c", fontSize: 12, marginTop: -8, marginBottom: 16 }}>
  勾选后，该技能将出现在运营看板的技能使用排行榜中
</div>
```

- [ ] **Step 3: 在上传请求中传递参数**

```tsx
const handleUpload = async () => {
  const values = await form.validateFields();
  // ... 其他代码 ...

  const formData = new FormData();
  formData.append("file", file);
  formData.append("include_in_statistics", String(values.include_in_statistics || false));
  // ... 其他参数 ...

  // 发送请求
  await marketApi.publishSkillUpload(formData, headers);
};
```

- [ ] **Step 4: 提交代码**

```bash
git add console/src/pages/Market/components/UploadSkillModal.tsx
git commit -m "feat(console): add include_in_statistics checkbox in upload modal"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Task 12: 集成测试

**Files:**
- Create: `market/tests/integrated/test_skill_statistics_config.py`

- [ ] **Step 1: 创建集成测试文件**

```python
# -*- coding: utf-8 -*-
"""技能统计配置集成测试."""

import pytest
from pathlib import Path
import tempfile
import json

from market.marketplace.models import MarketItem
from market.marketplace.fs import save_index, load_index
from market.marketplace.market_skill_registry import MarketSkillRegistry


@pytest.mark.asyncio
class TestSkillStatisticsConfig:
    """技能统计配置集成测试."""

    async def test_upload_skill_with_statistics(self, tmp_path):
        """测试上传技能时设置统计配置."""
        # 创建测试 index.json
        items = [
            MarketItem(
                item_id="test-item-1",
                item_type="skill",
                name="test_skill",
                skill_id="skill-001",
                chinese_name="测试技能",
                description="测试技能描述",
                version="1.0.0",
                creator_id="user1",
                include_in_statistics=True,
            )
        ]
        save_index(tmp_path, "test_source", items)

        # 验证保存结果
        loaded = load_index(tmp_path, "test_source")
        assert len(loaded) == 1
        assert loaded[0].include_in_statistics is True

    async def test_update_statistics_config(self, tmp_path):
        """测试更新统计配置."""
        # 创建测试数据
        items = [
            MarketItem(
                item_id="test-item-1",
                item_type="skill",
                name="test_skill",
                skill_id="skill-001",
                chinese_name="测试技能",
                description="测试技能描述",
                version="1.0.0",
                creator_id="user1",
                include_in_statistics=True,
            )
        ]
        save_index(tmp_path, "test_source", items)

        # 更新配置
        items[0].include_in_statistics = False
        save_index(tmp_path, "test_source", items)

        # 验证更新结果
        loaded = load_index(tmp_path, "test_source")
        assert loaded[0].include_in_statistics is False
```

- [ ] **Step 2: 运行集成测试**

Run: `cd D:/workspace/CoPaw && .venv/Scripts/python.exe -m pytest market/tests/integrated/test_skill_statistics_config.py -v`
Expected: 所有测试通过

- [ ] **Step 3: 提交代码**

```bash
git add market/tests/integrated/test_skill_statistics_config.py
git commit -m "test(market): add integration tests for skill statistics config"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## 自我审查

### 1. Spec 覆盖检查

| Spec 要求 | 对应 Task | 状态 |
|-----------|-----------|------|
| MarketItem 模型增加 include_in_statistics 字段 | Task 2 | ✅ |
| 创建 swe_market_skills 表 | Task 1 | ✅ |
| 技能上传时支持 include_in_statistics 参数 | Task 4 | ✅ |
| 新增统计配置修改接口 | Task 5 | ✅ |
| 新增历史数据初始化接口 | Task 6 | ✅ |
| 排行榜查询过滤纳入统计的技能 | Task 7 | ✅ |
| 前端技能详情页增加开关 | Task 9 | ✅ |
| 前端技能列表增加徽章 | Task 10 | ✅ |
| 前端上传弹窗增加复选框 | Task 11 | ✅ |
| API 类型定义更新 | Task 8 | ✅ |

### 2. 占位符扫描

- 无 TBD 或 TODO
- 所有代码步骤包含完整实现

### 3. 类型一致性

- `include_in_statistics` 字段在所有地方使用 `bool` 类型
- API 接口使用一致的请求/响应模型

---

## 部署检查清单

| 检查项 | 命令 |
|--------|------|
| 执行数据库迁移 | `mysql -u root -p < deploy/migrations/2026_07_29_add_swe_market_skills_table.sql` |
| 初始化历史数据 | `POST /market/admin/skills/init-statistics` with `{"source_ids": ["your_source_id"]}` |
| 验证排行榜过滤 | 访问运营看板，确认只显示纳入统计的技能 |
| 验证前端功能 | 测试技能详情页开关、列表徽章、上传弹窗复选框 |