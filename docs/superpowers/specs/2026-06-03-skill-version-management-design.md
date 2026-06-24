# 应用市场技能版本管理设计文档

## 设计概述

为应用市场技能（Market Skills）添加完整的版本管理功能，支持版本历史查看、版本比对、版本切换/回滚和版本删除。采用 GitHub 风格的 UI 设计，提供清晰简洁的用户体验。

## 需求总结

### 功能范围

**目标对象**：应用市场技能（Market Skills）

- Market 服务管理的技能，包括用户创建和从 Market 分发的技能
- 对应前端"应用市场"页面

### 核心功能

| 功能 | 描述 |
|------|------|
| 查看版本历史 | 查看技能的所有历史版本，包括版本号、更新时间、变更描述 |
| 版本文件比对 | 比对任意两个版本的文件差异，包括 SKILL.md、references、scripts |
| 版本切换/回滚 | 将技能切换到指定的历史版本，类似 Git checkout |
| 删除历史版本 | 删除不需要的历史版本，节省存储空间 |

### 存储策略

**全量快照（完整副本）**

- 每次技能更新保存完整文件副本
- 实现简单可靠，回滚速度快
- 占用存储空间较多，但对于技能文件可接受

### 版本快照触发时机

| 场景 | 触发位置 | 说明 |
|------|----------|------|
| 我的技能同步同名技能到应用市场 | `service.py:publish_skill()` 第 727-750 行 | 复制技能目录后创建版本快照 |
| 应用市场上传同名技能 | `skills_market.py:_process_single_skill()` 第 228-294 行 | 处理 zip 上传后创建版本快照 |

**触发逻辑**：

```python
# 在 publish_skill() 中集成版本快照创建
async def publish_skill(...) -> MarketItem:
    # ... 现有上架逻辑 ...

    # 创建版本快照
    version_svc = SkillVersionService(self.marketplace_root)
    version_svc.create_version_snapshot(
        source_id=source_id,
        item_id=item.item_id,
        skill_dir=skill_dir,
        description=f"上架版本 {item.version}",
        creator=item.creator_name,
    )

    return item
```

**版本快照存储位置**：

```
<marketplace_root>/<source_id>/skill_versions/<item_id>/
├── versions.json                  # 版本清单文件
├── v2.3.0/                        # 版本快照目录
│   ├── SKILL.md
│   ├── skill.json
│   ├── references/
│   └── scripts/
├── v2.2.0/
│   └── ...
└── v1.0.0/
    └── ...
```

### 前端集成

**新增 API 模块**：`console/src/api/modules/skillVersion.ts`

```typescript
export interface SkillVersion {
  version_id: string;
  created_at: string;
  created_by: string;
  description: string;
  is_current: boolean;
  is_initial: boolean;
}

export interface VersionCompareResult {
  base_version: string;
  target_version: string;
  stats: {
    added_lines: number;
    deleted_lines: number;
    changed_files: number;
  };
  files: Array<{
    path: string;
    added_lines: number;
    deleted_lines: number;
    diff: string;
  }>;
}

export const skillVersionApi = {
  listVersions: (sourceId, itemId) => ...,
  getVersionDetail: (sourceId, itemId, versionId) => ...,
  switchVersion: (sourceId, itemId, versionId) => ...,
  compareVersions: (sourceId, itemId, baseVersion, targetVersion) => ...,
  deleteVersion: (sourceId, itemId, versionId) => ...,
};
```

**新增页面组件**：

| 组件路径 | 职责 |
|----------|------|
| `console/src/pages/Market/Skills/VersionHistory.tsx` | 版本历史列表组件 |
| `console/src/pages/Market/Skills/VersionCompare.tsx` | 版本比对页面组件 |

**集成到技能详情页**：

在现有的技能详情页中添加版本历史面板入口：

```tsx
// 在 SkillDetail 页面中
<SkillDetailTabs>
  <Tab label="基本信息">...</Tab>
  <Tab label="文件预览">...</Tab>
  <Tab label="版本历史">
    <VersionHistoryPanel itemId={skill.item_id} />
  </Tab>
</SkillDetailTabs>
```

## 现有代码分析

### Market 服务结构

**服务目录**：`market/src/market/`

| 目录/文件 | 职责 |
|-----------|------|
| `marketplace/service.py` | 核心业务服务，包含上架、分发、撤回等逻辑 |
| `marketplace/fs.py` | 文件系统工具，提供 `load_index`、`save_index`、`get_skill_dir` 等函数 |
| `marketplace/models.py` | 数据模型，定义 `MarketItem`、`CategoryItem` |
| `app/routers/skills_market.py` | 管理员 API 路由，上架、下架、分发、撤回等端点 |
| `app/routers/skills_browse.py` | 用户浏览 API 路由，列表、详情、文件预览等端点 |

### 现有存储结构

**市场索引文件**：`<marketplace_root>/<source_id>/index.json`

```json
[
  {
    "item_id": "abc-123",
    "item_type": "skill",
    "name": "数据分析技能",
    "version": "2.3.0",
    "description": "...",
    "creator_id": "user1",
    "creator_name": "张三",
    "status": "active",
    "created_at": "2026-06-03T14:30:00Z",
    "updated_at": "2026-06-03T14:30:00Z"
  }
]
```

**技能文件目录**：`<marketplace_root>/<source_id>/skills/<item_id>/`

```
skills/<item_id>/
├── skill.json
├── SKILL.md
├── references/
│   └── data_template.md
└── scripts/
    └── analyze.py
```

### 关键函数

| 函数 | 位置 | 用途 |
|------|------|------|
| `load_index()` | `fs.py` | 读取市场索引 |
| `save_index()` | `fs.py` | 写入市场索引 |
| `get_skill_dir()` | `fs.py` | 获取技能文件目录路径 |
| `_atomic_write_json()` | `fs.py` | 原子性写入 JSON 文件 |
| `publish_skill()` | `service.py` | 上架技能（含版本号递增 `_bump_patch`） |
| `_parse_md_frontmatter()` | `service.py` | 从 SKILL.md 解析 name、description |
| `_extract_version_from_frontmatter()` | `service.py` | 从 SKILL.md 提取 version |

### 现有版本字段

Market 服务已具备版本相关字段：

1. **MarketItem.version**：市场条目的版本号（如 `"2.3.0"`）
2. **SKILL.md frontmatter.version**：技能文件中的版本号
3. **`_bump_patch()` 函数**：版本号递增逻辑（`"1.0.0"` → `"1.0.1"`）

## 架构设计

### 方案选择

**方案 A：独立版本服务**

在 Market 服务中新增 `SkillVersionService`，专门管理技能版本。

**优势**：

- 职责清晰，版本管理与技能内容分离
- 易于扩展（未来可支持更多版本操作）
- 不影响现有技能管理逻辑
- 符合微服务设计原则

### 新增文件清单

| 文件路径 | 职责 |
|----------|------|
| `market/src/market/marketplace/version_service.py` | 版本管理服务核心逻辑 |
| `market/src/market/marketplace/version_models.py` | 版本数据模型（`SkillVersion`、`VersionCompareResult`） |
| `market/src/market/app/routers/skill_versions.py` | 版本管理 API 路由 |
| `market/tests/unit/marketplace/test_version_service.py` | 版本服务单元测试 |

### 需修改文件清单

| 文件路径 | 修改内容 |
|----------|----------|
| `market/src/market/marketplace/service.py` | 在 `publish_skill()` 中集成版本快照创建逻辑 |
| `market/src/market/app/routers/skills_market.py` | 在 `publish_skill_upload()` 中集成版本快照创建逻辑 |
| `market/src/market/app/routers/__init__.py` | 注册版本管理路由 |
| `console/src/api/modules/market.ts` | 新增版本管理 API 调用函数 |

### 数据模型

#### 市场技能存储结构

**设计原则**：
- 技能主目录（`skills/<item_id>/`）始终存储**当前版本**文件
- 版本历史存储在独立目录（`skill_versions/<item_id>/`）
- 市场技能列表**只展示最新版本**，版本历史在详情页查看

```
<marketplace_root>/<source_id>/
├── index.json                              # 市场索引（只记录最新版本信息）
├── skills/
│   └── <item_id>/                          # 当前版本文件
│       ├── skill.json
│       ├── SKILL.md
│       ├── references/
│       └── scripts/
└── skill_versions/
    └── <item_id>/                          # 版本历史目录
        ├── versions.json                   # 版本清单
        ├── v2.3.0/                         # 历史版本快照
        │   ├── skill.json
        │   ├── SKILL.md
        │   └── ...
        ├── v2.2.0/
        └── v1.0.0/
```

**版本清单 JSON 示例（versions.json）**：

```json
{
  "skill_name": "数据分析技能",
  "versions": [
    {
      "version_id": "v2.3.0",
      "created_at": "2026-06-03T14:30:00Z",
      "created_by": "张三",
      "description": "优化数据分析性能，新增实时数据处理功能",
      "signature": "sha256:abc123...",
      "is_current": true,
      "is_initial": false
    },
    {
      "version_id": "v2.2.0",
      "created_at": "2026-05-28T10:15:00Z",
      "created_by": "张三",
      "description": "新增数据可视化组件，支持图表导出",
      "signature": "sha256:def456...",
      "is_current": false,
      "is_initial": false
    },
    {
      "version_id": "v1.0.0",
      "created_at": "2026-04-10T10:00:00Z",
      "created_by": "张三",
      "description": "初始版本：基础数据分析功能",
      "signature": "sha256:ghi789...",
      "is_current": false,
      "is_initial": true
    }
  ]
}
```

**市场技能列表展示规则**：

| 场景 | 展示内容 |
|------|----------|
| 技能列表（`/market/skills`） | 只展示最新版本（`skills/<item_id>/` 目录的文件） |
| 技能详情页 | 展示当前版本详情 + 版本历史入口 |
| 版本比对 | 选择任意两个历史版本进行比对 |

**版本切换行为**：

- 切换版本后，将目标版本的文件复制到 `skills/<item_id>/` 目录
- 更新 `versions.json` 中的 `is_current` 标识
- 市场索引 `index.json` 的 `version` 字段随之更新

### 服务层设计

#### SkillVersionService

**文件位置**：`market/src/market/marketplace/version_service.py`

```python
# -*- coding: utf-8 -*-
"""技能版本管理服务."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SkillVersionService:
    """技能版本管理服务.

    管理市场技能的版本快照，支持创建、查询、切换、比对和删除版本。

    存储结构:
        <marketplace_root>/<source_id>/skill_versions/<item_id>/
        ├── versions.json
        ├── v2.3.0/
        │   ├── SKILL.md
        │   └── ...
        └── v2.2.0/
            └── ...
    """

    def __init__(self, marketplace_root: Path):
        self.marketplace_root = marketplace_root

    def create_version_snapshot(
        self,
        source_id: str,
        item_id: str,
        skill_dir: Path,
        description: str = "",
        creator: str = "",
    ) -> dict[str, Any]:
        """创建新版本快照.

        从 SKILL.md 提取版本号，若无则生成时间戳格式版本号。
        复制完整技能文件到版本快照目录，更新版本清单。

        Args:
            source_id: 来源 ID
            item_id: 条目 ID
            skill_dir: 当前技能文件目录
            description: 版本描述
            creator: 创建者名称

        Returns:
            创建的版本信息
        """
        pass

    def list_versions(
        self,
        source_id: str,
        item_id: str,
    ) -> list[dict[str, Any]]:
        """获取版本历史列表.

        Args:
            source_id: 来源 ID
            item_id: 条目 ID

        Returns:
            版本列表，按创建时间倒序排列
        """
        pass

    def get_version_detail(
        self,
        source_id: str,
        item_id: str,
        version_id: str,
    ) -> dict[str, Any]:
        """获取单个版本详情.

        Args:
            source_id: 来源 ID
            item_id: 条目 ID
            version_id: 版本 ID

        Returns:
            版本详情，包含文件树
        """
        pass

    def switch_version(
        self,
        source_id: str,
        item_id: str,
        target_version_id: str,
        skill_dir: Path,
    ) -> dict[str, Any]:
        """切换到指定版本.

        将目标版本的文件复制到技能主目录，更新版本清单中的 is_current 标识。

        Args:
            source_id: 来源 ID
            item_id: 条目 ID
            target_version_id: 目标版本 ID
            skill_dir: 当前技能文件目录（用于备份和覆盖）

        Returns:
            切换结果
        """
        pass

    def compare_versions(
        self,
        source_id: str,
        item_id: str,
        base_version_id: str,
        target_version_id: str,
    ) -> dict[str, Any]:
        """比对两个版本.

        对比文件列表和每个文件的内容差异，返回 Diff 详情。

        Args:
            source_id: 来源 ID
            item_id: 条目 ID
            base_version_id: 基准版本 ID
            target_version_id: 目标版本 ID

        Returns:
            比对结果，包含变更统计和文件差异
        """
        pass

    def delete_version(
        self,
        source_id: str,
        item_id: str,
        version_id: str,
    ) -> bool:
        """删除指定版本.

        不允许删除当前版本和初始版本。

        Args:
            source_id: 来源 ID
            item_id: 条目 ID
            version_id: 要删除的版本 ID

        Returns:
            是否删除成功
        """
        pass

    # === 内部方法 ===

    def _get_version_root(
        self,
        source_id: str,
        item_id: str,
    ) -> Path:
        """获取版本根目录路径."""
        return (
            self.marketplace_root
            / source_id
            / "skill_versions"
            / item_id
        )

    def _get_versions_json_path(
        self,
        source_id: str,
        item_id: str,
    ) -> Path:
        """获取版本清单文件路径."""
        return self._get_version_root(source_id, item_id) / "versions.json"

    def _load_versions_manifest(
        self,
        source_id: str,
        item_id: str,
    ) -> dict[str, Any]:
        """加载版本清单文件."""
        path = self._get_versions_json_path(source_id, item_id)
        if not path.exists():
            return {"versions": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_versions_manifest(
        self,
        source_id: str,
        item_id: str,
        manifest: dict[str, Any],
    ) -> None:
        """保存版本清单文件."""
        path = self._get_versions_json_path(source_id, item_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _extract_version_from_skill_md(
        self,
        skill_dir: Path,
    ) -> str:
        """从 SKILL.md 提取版本号，若无则生成时间戳格式."""
        skill_md_path = skill_dir / "SKILL.md"
        if skill_md_path.exists():
            version = _extract_version_from_frontmatter(
                skill_md_path.read_text(encoding="utf-8")
            )
            if version:
                return version
        # 生成时间戳格式版本号
        return datetime.now(timezone.utc).strftime("v%Y%m%d%H%M%S")

    def _calculate_signature(
        self,
        skill_dir: Path,
    ) -> str:
        """计算技能目录内容签名."""
        digest = hashlib.sha256()
        for path in sorted(skill_dir.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                rel = path.relative_to(skill_dir)
                digest.update(str(rel).encode("utf-8"))
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def _copy_skill_to_version(
        self,
        source_dir: Path,
        target_dir: Path,
    ) -> None:
        """复制技能文件到版本目录."""
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)

    def _compute_file_diff(
        self,
        base_content: str,
        target_content: str,
    ) -> list[dict[str, Any]]:
        """计算文件内容差异."""
        # 使用 difflib 或类似库实现
        pass
```

### API 设计

#### 版本管理端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/market/skills/{item_id}/versions` | 获取版本历史列表 |
| GET | `/market/skills/{item_id}/versions/{version_id}` | 获取单个版本详情 |
| POST | `/market/skills/{item_id}/versions/{version_id}/switch` | 切换到指定版本 |
| POST | `/market/skills/{item_id}/versions/compare` | 比对两个版本 |
| DELETE | `/market/skills/{item_id}/versions/{version_id}` | 删除指定版本 |

#### 请求/响应示例

**获取版本历史列表**：

```json
// GET /market/skills/abc123/versions
{
  "versions": [
    {
      "version_id": "v2.3.0",
      "created_at": "2026-06-03T14:30:00Z",
      "created_by": "张三",
      "description": "优化数据分析性能，新增实时数据处理功能",
      "is_current": true,
      "is_initial": false
    },
    {
      "version_id": "v2.2.0",
      "created_at": "2026-05-28T10:15:00Z",
      "created_by": "张三",
      "description": "新增数据可视化组件，支持图表导出",
      "is_current": false,
      "is_initial": false
    }
  ],
  "total": 5
}
```

**比对两个版本**：

```json
// POST /market/skills/abc123/versions/compare
{
  "base_version_id": "v2.2.0",
  "target_version_id": "v2.3.0"
}

// Response
{
  "base_version": "v2.2.0",
  "target_version": "v2.3.0",
  "stats": {
    "added_lines": 12,
    "deleted_lines": 5,
    "changed_files": 3
  },
  "files": [
    {
      "path": "SKILL.md",
      "added_lines": 8,
      "deleted_lines": 3,
      "diff": "..."
    },
    {
      "path": "references/data_template.md",
      "added_lines": 4,
      "deleted_lines": 0,
      "diff": "..."
    },
    {
      "path": "scripts/analyze.py",
      "added_lines": 0,
      "deleted_lines": 2,
      "diff": "..."
    }
  ]
}
```

## UI 设计

### 设计风格

**GitHub 风格**

- 列表清晰、操作简洁、信息密度适中
- 采用 GitHub 的配色方案和交互模式

### 页面结构

#### 1. 版本历史列表（已确认）

**入口**：技能详情页 - 版本历史面板

**核心元素**：

| 元素 | 设计 |
|------|------|
| 当前版本标识 | 绿色标签（`当前`），背景高亮 |
| 初始版本标识 | 蓝色标签（`初始`） |
| 版本信息 | 版本号、时间、作者、变更描述 |
| 操作按钮 | 切换、查看详情、比对、删除 |
| 按钮规则 | 当前版本和初始版本无"切换"和"删除"按钮 |

**设计要点**：

- 不需要"快速比对"功能
- 点击每个版本的"比对"按钮后进入专门的比对页面

#### 2. 版本详情页面

**策略**：复用现有技能详情页

- 展示指定版本的文件结构和内容
- 不需要单独设计

#### 3. 版本比对页面（已确认）

**核心元素**：

| 区域 | 设计 |
|------|------|
| 版本选择 | 两个下拉框选择基准版本和目标版本 |
| 变更统计卡片 | 新增行数（绿色）、删除行数（红色）、文件变更数（黄色） |
| 文件列表 | 每个文件显示变更行数统计，可展开差异详情 |
| 差异详情 | 红色背景表示删除行，绿色背景表示新增行 |

**设计要点**：

- 使用 GitHub 风格的 Diff 视图配色
- 支持展开/折叠每个文件的差异详情
- 使用 Monospace 字体展示代码差异

## 实现计划

### 阶段划分

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| 后端服务 | SkillVersionService 实现 | P0 |
| 后端 API | 版本管理 API 端点 | P0 |
| 前端列表页 | 版本历史列表组件 | P0 |
| 前端比对页 | 版本比对页面 | P1 |
| 版本触发 | 同步/上传时自动创建版本 | P0 |

### 关键实现细节

#### 版本快照创建流程

1. 检测技能更新（同步或上传）
2. 从 SKILL.md frontmatter 提取版本号（如 `version: "2.3.0"`）
3. 若无版本号则生成默认版本号（格式：`v时间戳`，如 `v20260603143000`）
4. 计算技能内容 signature
5. 复制技能文件到版本快照目录
6. 更新 versions.json 清单文件
7. 更新当前版本标识

#### 版本切换流程

1. 验证目标版本存在
2. 备份当前版本状态
3. 复制目标版本文件到技能主目录
4. 更新 versions.json 的 is_current 标识
5. 触发 Agent 重载回调（如需要）

#### 版本比对流程

1. 读取两个版本的文件结构
2. 对比文件列表，找出新增/删除/修改的文件
3. 对每个文件进行行级 Diff 计算
4. 生成统计信息和 Diff 详情
5. 返回比对结果

## 技术约束

### 存储空间管理

- 每个技能版本快照占用独立存储空间
- 需提供版本删除功能，支持用户清理旧版本
- 可考虑设置版本数量上限（如最多保留 20 个版本）

### 性能考虑

- 版本列表查询应缓存，避免频繁文件系统扫描
- Diff 计算可能消耗较多 CPU，建议异步处理或限制文件大小
- 版本切换操作应快速，全量快照策略天然支持

### 数据一致性

- versions.json 与版本快照目录需保持强一致性
- 文件操作需使用原子性写入（临时目录 + rename）
- 需处理并发创建版本的情况（文件锁）

## 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 存储空间增长过快 | 占用过多磁盘空间 | 提供版本删除功能，设置版本上限 |
| 大文件 Diff 性能差 | 页面加载缓慢 | 异步计算，限制文件大小，分页展示 |
| 并发版本创建冲突 | 数据不一致 | 使用文件锁，原子性操作 |
| 版本切换后状态丢失 | 用户混淆 | 清晰提示当前版本，记录切换历史 |

## 测试策略

### 单元测试

- SkillVersionService 各方法测试
- 版本快照创建、切换、删除逻辑验证
- Diff 计算准确性验证

### 集成测试

- API 端点测试
- 前后端交互测试
- 并发场景测试

### 用户验收测试

- 版本历史浏览流程
- 版本比对查看流程
- 版本切换/回滚流程
- 版本删除流程

## 后续扩展

### 短期扩展

- 版本标签功能（如 beta、stable）
- 版本备注编辑功能
- 版本比对结果导出

### 长期扩展

- 支持增量存储策略（节省空间）
- 版本分支功能（类似 Git branch）
- 版本合并功能（类似 Git merge）
- 与外部 Git 仓库集成

## 参考资料

- GitHub 版本历史 UI
- GitLab 版本管理设计
- Semantic Versioning 规范
- Unified Diff 格式标准