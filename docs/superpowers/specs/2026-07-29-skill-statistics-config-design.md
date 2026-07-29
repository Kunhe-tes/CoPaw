# 技能统计配置功能设计

**日期**：2026-07-29
**状态**：待实现
**作者**：Claude

---

## 概述

### 背景

运营看板的"技能使用排行榜"需要支持管理员配置哪些技能纳入统计，以便只展示业务关注的核心技能，而非所有技能。

### 目标

1. 在应用市场上传/同步技能时，增加"是否纳入统计"的可选配置
2. 支持管理员后续修改统计配置
3. 技能排行榜只展示纳入统计的技能
4. 历史数据默认纳入统计

### 范围

- **Market 服务**：技能上传、同步、统计配置管理
- **Monitor 服务**：排行榜查询过滤
- **Console 前端**：技能详情页、列表页、上传弹窗

---

## 设计决策

### 关键决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 配置范围 | 市场层面配置 | 统计配置是市场级属性，非租户级 |
| 未纳入统计的技能 | 完全不出现 | 保持排行榜简洁，避免混淆 |
| 数据存储 | index.json + 数据库表 | index.json 作为数据源，数据库表用于高效查询 |
| 数据同步 | 实时同步 | 保证数据一致性 |
| 默认值 | 历史数据纳入，新技能不纳入 | 历史数据迁移成本低，新技能需显式配置 |

---

## 数据模型

### 1. MarketItem 模型修改

**文件**：`market/src/market/marketplace/models.py`

```python
class MarketItem(BaseModel):
    """市场条目（index.json 中的单条记录）."""

    item_id: str
    item_type: str = "skill"
    name: str
    skill_id: str = ""
    chinese_name: str = ""
    description: str = ""
    # ... 其他现有字段 ...

    # 新增字段：是否纳入统计（仅对 skill 类型生效）
    include_in_statistics: bool = False  # 默认不纳入统计
```

**说明**：
- 只对 `item_type == "skill"` 的条目生效
- 默认值为 `False`，新上传的技能需要显式勾选才纳入统计
- 历史数据通过初始化接口设置为 `True`

---

### 2. 数据库表设计

**新建表**：`swe_market_skills`

```sql
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

**说明**：
- 按 `source_id + item_id` 唯一约束，防止重复
- `include_in_statistics` 字段用于排行榜过滤
- 索引优化查询性能

---

## API 接口设计

### 1. 新增接口

#### 1.1 修改统计配置

**接口**：`PATCH /market/skills/{item_id}/statistics`

**权限**：管理员（X-Manager: true）

**请求体**：
```json
{
    "include_in_statistics": false,
    "updator_id": "admin001",
    "updator_name": "管理员"
}
```

**响应**：
```json
{
    "success": true,
    "item_id": "abc-123",
    "skill_name": "数据分析",
    "include_in_statistics": false
}
```

**处理逻辑**：
1. 验证管理员权限
2. 更新 index.json 中的 `include_in_statistics` 字段
3. 同步更新 swe_market_skills 表

---

#### 1.2 初始化历史数据

**接口**：`POST /market/admin/skills/init-statistics`

**权限**：管理员（X-Manager: true）

**请求体**：
```json
{
    "source_ids": ["dqb_source", "test_source"],
    "default_include": true,
    "dry_run": false
}
```

**响应**：
```json
{
    "dry_run": false,
    "source_ids": ["dqb_source", "test_source"],
    "total_skills": 50,
    "processed": 50,
    "inserted": 48,
    "updated": 2,
    "skipped": 0,
    "errors": []
}
```

**处理逻辑**：
1. 遍历指定 source_ids 的 index.json
2. 过滤 `item_type == "skill"` 的条目
3. 插入到 swe_market_skills 表（UPSERT）
4. 默认 `include_in_statistics = 1`
5. 支持 dry_run 模式预览

---

### 2. 修改现有接口

#### 2.1 技能上传接口

**接口**：`POST /market/skills/publish-upload`

**新增请求参数**：
- `include_in_statistics`: `false`（默认）/`true`

**修改逻辑**：
- 技能上传时设置 `include_in_statistics` 字段
- 同时写入 index.json 和 swe_market_skills 表

---

#### 2.2 技能同步接口

**接口**：`POST /market/skills`

**新增请求参数**：
- `include_in_statistics`: `false`（默认）/`true`

**修改逻辑**：
- 技能同步时设置 `include_in_statistics` 字段
- 同时更新 index.json 和 swe_market_skills 表

---

### 3. 查询接口修改

#### 3.1 排行榜查询

**接口**：`GET /monitor/tracing/skills`

**修改逻辑**：
- 新增 JOIN 关联 swe_market_skills 表
- 过滤 `include_in_statistics = 1` 的技能

**修改后的 SQL（简化版）**：
```sql
SELECT s.skill_name, MAX(s.skill_description) as skill_description,
       COUNT(DISTINCT s.trace_id) as count,
       AVG(s.duration_ms) as avg_duration
FROM swe_tracing_spans s
INNER JOIN swe_market_skills m
    ON s.skill_name = m.skill_name
    AND m.source_id = %s
    AND m.include_in_statistics = 1
WHERE s.source_id = %s
    AND s.start_time >= %s
    AND s.start_time <= %s
    AND s.skill_name IS NOT NULL
    AND s.user_id != 'default'
GROUP BY s.skill_name
ORDER BY count DESC
```

---

## 数据同步流程

### 1. 技能上传流程

```
用户上传技能 ZIP 文件
    ↓
Market 服务解析 ZIP 文件
    ↓
创建 MarketItem 对象（include_in_statistics 默认 false）
    ↓
写入 index.json（包含 include_in_statistics 字段）
    ↓
同步写入 swe_market_skills 表
    ↓
返回上传结果
```

### 2. 技能同步流程

```
用户空间同步技能到市场
    ↓
Market 服务调用 publish_skill()
    ↓
更新 MarketItem 对象
    ↓
更新 index.json
    ↓
同步更新 swe_market_skills 表（UPSERT）
    ↓
返回同步结果
```

### 3. 统计配置修改流程

```
管理员修改统计配置
    ↓
Market 服务验证权限
    ↓
更新 index.json 中的 include_in_statistics 字段
    ↓
同步更新 swe_market_skills 表
    ↓
返回修改结果
```

### 4. 历史数据初始化流程

```
管理员调用初始化接口
    ↓
遍历指定 source_ids 的 index.json
    ↓
过滤 item_type == "skill" 的条目
    ↓
批量插入到 swe_market_skills 表（默认 include_in_statistics = 1）
    ↓
返回初始化统计
```

---

## 前端设计

### 1. 技能详情页修改

**文件**：`console/src/pages/Market/SkillDetail/index.tsx`（或类似路径）

**修改内容**：
- 增加一个 Switch 组件，控制 `include_in_statistics` 字段
- 调用 `PATCH /market/skills/{item_id}/statistics` 接口更新配置
- 显示更新人和更新时间

**UI 布局**：
```
┌─────────────────────────────────────┐
│ 基本信息                              │
├─────────────────────────────────────┤
│ 技能名称：数据分析                     │
│ 中文名称：数据分析技能                  │
│ 技能描述：...                         │
│ 所属分类：数据分析                     │
│ 所属分行：总行、分行A                   │
│ 是否纳入统计：[开关] 🔵                │ ← 新增
│ 创建人：张三                           │
│ 更新时间：2026-07-29 10:00:00         │
└─────────────────────────────────────┘
```

---

### 2. 技能列表徽章显示

**文件**：`console/src/pages/Market/SkillList/index.tsx`（或类似路径）

**修改内容**：
- 在技能名称列增加 Badge 组件
- 根据 `include_in_statistics` 字段显示不同样式

**徽章样式**：
- 纳入统计：绿色背景，白色文字，显示"纳入统计"
- 不纳入统计：灰色背景，白色文字，显示"不纳入统计"

---

### 3. 技能上传/同步弹窗修改

**文件**：`console/src/pages/Market/PublishSkillModal/index.tsx`（或类似路径）

**修改内容**：
- 增加一个 Checkbox 组件，控制 `include_in_statistics` 字段
- 默认不勾选
- 提示文字：勾选后，该技能将出现在运营看板的技能使用排行榜中

---

## 错误处理

### 1. 数据同步失败

| 场景 | 处理策略 |
|------|----------|
| index.json 写入成功，数据库写入失败 | 记录日志，返回部分成功状态，建议重试 |
| 数据库写入成功，index.json 写入失败 | 事务回滚，返回失败状态 |
| 并发修改冲突 | 使用乐观锁，返回冲突提示，建议刷新后重试 |

### 2. API 错误响应

**数据库连接失败**：
```json
{
    "detail": {
        "code": "DATABASE_ERROR",
        "message": "数据库连接失败，请稍后重试"
    }
}
```

**技能不存在**：
```json
{
    "detail": {
        "code": "SKILL_NOT_FOUND",
        "message": "技能不存在"
    }
}
```

---

## 测试策略

### 1. 单元测试

| 测试项 | 测试内容 |
|--------|----------|
| MarketItem 模型 | 验证 `include_in_statistics` 字段序列化/反序列化 |
| 数据库操作 | 验证 INSERT/UPDATE/SELECT 操作 |
| API 接口 | 验证请求参数校验、权限校验 |

### 2. 集成测试

| 测试项 | 测试内容 |
|--------|----------|
| 技能上传流程 | 验证 index.json 和数据库同步写入 |
| 统计配置修改 | 验证配置更新后排行榜正确过滤 |
| 初始化接口 | 验证历史数据正确初始化 |

### 3. 性能测试

| 测试项 | 预期结果 |
|--------|----------|
| 排行榜查询（关联数据库） | < 100ms（1000 条记录） |
| 技能上传（含数据库同步） | < 500ms |
| 初始化接口（1000 个技能） | < 10s |

---

## 部署检查清单

| 检查项 | 说明 |
|--------|------|
| 数据库迁移 | 执行 `swe_market_skills` 表创建脚本 |
| 历史数据初始化 | 调用初始化接口迁移历史数据 |
| 前端部署 | 更新技能详情页、列表页、上传弹窗 |
| 接口权限验证 | 验证管理员权限控制 |

---

## 实现文件清单

### Market 服务

| 文件 | 修改内容 |
|------|----------|
| `market/src/market/marketplace/models.py` | MarketItem 增加 include_in_statistics 字段 |
| `market/src/market/marketplace/service.py` | 技能上传/同步时同步写入数据库 |
| `market/src/market/app/routers/skills_market.py` | 新增统计配置修改接口、初始化接口 |
| `deploy/migrations/XXXX_add_swe_market_skills_table.sql` | 新建 swe_market_skills 表 |

### Monitor 服务

| 文件 | 修改内容 |
|------|----------|
| `monitor/src/monitor/app/services/tracing/query_service.py` | 排行榜查询增加 JOIN 和过滤逻辑 |

### Console 前端

| 文件 | 修改内容 |
|------|----------|
| `console/src/pages/Market/SkillDetail/index.tsx` | 增加统计配置开关 |
| `console/src/pages/Market/SkillList/index.tsx` | 增加徽章显示 |
| `console/src/pages/Market/PublishSkillModal/index.tsx` | 增加纳入统计复选框 |
| `console/src/api/modules/market.ts` | 增加统计配置修改接口 |

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 数据同步失败 | index.json 与数据库不一致 | 提供数据校验接口，支持手动修复 |
| 排行榜查询性能下降 | JOIN 操作增加查询时间 | 优化索引，监控查询性能 |
| 历史数据迁移耗时 | 初始化接口执行时间长 | 支持分批初始化，提供进度反馈 |

---

## 附录

### A. 相关文档

- [应用市场设计](../specs/2026-04-29-marketplace-design.md)
- [运营看板 UI 恢复设计](../specs/2026-05-16-business-overview-ui-restoration-design.md)

### B. 数据库迁移脚本

```sql
-- 文件: deploy/migrations/2026_07_29_add_swe_market_skills_table.sql

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