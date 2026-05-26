# 移除运营看板平台筛选器实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除运营看板右上角的平台筛选器，source_id 统一从 X-Source-Id 请求头获取。

**Architecture:** 后端新增统一函数从请求头获取 source_id，前端移除 source_id 查询参数依赖请求头自动传递，移除平台筛选 UI 组件。

**Tech Stack:** Python/FastAPI (后端), TypeScript/React (前端)

---

## 文件结构

### 后端修改文件

| 文件 | 职责 |
|------|------|
| `monitor/src/monitor/app/routers/tracing.py` | 移除 source_id Query 参数，新增 `_get_source_id_from_header()` |
| `monitor/src/monitor/app/routers/cron.py` | 移除 source_id Query 参数，新增 `_get_source_id_from_header()` |
| `monitor/tests/test_query_api.py` | 更新测试使用 X-Source-Id 请求头 |
| `monitor/tests/test_export_integration.py` | 更新测试使用 X-Source-Id 请求头 |
| `monitor/tests/test_export_service.py` | 更新测试使用 X-Source-Id 请求头 |

### 前端修改文件

| 文件 | 职责 |
|------|------|
| `console/src/pages/Analytics/BusinessOverview/index.tsx` | 移除平台筛选 UI 和相关状态 |
| `console/src/pages/Analytics/Users/index.tsx` | 移除 source_id 查询参数 |
| `console/src/pages/Analytics/Sessions/index.tsx` | 移除 source_id 查询参数 |
| `console/src/pages/Analytics/Messages/index.tsx` | 移除 source_id 查询参数 |
| `console/src/pages/Analytics/Traces/index.tsx` | 移除 source_id 查询参数 |
| `console/src/api/modules/tracing.ts` | 移除所有函数的 source_id 参数 |
| `console/src/api/modules/monitor.ts` | 移除导出函数的 source_id 参数 |

---

## Task 1: 后端 tracing.py - 新增辅助函数并修改 overview 接口

**Files:**
- Modify: `monitor/src/monitor/app/routers/tracing.py`

- [ ] **Step 1: 替换 `_get_source_id()` 函数为 `_get_source_id_from_header()`**

找到第 42-68 行的 `_get_source_id()` 函数，替换为：

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

- [ ] **Step 2: 修改 `get_overview` 接口**

找到第 195-235 行的 `get_overview` 函数，修改为：

```python
@router.get("/overview", response_model=OverviewStats)
async def get_overview(
    request: Request,
    bbk_ids: Optional[str] = Query(
        None,
        description="分行ID筛选",
    ),
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
) -> OverviewStats:
    """获取运营概览统计.

    Args:
        bbk_ids: 分行ID筛选
        start_date: 可选的开始日期筛选
        end_date: 可选的结束日期筛选

    Returns:
        运营概览统计，包括用户数、Token 使用量、模型分布等
    """
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    return await service.get_overview_stats(
        actual_source_id,
        start,
        end,
        bbk_ids,
    )
```

- [ ] **Step 3: 提交后端第一步修改**

```bash
cd monitor && git add src/monitor/app/routers/tracing.py
git commit -m "refactor(tracing): replace _get_source_id with _get_source_id_from_header, update overview endpoint

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: 后端 tracing.py - 修改 users 相关接口

**Files:**
- Modify: `monitor/src/monitor/app/routers/tracing.py`

- [ ] **Step 1: 修改 `get_users` 接口**

找到第 241-306 行的 `get_users` 函数，移除 `source_id` 参数，修改 effective_source_id 计算：

```python
@router.get("/users", response_model=dict)
async def get_users(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user_id: Optional[str] = Query(
        None,
        description="按用户 ID 筛选（模糊匹配）",
    ),
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    sort_by: Optional[str] = Query(
        None,
        description="排序字段: conversations, last_active",
    ),
    filter_user_type: Optional[str] = Query(
        "filtered",
        description="用户过滤类型: filtered(过滤80/IT开头用户), all(仅过滤default用户)",
    ),
    bbk_ids: Optional[str] = Query(None, description="按分行号筛选"),
) -> dict:
    """获取用户列表及其统计信息.

    Args:
        page: 页码
        page_size: 每页数量
        user_id: 按用户 ID 筛选
        start_date: 开始日期筛选
        end_date: 结束日期筛选
        sort_by: 排序字段（conversations, last_active）
        filter_user_type: 用户过滤类型（filtered/all）
        bbk_ids: 分行号筛选

    Returns:
        分页的用户列表及统计信息
    """
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    users, total = await service.get_users(
        actual_source_id,
        page,
        page_size,
        user_id,
        start,
        end,
        sort_by,
        filter_user_type,
        bbk_ids,
    )
    return {
        "items": [u.model_dump() for u in users],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
```

- [ ] **Step 2: 修改 `get_user_stats` 接口**

找到第 309-348 行的 `get_user_stats` 函数，移除 `source_id` 参数：

```python
@router.get("/users/{user_id}", response_model=UserStats)
async def get_user_stats(
    user_id: str,
    request: Request,
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    bbk_ids: Optional[str] = Query(
        None,
        description="分行ID筛选",
    ),
) -> UserStats:
    """获取指定用户的统计详情.

    Args:
        user_id: 用户标识
        start_date: 可选的开始日期筛选
        end_date: 可选的结束日期筛选
        bbk_ids: 分行ID筛选

    Returns:
        用户统计信息
    """
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    return await service.get_user_stats(
        actual_source_id,
        user_id,
        start,
        end,
        bbk_ids,
    )
```

- [ ] **Step 3: 提交**

```bash
cd monitor && git add src/monitor/app/routers/tracing.py
git commit -m "refactor(tracing): remove source_id query param from users endpoints

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: 后端 tracing.py - 修改 traces 相关接口

**Files:**
- Modify: `monitor/src/monitor/app/routers/tracing.py`

- [ ] **Step 1: 修改 `get_traces` 接口**

找到第 369-425 行的 `get_traces` 函数，移除 `source_id` 参数：

```python
@router.get("/traces", response_model=dict)
async def get_traces(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user_id: Optional[str] = Query(None, description="按用户 ID 筛选"),
    session_id: Optional[str] = Query(
        None,
        description="按会话 ID 筛选",
    ),
    status: Optional[str] = Query(None, description="按状态筛选"),
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    bbk_ids: Optional[str] = Query(None, description="按分行号筛选"),
) -> dict:
    """获取对话列表.

    Args:
        page: 页码
        page_size: 每页数量
        user_id: 按用户 ID 筛选
        session_id: 按会话 ID 筛选
        status: 按状态筛选（running, completed, error, cancelled）
        start_date: 开始日期筛选
        end_date: 结束日期筛选
        bbk_ids: 分行号筛选

    Returns:
        分页的对话列表
    """
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    traces, total = await service.get_traces(
        source_id=actual_source_id,
        page=page,
        page_size=page_size,
        user_id=user_id,
        session_id=session_id,
        status=status,
        start_date=start,
        end_date=end,
        bbk_ids=bbk_ids,
    )
    return {
        "items": [t.model_dump() for t in traces],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
```

- [ ] **Step 2: 修改 `get_trace_detail` 接口**

找到第 428-455 行的 `get_trace_detail` 函数，移除 `source_id` 参数：

```python
@router.get("/traces/{trace_id}", response_model=TraceDetail)
async def get_trace_detail(
    trace_id: str,
    request: Request,
) -> TraceDetail:
    """获取对话详情（包含 Span）.

    Args:
        trace_id: 对话标识

    Returns:
        对话详情及所有 Span

    Raises:
        HTTPException: 对话未找到时抛出
    """
    service = TracingQueryService.get_instance()

    detail = await service.get_trace_detail(trace_id, None)
    if detail is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    return detail
```

- [ ] **Step 3: 修改 `get_trace_timeline` 接口**

找到第 458-492 行的 `get_trace_timeline` 函数，移除 `source_id` 参数：

```python
@router.get(
    "/traces/{trace_id}/timeline",
    response_model=TraceDetailWithTimeline,
)
async def get_trace_timeline(
    trace_id: str,
    request: Request,
) -> TraceDetailWithTimeline:
    """获取对话详情（带时间线）.

    返回分层时间线，其中技能调用是父节点，包含其工具调用作为子节点。

    Args:
        trace_id: 对话标识

    Returns:
        对话详情及分层时间线

    Raises:
        HTTPException: 对话未找到时抛出
    """
    service = TracingQueryService.get_instance()

    detail = await service.get_trace_detail_with_timeline(
        trace_id,
        None,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    return detail
```

- [ ] **Step 4: 提交**

```bash
cd monitor && git add src/monitor/app/routers/tracing.py
git commit -m "refactor(tracing): remove source_id query param from traces endpoints

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: 后端 tracing.py - 修改 sessions 相关接口

**Files:**
- Modify: `monitor/src/monitor/app/routers/tracing.py`

- [ ] **Step 1: 修改 `get_sessions` 接口**

找到第 498-551 行的 `get_sessions` 函数，移除 `source_id` 参数：

```python
@router.get("/sessions", response_model=dict)
async def get_sessions(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user_id: Optional[str] = Query(None, description="按用户 ID 筛选"),
    session_id: Optional[str] = Query(
        None,
        description="按会话 ID 筛选（模糊匹配）",
    ),
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    bbk_ids: Optional[str] = Query(None, description="按分行号筛选"),
) -> dict:
    """获取会话列表及其统计信息.

    Args:
        page: 页码
        page_size: 每页数量
        user_id: 按用户 ID 筛选
        session_id: 按会话 ID 筛选（模糊匹配）
        start_date: 开始日期筛选
        end_date: 结束日期筛选
        bbk_ids: 分行号筛选

    Returns:
        分页的会话列表及统计信息
    """
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    sessions, total = await service.get_sessions(
        source_id=actual_source_id,
        page=page,
        page_size=page_size,
        user_id=user_id,
        session_id=session_id,
        start_date=start,
        end_date=end,
        bbk_ids=bbk_ids,
    )
    return {
        "items": [s.model_dump() for s in sessions],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
```

- [ ] **Step 2: 修改 `get_session_stats` 接口**

找到第 554-592 行的 `get_session_stats` 函数，移除 `source_id` 参数：

```python
@router.get("/sessions/{session_id:path}", response_model=SessionStats)
async def get_session_stats(
    session_id: str,
    request: Request,
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    bbk_ids: Optional[str] = Query(
        None,
        description="分行标识，多个用逗号分隔",
    ),
) -> SessionStats:
    """获取指定会话的统计详情.

    Args:
        session_id: 会话标识
        start_date: 可选的开始日期筛选
        end_date: 可选的结束日期筛选
        bbk_ids: 分行标识筛选

    Returns:
        会话统计信息
    """
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    return await service.get_session_stats(
        actual_source_id,
        session_id,
        start,
        end,
        bbk_ids,
    )
```

- [ ] **Step 3: 提交**

```bash
cd monitor && git add src/monitor/app/routers/tracing.py
git commit -m "refactor(tracing): remove source_id query param from sessions endpoints

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: 后端 tracing.py - 修改 user-messages 相关接口

**Files:**
- Modify: `monitor/src/monitor/app/routers/tracing.py`

- [ ] **Step 1: 修改 `get_user_messages` 接口**

找到第 598-660 行的 `get_user_messages` 函数，移除 `source_id` 参数：

```python
@router.get("/user-messages", response_model=dict)
async def get_user_messages(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user_id: Optional[str] = Query(None, description="按用户 ID 筛选"),
    session_id: Optional[str] = Query(
        None,
        description="按会话 ID 筛选",
    ),
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    query: Optional[str] = Query(
        None,
        description="搜索用户消息内容",
    ),
    bbk_ids: Optional[str] = Query(None, description="按分行号筛选"),
) -> dict:
    """获取用户消息列表（含 Token 信息）.

    用于成本分析和消息内容查询。

    Args:
        page: 页码
        page_size: 每页数量
        user_id: 按用户 ID 筛选
        session_id: 按会话 ID 筛选
        start_date: 开始日期筛选
        end_date: 结束日期筛选
        query: 搜索用户消息内容（模糊匹配）
        bbk_ids: 分行号筛选

    Returns:
        分页的用户消息列表及 Token 使用量
    """
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    messages, total = await service.get_user_messages(
        source_id=actual_source_id,
        page=page,
        page_size=page_size,
        user_id=user_id,
        session_id=session_id,
        start_date=start,
        end_date=end,
        query_text=query,
        export=False,
        bbk_ids=bbk_ids,
    )
    return {
        "items": [m.model_dump() for m in messages],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
```

- [ ] **Step 2: 修改 `export_user_messages` 接口**

找到第 663-736 行的 `export_user_messages` 函数，移除 `source_id` 参数：

```python
@router.get("/user-messages/export")
async def export_user_messages(
    request: Request,
    user_id: Optional[str] = Query(None, description="按用户 ID 筛选"),
    session_id: Optional[str] = Query(
        None,
        description="按会话 ID 筛选",
    ),
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    query: Optional[str] = Query(
        None,
        description="搜索用户消息内容",
    ),
    export_format: str = Query(
        "csv",
        description="导出格式: csv, json 或 xlsx",
        alias="format",
    ),
    bbk_ids: Optional[str] = Query(None, description="按分行号筛选"),
) -> StreamingResponse:
    """导出用户消息.

    Args:
        user_id: 按用户 ID 筛选
        session_id: 按会话 ID 筛选
        start_date: 开始日期筛选
        end_date: 结束日期筛选
        query: 搜索用户消息内容（模糊匹配）
        export_format: 导出格式（csv, json 或 xlsx）
        bbk_ids: 分行号筛选

    Returns:
        StreamingResponse 包含导出文件
    """
    actual_source_id = _get_source_id_from_header(request)
    export_service = TracingExportService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    if export_format == "json":
        return await export_service.export_user_messages_json(
            source_id=actual_source_id,
            user_id=user_id,
            session_id=session_id,
            start_date=start,
            end_date=end,
            query_text=query,
            bbk_id=bbk_ids,
        )
    if export_format == "xlsx":
        return await export_service.export_user_messages_xlsx(
            source_id=actual_source_id,
            user_id=user_id,
            session_id=session_id,
            start_date=start,
            end_date=end,
            query_text=query,
            bbk_id=bbk_ids,
        )
    return await export_service.export_user_messages_csv(
        source_id=actual_source_id,
        user_id=user_id,
        session_id=session_id,
        start_date=start,
        end_date=end,
        query_text=query,
        bbk_id=bbk_ids,
    )
```

- [ ] **Step 3: 提交**

```bash
cd monitor && git add src/monitor/app/routers/tracing.py
git commit -m "refactor(tracing): remove source_id query param from user-messages endpoints

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: 后端 tracing.py - 修改其他统计接口

**Files:**
- Modify: `monitor/src/monitor/app/routers/tracing.py`

- [ ] **Step 1: 修改 `get_channel_distribution` 接口**

找到第 772-801 行的 `get_channel_distribution` 函数，移除 `source_id` 参数：

```python
@router.get("/channel-distribution", response_model=dict)
async def get_channel_distribution(
    request: Request,
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
) -> dict:
    """获取渠道分布统计.

    Args:
        start_date: 开始日期筛选
        end_date: 结束日期筛选

    Returns:
        渠道分布：platformUserDistribution, platformCallDistribution, totalPlatforms
    """
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    return await service.get_channel_distribution(actual_source_id, start, end)
```

- [ ] **Step 2: 修改 `get_growth_stats` 接口**

找到第 807-850 行的 `get_growth_stats` 函数，移除 `source_id` 参数：

```python
@router.get("/growth-stats", response_model=dict)
async def get_growth_stats(
    request: Request,
    start_date: str = Query(..., description="开始日期 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="结束日期 (YYYY-MM-DD)"),
    time_range: str = Query(
        "day",
        description="时间范围: day, week, month, custom",
    ),
    bbk_ids: Optional[str] = Query(None, description="分行ID筛选"),
) -> dict:
    """获取运营看板环比指标。

    口径说明：
    - 该接口返回的是"当前统计窗口"相对"上一对比窗口"的环比结果。
    - 分行维度通过 `bbk_ids` 过滤。
    - `time_range` 只决定上一对比窗口的回溯长度，不改变当前窗口
      的起止日期输入。
    - 返回字段的业务口径由服务层统一定义，供总览卡片和使用深度卡片
      复用，避免前端自行推导环比口径。
    """
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)
    if start is None or end is None:
        raise HTTPException(
            status_code=400,
            detail="start_date and end_date are required",
        )

    return await service.get_growth_stats(
        actual_source_id,
        start,
        end,
        time_range,
        bbk_ids,
    )
```

- [ ] **Step 3: 修改 `get_daily_trend` 接口**

找到第 856-883 行的 `get_daily_trend` 函数，移除 `source_id` 参数：

```python
@router.get("/daily-trend", response_model=dict)
async def get_daily_trend(
    request: Request,
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    bbk_ids: Optional[str] = Query(None, description="分行ID筛选"),
) -> dict:
    """获取日趋势数据."""
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    trend = await service.get_daily_trend(
        actual_source_id,
        start,
        end,
        bbk_ids,
    )
    return {"trendData": trend}
```

- [ ] **Step 4: 修改 `get_hourly_trend` 接口**

找到第 886-916 行的 `get_hourly_trend` 函数，移除 `source_id` 参数：

```python
@router.get("/hourly-trend", response_model=dict)
async def get_hourly_trend(
    request: Request,
    start_date: Optional[str] = Query(
        None,
        description="Start date (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(
        None,
        description="End date (YYYY-MM-DD)",
    ),
    bbk_ids: Optional[str] = Query(None, description="分行ID筛选"),
) -> dict:
    """Get hourly trend data for single-day charts."""
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    trend = await service.get_hourly_trend(
        actual_source_id,
        start,
        end,
        bbk_ids,
    )
    return {"trendData": trend}
```

- [ ] **Step 5: 提交**

```bash
cd monitor && git add src/monitor/app/routers/tracing.py
git commit -m "refactor(tracing): remove source_id query param from channel-distribution, growth-stats, trend endpoints

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: 后端 tracing.py - 修改 models/tools/skills/mcp 等接口

**Files:**
- Modify: `monitor/src/monitor/app/routers/tracing.py`

- [ ] **Step 1: 修改 `get_model_usage` 接口**

找到第 922-949 行的 `get_model_usage` 函数，移除 `source_id` 参数：

```python
@router.get("/models", response_model=dict)
async def get_model_usage(
    request: Request,
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
) -> dict:
    """获取模型使用统计.

    Args:
        start_date: 开始日期筛选
        end_date: 结束日期筛选

    Returns:
        模型使用统计
    """
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    stats = await service.get_overview_stats(actual_source_id, start, end)
    return {"models": [m.model_dump() for m in stats.model_distribution]}
```

- [ ] **Step 2: 修改 `get_tool_usage` 接口**

找到第 955-982 行的 `get_tool_usage` 函数，移除 `source_id` 参数：

```python
@router.get("/tools", response_model=dict)
async def get_tool_usage(
    request: Request,
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
) -> dict:
    """获取工具使用统计.

    Args:
        start_date: 开始日期筛选
        end_date: 结束日期筛选

    Returns:
        工具使用统计
    """
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    stats = await service.get_overview_stats(actual_source_id, start, end)
    return {"tools": [t.model_dump() for t in stats.top_tools]}
```

- [ ] **Step 3: 修改 `get_skill_usage` 接口**

找到第 988-1024 行的 `get_skill_usage` 函数，移除 `source_id` 参数：

```python
@router.get("/skills", response_model=dict)
async def get_skill_usage(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    bbk_ids: Optional[str] = Query(None, description="分行ID筛选"),
) -> dict:
    """获取技能调用排行榜（分页）."""
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    skills, total = await service.get_skills_paginated(
        actual_source_id,
        page,
        page_size,
        start,
        end,
        bbk_ids,
    )
    return {
        "items": [s.model_dump() for s in skills],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
```

- [ ] **Step 4: 修改 `get_skill_traces` 接口**

找到第 1027-1075 行的 `get_skill_traces` 函数，移除 `source_id` 参数：

```python
@router.get("/skills/{skill_name}/traces", response_model=dict)
async def get_skill_traces(
    skill_name: str,
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
) -> dict:
    """获取指定技能调用的对话列表（分页）.

    Args:
        skill_name: 技能名称
        page: 页码
        page_size: 每页数量
        start_date: 开始日期筛选
        end_date: 结束日期筛选

    Returns:
        分页的对话列表
    """
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    traces, total = await service.get_skill_traces(
        skill_name,
        actual_source_id,
        page,
        page_size,
        start,
        end,
    )
    return {
        "items": [t.model_dump() for t in traces],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
```

- [ ] **Step 5: 提交**

```bash
cd monitor && git add src/monitor/app/routers/tracing.py
git commit -m "refactor(tracing): remove source_id query param from models, tools, skills endpoints

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: 后端 tracing.py - 修改 mcp/task-status/depth 接口

**Files:**
- Modify: `monitor/src/monitor/app/routers/tracing.py`

- [ ] **Step 1: 修改 `get_mcp_summary` 接口**

找到第 1081-1108 行的 `get_mcp_summary` 函数，移除 `source_id` 参数：

```python
@router.get("/mcp/summary", response_model=MCPSummary)
async def get_mcp_summary(
    request: Request,
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    bbk_ids: Optional[str] = Query(None, description="分行ID筛选"),
) -> MCPSummary:
    """获取 MCP 全局调用汇总统计."""
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    summary = await service.get_mcp_summary(
        actual_source_id,
        start,
        end,
        bbk_ids,
    )
    return summary
```

- [ ] **Step 2: 修改 `get_mcp_usage` 接口**

找到第 1111-1147 行的 `get_mcp_usage` 函数，移除 `source_id` 参数：

```python
@router.get("/mcp", response_model=dict)
async def get_mcp_usage(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    bbk_ids: Optional[str] = Query(None, description="分行ID筛选"),
) -> dict:
    """获取 MCP 服务调用排行榜（分页）."""
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    servers, total = await service.get_mcp_servers_paginated(
        actual_source_id,
        page,
        page_size,
        start,
        end,
        bbk_ids,
    )
    return {
        "items": [s.model_dump() for s in servers],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
```

- [ ] **Step 3: 修改 `get_task_status_summary` 接口**

找到第 1153-1180 行的 `get_task_status_summary` 函数，移除 `source_id` 参数：

```python
@router.get("/task-status/summary", response_model=TaskStatusSummary)
async def get_task_status_summary(
    request: Request,
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    bbk_ids: Optional[str] = Query(None, description="分行ID筛选"),
) -> TaskStatusSummary:
    """获取定时任务执行汇总统计."""
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    summary = await service.get_task_status_summary(
        actual_source_id,
        start,
        end,
        bbk_ids,
    )
    return summary
```

- [ ] **Step 4: 修改 `get_depth_summary` 接口**

找到第 1186-1213 行的 `get_depth_summary` 函数，移除 `source_id` 参数：

```python
@router.get("/depth/summary", response_model=DepthSummary)
async def get_depth_summary(
    request: Request,
    start_date: Optional[str] = Query(
        None,
        description="开始日期 (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    bbk_ids: Optional[str] = Query(None, description="分行ID筛选"),
) -> DepthSummary:
    """获取使用深度汇总统计."""
    actual_source_id = _get_source_id_from_header(request)
    service = TracingQueryService.get_instance()

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date", add_day=True)

    summary = await service.get_depth_summary(
        actual_source_id,
        start,
        end,
        bbk_ids,
    )
    return summary
```

- [ ] **Step 5: 提交**

```bash
cd monitor && git add src/monitor/app/routers/tracing.py
git commit -m "refactor(tracing): remove source_id query param from mcp, task-status, depth endpoints

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: 后端 cron.py - 新增辅助函数并修改接口

**Files:**
- Modify: `monitor/src/monitor/app/routers/cron.py`

- [ ] **Step 1: 新增 `_get_source_id_from_header()` 函数**

在文件顶部（import 语句后）添加：

```python
def _get_source_id_from_header(request: Request) -> str:
    """从请求头获取 source_id."""
    header_source_id = request.headers.get("X-Source-Id")
    if header_source_id:
        return header_source_id
    return "default"
```

需要添加 `from fastapi import Request` 导入（如果尚未导入）。

- [ ] **Step 2: 修改 `list_jobs` 接口**

找到第 51-92 行的 `list_jobs` 函数，移除 `source_id` 参数：

```python
@router.get("/jobs", response_model=PaginatedResponse[CronJobModel])
async def list_jobs(
    request: Request,
    tenant_id: str | None = Query(default=None, description="租户ID筛选"),
    bbk_id: str | None = Query(default=None, description="分行号筛选"),
    creator_user_id: str | None = Query(
        default=None,
        description="创建者ID筛选",
    ),
    status: str | None = Query(default=None, description="状态筛选"),
    enabled: bool | None = Query(default=None, description="是否启用筛选"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=10, ge=1, le=100, description="每页数量"),
    service: QueryService = Depends(get_query_service),
) -> PaginatedResponse[CronJobModel]:
    """List cron jobs with pagination and filters.

    Args:
        tenant_id: Tenant ID filter
        bbk_id: BBK ID filter (分行号)
        creator_user_id: Creator user ID filter
        status: Status filter
        enabled: Enabled filter
        page: Page number
        page_size: Page size
        service: Query service

    Returns:
        Paginated job list
    """
    actual_source_id = _get_source_id_from_header(request)
    params = CronJobQueryParams(
        tenant_id=tenant_id,
        bbk_id=bbk_id,
        source_id=actual_source_id,
        creator_user_id=creator_user_id,
        status=status,
        enabled=enabled,
        page=page,
        page_size=page_size,
    )
    return await service.list_jobs(params)
```

- [ ] **Step 3: 修改 `list_executions` 接口**

找到第 118-162 行的 `list_executions` 函数，移除 `source_id` 参数：

```python
@router.get("/executions", response_model=PaginatedResponse[ExecutionModel])
async def list_executions(
    request: Request,
    job_id: str | None = Query(default=None, description="任务ID筛选"),
    tenant_id: str | None = Query(default=None, description="租户ID筛选"),
    status: str | None = Query(default=None, description="执行状态筛选"),
    start_time: datetime | None = Query(
        default=None,
        description="开始时间范围",
    ),
    end_time: datetime | None = Query(
        default=None,
        description="结束时间范围",
    ),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=10, ge=1, le=100, description="每页数量"),
    service: QueryService = Depends(get_query_service),
) -> PaginatedResponse[ExecutionModel]:
    """List execution history with pagination and filters.

    Args:
        job_id: Job ID filter
        tenant_id: Tenant ID filter
        status: Status filter
        start_time: Start time filter
        end_time: End time filter
        page: Page number
        page_size: Page size
        service: Query service

    Returns:
        Paginated execution list
    """
    actual_source_id = _get_source_id_from_header(request)
    params = ExecutionQueryParams(
        job_id=job_id,
        tenant_id=tenant_id,
        source_id=actual_source_id,
        status=status,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )
    return await service.list_executions(params)
```

- [ ] **Step 4: 修改 `export_data` 接口**

找到第 191-266 行的 `export_data` 函数，移除 `source_id` 参数：

```python
@router.get("/export")
async def export_data(
    request: Request,
    job_id: str | None = Query(default=None, description="任务ID筛选"),
    tenant_id: str | None = Query(default=None, description="租户ID筛选"),
    bbk_id: str | None = Query(default=None, description="分行号筛选"),
    enabled: bool | None = Query(default=None, description="是否启用筛选"),
    status: str | None = Query(default=None, description="状态筛选"),
    start_time: datetime | None = Query(
        default=None,
        description="开始时间范围",
    ),
    end_time: datetime | None = Query(
        default=None,
        description="结束时间范围",
    ),
    export_type: str = Query(
        default="executions",
        description="导出类型: jobs/executions",
    ),
    query_service: QueryService = Depends(get_query_service),
    export_service: ExportService = Depends(get_export_service),
) -> StreamingResponse:
    """Export cron data to Excel.

    Args:
        job_id: Job ID filter (for executions)
        tenant_id: Tenant ID filter
        bbk_id: BBK ID filter (分行号)
        enabled: Enabled filter (是否启用)
        status: Status filter
        start_time: Start time filter (for executions)
        end_time: End time filter (for executions)
        export_type: Export type (jobs or executions)
        query_service: Query service
        export_service: Export service

    Returns:
        Excel file download
    """
    actual_source_id = _get_source_id_from_header(request)
    try:
        if export_type == "jobs":
            jobs = await query_service.get_jobs_for_export(
                tenant_id=tenant_id,
                bbk_id=bbk_id,
                source_id=actual_source_id,
                enabled=enabled,
                status=status,
            )
            excel_bytes = export_service.export_jobs(jobs)
            filename = "定时任务.xlsx"
        else:
            executions = await query_service.get_executions_for_export(
                job_id=job_id,
                tenant_id=tenant_id,
                source_id=actual_source_id,
                status=status,
                start_time=start_time,
                end_time=end_time,
            )
            excel_bytes = export_service.export_executions(executions)
            filename = "定时任务执行情况.xlsx"

        # RFC 5987: 使用filename*参数支持中文文件名
        encoded_filename = quote(filename)
        return StreamingResponse(
            BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            },
        )
    except Exception as e:
        logger.error("Failed to export data: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 5: 提交**

```bash
cd monitor && git add src/monitor/app/routers/cron.py
git commit -m "refactor(cron): remove source_id query param, use X-Source-Id header instead

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 10: 后端测试更新

**Files:**
- Modify: `monitor/tests/test_query_api.py`
- Modify: `monitor/tests/test_export_integration.py`
- Modify: `monitor/tests/test_export_service.py`

- [ ] **Step 1: 更新 test_query_api.py**

将测试中的 `source_id` 查询参数改为 `X-Source-Id` 请求头。

示例修改：
```python
# 修改前
response = client.get("/monitor/tracing/overview?source_id=CMSJY")

# 修改后
response = client.get(
    "/monitor/tracing/overview",
    headers={"X-Source-Id": "CMSJY"}
)
```

对所有涉及 `source_id` 的测试用例进行相同修改。

- [ ] **Step 2: 更新 test_export_integration.py**

同样将 `source_id` 查询参数改为请求头。

- [ ] **Step 3: 更新 test_export_service.py**

同样将 `source_id` 查询参数改为请求头。

- [ ] **Step 4: 运行测试验证**

```bash
cd monitor && venv/Scripts/python -m pytest tests/ -v
```

Expected: 所有测试通过

- [ ] **Step 5: 提交**

```bash
cd monitor && git add tests/
git commit -m "test: update tests to use X-Source-Id header instead of query param

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 11: 前端 tracing.ts API 模块修改

**Files:**
- Modify: `console/src/api/modules/tracing.ts`

- [ ] **Step 1: 修改 `getOverview` 函数**

找到第 321-333 行，移除 `sourceId` 参数：

```typescript
getOverview: async (
  startDate?: string,
  endDate?: string,
  bbkIds?: string,
): Promise<OverviewStats> => {
  const params = new URLSearchParams();
  if (startDate) params.append("start_date", startDate);
  if (endDate) params.append("end_date", endDate);
  if (bbkIds) params.append("bbk_ids", bbkIds);
  return request(`/monitor/tracing/overview?${params.toString()}`);
},
```

- [ ] **Step 2: 修改 `getUsers` 函数**

找到第 336-369 行，移除 `filters.source_id`：

```typescript
getUsers: async (
  page = 1,
  pageSize = 20,
  filters?: {
    user_id?: string;
    bbk_ids?: string;
    start_date?: string;
    end_date?: string;
    filter_user_type?: string;
  },
) => {
  const params = new URLSearchParams();
  params.append("page", page.toString());
  params.append("page_size", pageSize.toString());
  if (filters) {
    Object.entries(filters).forEach(([key, value]) => {
      if (key === "filter_user_type") {
        if (value) params.append(key, value);
      } else if (value) {
        params.append(key, value);
      }
    });
  }
  return request(`/monitor/tracing/users?${params.toString()}`);
},
```

- [ ] **Step 3: 修改 `getUserStats` 函数**

找到第 372-398 行，移除 `sourceId` 参数：

```typescript
getUserStats: async (
  userId: string,
  startDate?: string,
  endDate?: string,
  bbkIds?: string,
): Promise<UserStats> => {
  const params = new URLSearchParams();
  if (startDate) params.append("start_date", startDate);
  if (endDate) params.append("end_date", endDate);
  if (bbkIds) params.append("bbk_ids", bbkIds);
  return request(`/monitor/tracing/users/${userId}?${params.toString()}`);
},
```

- [ ] **Step 4: 修改 `getTraces` 函数**

找到第 400-427 行，移除 `filters.source_id`：

```typescript
getTraces: async (
  page = 1,
  pageSize = 20,
  filters?: {
    user_id?: string;
    session_id?: string;
    status?: string;
    start_date?: string;
    end_date?: string;
    bbk_ids?: string;
  },
) => {
  const params = new URLSearchParams();
  params.append("page", page.toString());
  params.append("page_size", pageSize.toString());
  if (filters) {
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.append(key, value);
    });
  }
  return request(`/monitor/tracing/traces?${params.toString()}`);
},
```

- [ ] **Step 5: 修改 `getTraceDetail` 和 `getTraceTimeline` 函数**

找到第 430-458 行和第 460-489 行，移除 `sourceId` 参数：

```typescript
getTraceDetail: async (traceId: string): Promise<TraceDetail> => {
  return request(`/monitor/tracing/traces/${traceId}`);
},

getTraceTimeline: async (traceId: string): Promise<TraceDetailWithTimeline> => {
  return request(`/monitor/tracing/traces/${traceId}/timeline`);
},
```

- [ ] **Step 6: 提交**

```bash
cd console && git add src/api/modules/tracing.ts
git commit -m "refactor(api): remove source_id query param from tracing API calls

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 12: 前端 tracing.ts 其他函数修改

**Files:**
- Modify: `console/src/api/modules/tracing.ts`

- [ ] **Step 1: 修改 `getSessions` 函数**

移除 `filters.source_id`。

- [ ] **Step 2: 修改 `getSessionStats` 函数**

移除 `sourceId` 参数。

- [ ] **Step 3: 修改 `getUserMessages` 函数**

移除 `filters.source_id`。

- [ ] **Step 4: 修改 `exportUserMessages` 函数**

移除 `filters.source_id`。

- [ ] **Step 5: 修改 `getChannelDistribution` 函数**

移除 `sourceId` 参数。

- [ ] **Step 6: 修改 `getGrowthStats`、`getDailyTrend`、`getHourlyTrend` 函数**

移除 `sourceId` 参数。

- [ ] **Step 7: 修改 `getModels`、`getTools` 函数**

移除 `sourceId` 参数。

- [ ] **Step 8: 修改 `getSkills`、`getSkillTraces` 函数**

移除 `source_id` 参数。

- [ ] **Step 9: 修改 `getMcpSummary`、`getMcpServers` 函数**

移除 `sourceId` 参数。

- [ ] **Step 10: 修改 `getTaskStatusSummary`、`getDepthSummary` 函数**

移除 `sourceId` 参数。

- [ ] **Step 11: 提交**

```bash
cd console && git add src/api/modules/tracing.ts
git commit -m "refactor(api): remove source_id from remaining tracing API functions

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 13: 前端 monitor.ts API 模块修改

**Files:**
- Modify: `console/src/api/modules/monitor.ts`

- [ ] **Step 1: 修改 `exportJobs` 函数**

移除 `filters.source_id`。

- [ ] **Step 2: 修改 `exportExecutions` 函数**

移除 `filters.source_id`。

- [ ] **Step 3: 提交**

```bash
cd console && git add src/api/modules/monitor.ts
git commit -m "refactor(api): remove source_id from monitor export functions

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 14: 前端 BusinessOverview 页面修改

**Files:**
- Modify: `console/src/pages/Analytics/BusinessOverview/index.tsx`

- [ ] **Step 1: 移除 `PLATFORM_NAME_MAP` 常量**

找到第 61-70 行，删除整个常量定义。

- [ ] **Step 2: 移除 `getPlatformDisplayName` 函数**

找到第 72-82 行，删除整个函数。

- [ ] **Step 3: 移除 `platform` 状态及初始化逻辑**

找到第 482-498 行，删除：
```typescript
const [platform, setPlatform] = useState<string>(() => {
  try {
    const stored = sessionStorage.getItem("swe-iframe-context");
    if (stored) {
      const ctx = JSON.parse(stored);
      return ctx.state?.source || DEFAULT_SOURCE_ID || "all";
    }
  } catch {
    // ignore
  }
  return DEFAULT_SOURCE_ID || "all";
});
```

- [ ] **Step 4: 修改 `effectiveSourceId` 计算逻辑**

找到第 563-569 行，替换为：
```typescript
const effectiveSourceId = useMemo(() => {
  const sourceFromContext = getIframeContext().source || DEFAULT_SOURCE_ID;
  return sourceFromContext ? sourceFromContext : "default";
}, []);
```

- [ ] **Step 5: 移除 `sources` 获取逻辑**

找到第 592-616 行，删除相关代码。

- [ ] **Step 6: 移除平台筛选 Select 组件 UI**

找到第 992-1007 行，删除整个 Select 组件。

- [ ] **Step 7: 移除 `displayPlatformValue` 变量**

如果存在，删除 `displayPlatformValue` 相关变量定义。

- [ ] **Step 8: 提交**

```bash
cd console && git add src/pages/Analytics/BusinessOverview/index.tsx
git commit -m "refactor(ui): remove platform filter from BusinessOverview page

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 15: 前端其他分析页面修改

**Files:**
- Modify: `console/src/pages/Analytics/Users/index.tsx`
- Modify: `console/src/pages/Analytics/Sessions/index.tsx`
- Modify: `console/src/pages/Analytics/Messages/index.tsx`
- Modify: `console/src/pages/Analytics/Traces/index.tsx`

- [ ] **Step 1: 修改 Users/index.tsx**

找到第 36-39 行，删除 `effectiveSourceId` 变量定义。
修改 API 调用，移除 `source_id` 参数。

- [ ] **Step 2: 修改 Sessions/index.tsx**

找到第 77-80 行，删除 `effectiveSourceId` 变量定义。
修改 API 调用，移除 `source_id` 参数。

- [ ] **Step 3: 修改 Messages/index.tsx**

找到第 41-44 行，删除 `effectiveSourceId` 变量定义。
修改 API 调用和导出函数，移除 `source_id` 参数。

- [ ] **Step 4: 修改 Traces/index.tsx**

找到第 79-84 行，删除 `effectiveSourceId` 变量定义。
修改 API 调用，移除 `source_id` 参数。

- [ ] **Step 5: 提交**

```bash
cd console && git add src/pages/Analytics/Users/index.tsx \
  src/pages/Analytics/Sessions/index.tsx \
  src/pages/Analytics/Messages/index.tsx \
  src/pages/Analytics/Traces/index.tsx
git commit -m "refactor(ui): remove source_id param from Analytics pages

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 16: 前端构建验证

**Files:**
- 无文件修改，仅验证

- [ ] **Step 1: 运行前端类型检查**

```bash
cd console && npm run type-check
```

Expected: 无类型错误

- [ ] **Step 2: 运行前端 Lint**

```bash
cd console && npm run lint
```

Expected: 无 Lint 错误

- [ ] **Step 3: 运行前端构建**

```bash
cd console && npm run build
```

Expected: 构建成功

---

## Task 17: 最终提交和验证

**Files:**
- 无文件修改，仅验证

- [ ] **Step 1: 运行后端测试**

```bash
cd monitor && venv/Scripts/python -m pytest tests/ -v
```

Expected: 所有测试通过

- [ ] **Step 2: 确认所有修改已提交**

```bash
git status
```

Expected: 无未提交的修改

- [ ] **Step 3: 查看提交历史**

```bash
git log --oneline -10
```

Expected: 所有提交按顺序排列

---

## Self-Review

**1. Spec Coverage:**
- 移除平台筛选 UI ✓ (Task 14)
- 移除 source_id 查询参数 ✓ (Tasks 1-15)
- 统一从请求头获取 source_id ✓ (Tasks 1, 9)
- 更新测试 ✓ (Task 10)
- 其他 4 个页面保持从请求头获取 ✓ (Task 15)

**2. Placeholder Scan:**
- 无 TBD、TODO 或占位符 ✓

**3. Type Consistency:**
- `_get_source_id_from_header()` 函数签名一致 ✓
- 所有 API 函数签名一致移除 source_id ✓
