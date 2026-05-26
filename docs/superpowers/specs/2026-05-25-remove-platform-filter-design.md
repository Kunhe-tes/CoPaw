# 移除运营看板平台筛选器设计文档

## 概述

**目标**：移除运营看板右上角的平台筛选器，source_id 统一从 `X-Source-Id` 请求头获取。

**影响范围**：
- 前端：BusinessOverview 页面、tracing.ts API 模块、monitor.ts API 模块、其他 4 个分析页面
- 后端：tracing.py router、cron.py router
- 测试：相关单元测试和集成测试

**行为变化**：
- 超级管理员：失去"全部平台"选项，只能查看自己所属平台数据
- 非超级管理员：行为不变（已从请求头获取）

---

## 后端修改

### 1. tracing.py Router

**文件**：`monitor/src/monitor/app/routers/tracing.py`

#### 1.1 新增函数

移除现有 `_get_source_id()` 函数，新增 `_get_source_id_from_header()` 函数：

```python
def _get_source_id_from_header(request: Request) -> str:
    """从请求头获取 source_id.

    优先级：
    1. X-Source-Id 请求头
    2. 默认值 "default"

    Args:
        request: FastAPI 请求对象

    Returns:
        数据源标识字符串
    """
    header_source_id = request.headers.get("X-Source-Id")
    if header_source_id:
        return header_source_id
    return "default"
```

#### 1.2 接口修改列表

| 接口 | 当前方式 | 修改后 |
|------|----------|--------|
| `GET /overview` | `source_id or "all"` | 从请求头获取 |
| `GET /users` | `source_id or "all"` | 从请求头获取 |
| `GET /users/{user_id}` | `_get_source_id()` | 从请求头获取 |
| `GET /traces` | `_get_source_id()` | 从请求头获取 |
| `GET /traces/{trace_id}` | 直接使用参数 | 移除参数，从请求头获取 |
| `GET /traces/{trace_id}/timeline` | 直接使用参数 | 移除参数，从请求头获取 |
| `GET /sessions` | `_get_source_id()` | 从请求头获取 |
| `GET /sessions/{session_id}` | `_get_source_id()` | 从请求头获取 |
| `GET /user-messages` | `_get_source_id()` | 从请求头获取 |
| `GET /user-messages/export` | `_get_source_id()` | 从请求头获取 |
| `GET /sources` | 无 source_id | 不变 |
| `GET /channel-distribution` | `source_id or "all"` | 从请求头获取 |
| `GET /growth-stats` | `source_id or "all"` | 从请求头获取 |
| `GET /daily-trend` | `source_id or "all"` | 从请求头获取 |
| `GET /hourly-trend` | `source_id or "all"` | 从请求头获取 |
| `GET /models` | `_get_source_id()` | 从请求头获取 |
| `GET /tools` | `_get_source_id()` | 从请求头获取 |
| `GET /skills` | `source_id or "all"` | 从请求头获取 |
| `GET /skills/{skill_name}/traces` | `source_id or "all"` | 从请求头获取 |
| `GET /mcp/summary` | `source_id or "all"` | 从请求头获取 |
| `GET /mcp` | `source_id or "all"` | 从请求头获取 |
| `GET /task-status/summary` | `source_id or "all"` | 从请求头获取 |
| `GET /depth/summary` | `source_id or "all"` | 从请求头获取 |

#### 1.3 具体修改示例

**修改前**：
```python
@router.get("/overview", response_model=OverviewStats)
async def get_overview(
    request: Request,
    source_id: Optional[str] = Query(
        None,
        description="数据源标识，使用 'all' 查询所有平台",
    ),
    ...
) -> OverviewStats:
    actual_source_id = source_id or "all"
    ...
```

**修改后**：
```python
@router.get("/overview", response_model=OverviewStats)
async def get_overview(
    request: Request,
    ...
) -> OverviewStats:
    actual_source_id = _get_source_id_from_header(request)
    ...
```

---

### 2. cron.py Router

**文件**：`monitor/src/monitor/app/routers/cron.py`

#### 2.1 新增函数

```python
def _get_source_id_from_header(request: Request) -> str:
    """从请求头获取 source_id."""
    header_source_id = request.headers.get("X-Source-Id")
    if header_source_id:
        return header_source_id
    return "default"
```

#### 2.2 接口修改列表

| 接口 | 当前方式 | 修改后 |
|------|----------|--------|
| `GET /jobs` | Query 参数 `source_id` | 从请求头获取 |
| `GET /executions` | Query 参数 `source_id` | 从请求头获取 |
| `GET /export` | Query 参数 `source_id` | 从请求头获取 |
| `GET /filter-options` | 无 source_id | 不变 |
| `GET /jobs/{job_id}` | 无 source_id | 不变 |
| `GET /executions/{execution_id}` | 无 source_id | 不变 |
| `POST /jobs/{job_id}/mark-read` | 无 source_id | 不变 |
| `GET /unread-count` | 无 source_id | 不变 |

---

## 前端修改

### 1. BusinessOverview 页面

**文件**：`console/src/pages/Analytics/BusinessOverview/index.tsx`

#### 1.1 移除内容

| 行号 | 内容 |
|------|------|
| 61-70 | `PLATFORM_NAME_MAP` 常量（平台名称映射） |
| 72-82 | `getPlatformDisplayName()` 函数 |
| 482-498 | `platform` 状态及初始化逻辑 |
| 563-569 | `effectiveSourceId` 计算逻辑 |
| 592-616 | `sources` 获取逻辑（超级管理员获取平台列表） |
| 992-1007 | 平台筛选 Select 组件 UI |

#### 1.2 新增内容

替换 `effectiveSourceId` 计算逻辑：

```typescript
const effectiveSourceId = useMemo(() => {
  const sourceFromContext = getIframeContext().source || DEFAULT_SOURCE_ID;
  return sourceFromContext ? sourceFromContext : "default";
}, []);
```

---

### 2. tracing.ts API 模块

**文件**：`console/src/api/modules/tracing.ts`

#### 2.1 移除函数参数中的 `source_id`

| 函数 | 修改内容 |
|------|----------|
| `getOverview` | 移除 `sourceId` 参数 |
| `getUsers` | 移除 `filters.source_id` |
| `getUserStats` | 移除 `sourceId` 参数 |
| `getTraces` | 移除 `filters.source_id` |
| `getTraceDetail` | 移除 `sourceId` 参数 |
| `getTraceTimeline` | 移除 `sourceId` 参数 |
| `getSessions` | 移除 `filters.source_id` |
| `getSessionStats` | 移除 `sourceId` 参数 |
| `getUserMessages` | 移除 `filters.source_id` |
| `exportUserMessages` | 移除 `filters.source_id` |
| `getChannelDistribution` | 移除 `sourceId` 参数 |
| `getGrowthStats` | 移除 `sourceId` 参数 |
| `getDailyTrend` | 移除 `sourceId` 参数 |
| `getHourlyTrend` | 移除 `sourceId` 参数 |
| `getModels` | 移除 `sourceId` 参数 |
| `getTools` | 移除 `sourceId` 参数 |
| `getSkills` | 移除 `filters.source_id` |
| `getSkillTraces` | 移除 `sourceId` 参数 |
| `getMcpSummary` | 移除 `sourceId` 参数 |
| `getMcpServers` | 移除 `sourceId` 参数 |
| `getTaskStatusSummary` | 移除 `sourceId` 参数 |
| `getDepthSummary` | 移除 `sourceId` 参数 |

---

### 3. monitor.ts API 模块

**文件**：`console/src/api/modules/monitor.ts`

| 函数 | 修改内容 |
|------|----------|
| `exportJobs` | 移除 `filters.source_id` |
| `exportExecutions` | 移除 `filters.source_id` |

---

### 4. 其他分析页面

| 文件 | 修改内容 |
|------|----------|
| `Users/index.tsx` | 移除 `effectiveSourceId` 变量，移除 API 调用中的 `source_id` |
| `Sessions/index.tsx` | 移除 `effectiveSourceId` 变量，移除 API 调用中的 `source_id` |
| `Messages/index.tsx` | 移除 `effectiveSourceId` 变量，移除 API 调用和导出中的 `source_id` |
| `Traces/index.tsx` | 移除 `effectiveSourceId` 变量，移除 API 调用中的 `source_id` |

---

## 测试修改

| 文件 | 修改内容 |
|------|----------|
| `monitor/tests/test_query_api.py` | 移除 source_id 查询参数，改用 X-Source-Id 请求头 |
| `monitor/tests/test_export_integration.py` | 移除 source_id 查询参数，改用 X-Source-Id 请求头 |
| `monitor/tests/test_export_service.py` | 移除 source_id 查询参数，改用 X-Source-Id 请求头 |
| `console/src/pages/Analytics/BusinessOverview/index.test.tsx` | 移除平台筛选相关测试用例 |

---

## 风险评估

1. **向后兼容性**：移除 source_id 查询参数后，旧版本前端将无法正常工作。需要确保前后端同步发布。

2. **测试覆盖**：需要更新所有相关测试用例，确保测试通过后再发布。

3. **超级管理员功能变化**：失去跨平台查询能力，需提前通知相关用户。
