# 客户点击统计卡片实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将运营看板的"技能调用次数"卡片改为"客户数"卡片，展示查看方案客户数及两个小指标（去洞察客户数、去电访客户数）。

**Architecture:** 从 `swe_html_preview_click_events` 表按 `button_type` 分组统计去重客户数，复用现有运营概览接口返回新增字段，前端复用活跃用户卡片的小指标样式。

**Tech Stack:** Python/FastAPI (后端), TypeScript/React (前端), MySQL (数据库)

## Global Constraints

- 数据来源表：`swe_html_preview_click_events`
- 去重逻辑：`COUNT(DISTINCT CONCAT(cron_task_id, '|', customer_id))`
- button_type 取值：`plan`（查看方案）、`insight`（去洞察）、`phone`（去电访）
- 时间范围筛选与现有指标一致，支持 `start_date`、`end_date`、`bbk_ids`
- 增长率计算：与现有指标一致，支持环比

---

### Task 1: 后端模型添加字段

**Files:**
- Modify: `monitor/src/monitor/app/models/tracing.py:254-278`

**Interfaces:**
- Consumes: 无（新增字段）
- Produces: `OverviewStats.plan_customers`, `OverviewStats.insight_customers`, `OverviewStats.phone_customers`

- [ ] **Step 1: 在 OverviewStats 类添加三个新字段**

在 `monitor/src/monitor/app/models/tracing.py` 的 `OverviewStats` 类中，在 `total_skill_calls` 字段后添加：

```python
class OverviewStats(BaseModel):
    """Overview dashboard statistics."""

    # ... existing fields ...
    total_skill_calls: int = 0  # 技能调用总次数
    # 客户点击统计
    plan_customers: int = 0      # 查看方案客户数
    insight_customers: int = 0   # 去洞察客户数
    phone_customers: int = 0     # 去电访客户数
    # ... rest of existing fields ...
```

- [ ] **Step 2: 运行测试验证模型变更**

```bash
cd monitor && python -c "from src.monitor.app.models.tracing import OverviewStats; print(OverviewStats.model_fields.keys())"
```

Expected: 输出包含 `plan_customers`, `insight_customers`, `phone_customers`

- [ ] **Step 3: 提交模型变更**

```bash
git add monitor/src/monitor/app/models/tracing.py
git commit -m "feat(monitor): add customer click stats fields to OverviewStats model"
```

---

### Task 2: 后端查询服务添加方法

**Files:**
- Modify: `monitor/src/monitor/app/services/tracing/query_service.py:288-321, 323-364`

**Interfaces:**
- Consumes: `source_id`, `start_date`, `end_date`, `bbk_ids`
- Produces: `dict[str, int]` 包含 `plan_customers`, `insight_customers`, `phone_customers`

- [ ] **Step 1: 添加 `_get_customer_click_stats` 方法**

在 `monitor/src/monitor/app/services/tracing/query_service.py` 的 `TracingQueryService` 类中添加新方法：

```python
async def _get_customer_click_stats(
    self,
    source_id: str,
    start_date: datetime,
    end_date: datetime,
    bbk_ids: Optional[str] = None,
) -> dict[str, int]:
    """获取客户点击行为统计.

    从 swe_html_preview_click_events 表按 button_type 分组，
    统计 cron_task_id + customer_id 去重计数.

    Returns:
        dict with keys: plan_customers, insight_customers, phone_customers
    """
    db = self._db

    # 构建 WHERE 条件
    conditions = ["clicked_at >= %s", "clicked_at < %s"]
    params: list = [start_date, end_date]

    if source_id != "all":
        conditions.append("source_id = %s")
        params.append(source_id)
    else:
        # 排除测试平台
        from ...models.tracing import EXCLUDED_SOURCE_IDS
        exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
        conditions.append(f"source_id NOT IN ({exclude_placeholders})")
        params.extend(EXCLUDED_SOURCE_IDS)

    bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
    if bbk_filter_sql:
        conditions.append(bbk_filter_sql[4:])  # 移除 "AND " 前缀
        params.extend(bbk_filter_params)

    where_clause = " AND ".join(conditions)

    # 查询各 button_type 的去重客户数
    query = f"""
        SELECT
            button_type,
            COUNT(DISTINCT CONCAT(COALESCE(cron_task_id, ''), '|', COALESCE(customer_id, ''))) as customer_count
        FROM swe_html_preview_click_events
        WHERE {where_clause}
            AND button_type IN ('plan', 'insight', 'phone')
            AND cron_task_id IS NOT NULL
            AND customer_id IS NOT NULL
        GROUP BY button_type
    """

    rows = await db.fetch_all(query, tuple(params))

    result = {
        "plan_customers": 0,
        "insight_customers": 0,
        "phone_customers": 0,
    }

    for row in rows:
        button_type = row["button_type"]
        if button_type == "plan":
            result["plan_customers"] = row["customer_count"] or 0
        elif button_type == "insight":
            result["insight_customers"] = row["customer_count"] or 0
        elif button_type == "phone":
            result["phone_customers"] = row["customer_count"] or 0

    return result
```

- [ ] **Step 2: 修改 `_fetch_overview_data` 方法**

在 `asyncio.gather` 中添加新查询。找到 `_fetch_overview_data` 方法（约第288行），修改返回值：

```python
async def _fetch_overview_data(
    self,
    source_id: str,
    start_date: datetime,
    end_date: datetime,
    bbk_ids: Optional[str] = None,
) -> list:
    """并行获取运营概览的各项数据."""
    return await asyncio.gather(
        self._get_total_users(source_id, start_date, end_date, bbk_ids),
        self._get_online_users(source_id, bbk_ids),
        self._get_token_stats(source_id, start_date, end_date, bbk_ids),
        self._get_model_distribution(
            source_id,
            start_date,
            end_date,
            bbk_ids,
        ),
        self._get_top_tools(source_id, start_date, end_date, bbk_ids),
        self._get_top_skills(source_id, start_date, end_date, bbk_ids),
        self._get_mcp_stats(source_id, start_date, end_date, bbk_ids),
        self._get_branch_breakdown(
            source_id,
            start_date,
            end_date,
            bbk_ids,
        ),
        self._get_total_skill_calls(
            source_id,
            start_date,
            end_date,
            bbk_ids,
        ),
        self._get_customer_click_stats(  # 新增
            source_id,
            start_date,
            end_date,
            bbk_ids,
        ),
    )
```

- [ ] **Step 3: 修改 `_build_overview_stats` 方法**

添加新参数并传递到 OverviewStats。找到 `_build_overview_stats` 方法（约第323行）：

```python
def _build_overview_stats(
    self,
    total_users: int,
    it_users: int,
    business_users: int,
    online_users: int,
    online_user_ids: list[str],
    token_row: Optional[dict],
    model_distribution: list,
    top_tools: list,
    top_skills: list,
    top_mcp_tools: list,
    mcp_servers: list,
    branch_breakdown: Any,
    total_skill_calls: int = 0,
    customer_click_stats: dict[str, int] = {},  # 新增参数
) -> OverviewStats:
    """构建运营概览统计对象."""
    return OverviewStats(
        online_users=online_users,
        online_user_ids=online_user_ids,
        total_users=total_users,
        it_users=it_users,
        business_users=business_users,
        model_distribution=model_distribution,
        total_tokens=token_row["total_tokens"] or 0 if token_row else 0,
        input_tokens=token_row["input_tokens"] or 0 if token_row else 0,
        output_tokens=token_row["output_tokens"] or 0 if token_row else 0,
        total_sessions=(
            token_row["total_sessions"] or 0 if token_row else 0
        ),
        total_conversations=(
            token_row["total_traces"] or 0 if token_row else 0
        ),
        total_skill_calls=total_skill_calls,
        plan_customers=customer_click_stats.get("plan_customers", 0),  # 新增
        insight_customers=customer_click_stats.get("insight_customers", 0),  # 新增
        phone_customers=customer_click_stats.get("phone_customers", 0),  # 新增
        avg_duration_ms=self._extract_avg_duration(token_row),
        top_tools=top_tools,
        top_skills=top_skills,
        top_mcp_tools=top_mcp_tools,
        mcp_servers=mcp_servers,
        daily_trend=[],
        branch_breakdown=branch_breakdown,
    )
```

- [ ] **Step 4: 修改 `get_overview_stats` 方法**

更新解包和传参。找到 `get_overview_stats` 方法（约第241行）：

```python
async def get_overview_stats(
    self,
    source_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    bbk_ids: Optional[str] = None,
) -> OverviewStats:
    """获取运营概览统计."""
    if start_date is None:
        start_date = datetime.now() - timedelta(days=30)
    if end_date is None:
        end_date = datetime.now() + timedelta(days=1)

    # 并行获取当前周期各项统计数据
    (
        (total_users, it_users, business_users),
        (online_users, online_user_ids),
        token_row,
        model_distribution,
        top_tools,
        top_skills,
        (top_mcp_tools, mcp_servers),
        branch_breakdown,
        total_skill_calls,
        customer_click_stats,  # 新增
    ) = await self._fetch_overview_data(
        source_id,
        start_date,
        end_date,
        bbk_ids,
    )

    return self._build_overview_stats(
        total_users=total_users,
        it_users=it_users,
        business_users=business_users,
        online_users=online_users,
        online_user_ids=online_user_ids,
        model_distribution=model_distribution,
        token_row=token_row,
        top_tools=top_tools,
        top_skills=top_skills,
        top_mcp_tools=top_mcp_tools,
        mcp_servers=mcp_servers,
        branch_breakdown=branch_breakdown,
        total_skill_calls=total_skill_calls,
        customer_click_stats=customer_click_stats,  # 新增
    )
```

- [ ] **Step 5: 提交查询服务变更**

```bash
git add monitor/src/monitor/app/services/tracing/query_service.py
git commit -m "feat(monitor): add customer click stats query method"
```

---

### Task 3: 后端增长率统计添加字段

**Files:**
- Modify: `monitor/src/monitor/app/services/tracing/query_service.py:563-877`

**Interfaces:**
- Consumes: 现有增长率接口结构
- Produces: 新增 `planCustomersGrowth`, `insightCustomersGrowth`, `phoneCustomersGrowth`

- [ ] **Step 1: 在 `get_growth_stats` 方法中添加客户点击增长率计算**

找到 `get_growth_stats` 方法（约第563行），在方法末尾返回字典中添加：

```python
# 在 get_growth_stats 方法的末尾，return 语句之前添加

async def get_customer_click_stats_for_growth(
    s: datetime,
    e: datetime,
    is_prev: bool = False,
) -> dict[str, int]:
    """获取客户点击统计（用于增长率计算）."""
    time_compare = "<" if is_prev else "<="
    if source_id == "all":
        exclude_placeholders = ", ".join(
            ["%s"] * len(EXCLUDED_SOURCE_IDS),
        )
        query = f"""
            SELECT
                button_type,
                COUNT(DISTINCT CONCAT(COALESCE(cron_task_id, ''), '|', COALESCE(customer_id, ''))) as customer_count
            FROM swe_html_preview_click_events
            WHERE clicked_at >= %s AND clicked_at {time_compare} %s
              AND source_id NOT IN ({exclude_placeholders})
              AND button_type IN ('plan', 'insight', 'phone')
              AND cron_task_id IS NOT NULL
              AND customer_id IS NOT NULL{bbk_filter_sql}
            GROUP BY button_type
        """
        params = (s, e, *EXCLUDED_SOURCE_IDS, *bbk_filter_params)
        rows = await self._db.fetch_all(query, params)
    else:
        query = f"""
            SELECT
                button_type,
                COUNT(DISTINCT CONCAT(COALESCE(cron_task_id, ''), '|', COALESCE(customer_id, ''))) as customer_count
            FROM swe_html_preview_click_events
            WHERE source_id = %s AND clicked_at >= %s AND clicked_at {time_compare} %s
              AND button_type IN ('plan', 'insight', 'phone')
              AND cron_task_id IS NOT NULL
              AND customer_id IS NOT NULL{bbk_filter_sql}
            GROUP BY button_type
        """
        params = (source_id, s, e, *bbk_filter_params)
        rows = await self._db.fetch_all(query, params)

    result = {"plan": 0, "insight": 0, "phone": 0}
    for row in rows:
        btn = row["button_type"]
        if btn in result:
            result[btn] = row["customer_count"] or 0
    return result

# 获取当前和上一周期的客户点击统计
curr_click_stats = await get_customer_click_stats_for_growth(start_date, end_date, is_prev=False)
prev_click_stats = await get_customer_click_stats_for_growth(prev_start, prev_end, is_prev=True)

# 在 return 字典中添加（约第848行之后）
return {
    # ... existing fields ...
    "planCustomersGrowth": calc_growth(
        curr_click_stats.get("plan", 0),
        prev_click_stats.get("plan", 0),
    ),
    "insightCustomersGrowth": calc_growth(
        curr_click_stats.get("insight", 0),
        prev_click_stats.get("insight", 0),
    ),
    "phoneCustomersGrowth": calc_growth(
        curr_click_stats.get("phone", 0),
        prev_click_stats.get("phone", 0),
    ),
}
```

- [ ] **Step 2: 提交增长率统计变更**

```bash
git add monitor/src/monitor/app/services/tracing/query_service.py
git commit -m "feat(monitor): add customer click growth stats"
```

---

### Task 4: 前端类型定义更新

**Files:**
- Modify: `console/src/api/modules/tracing.ts:7-27, 701-725`

**Interfaces:**
- Consumes: 后端返回的新字段
- Produces: 更新后的 TypeScript 接口

- [ ] **Step 1: 更新 OverviewStats 接口**

在 `console/src/api/modules/tracing.ts` 中找到 `OverviewStats` 接口（约第7行），添加新字段：

```typescript
export interface OverviewStats {
  online_users: number;
  online_user_ids: string[];
  total_users: number;
  it_users: number;
  business_users: number;
  model_distribution: ModelUsage[];
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  total_sessions: number;
  total_conversations: number;
  total_skill_calls: number;
  // 新增：客户点击统计
  plan_customers: number;      // 查看方案客户数
  insight_customers: number;   // 去洞察客户数
  phone_customers: number;     // 去电访客户数
  avg_duration_ms: number;
  top_tools: ToolUsage[];
  top_skills: SkillUsage[];
  top_mcp_tools: MCPToolUsage[];
  mcp_servers: MCPServerUsage[];
  daily_trend: DailyStats[];
  branch_breakdown: OverviewBranchBreakdown;
}
```

- [ ] **Step 2: 更新 getGrowthStats 返回类型**

在 `console/src/api/modules/tracing.ts` 中找到 `getGrowthStats` 方法（约第701行），更新返回类型：

```typescript
getGrowthStats: async (
  startDate: string,
  endDate: string,
  timeRange: string = "day",
  bbkIds?: string,
): Promise<{
  callsGrowth: number | null;
  tokensGrowth: number | null;
  sessionGrowth: number | null;
  userGrowth: number | null;
  skillGrowth: number | null;
  cronGrowth: number | null;
  avgRoundsGrowth: number | null;
  multiRoundRatioGrowth: number | null;
  avgDurationGrowth: number | null;
  avgSessionsPerUserGrowth: number | null;
  // 新增：客户点击增长率
  planCustomersGrowth: number | null;
  insightCustomersGrowth: number | null;
  phoneCustomersGrowth: number | null;
}> => {
  const params = new URLSearchParams();
  params.append("start_date", startDate);
  params.append("end_date", endDate);
  params.append("time_range", timeRange);
  if (bbkIds) params.append("bbk_ids", bbkIds);
  return request(`/monitor/tracing/growth-stats?${params.toString()}`);
},
```

- [ ] **Step 3: 提交类型定义变更**

```bash
git add console/src/api/modules/tracing.ts
git commit -m "feat(console): add customer click stats types"
```

---

### Task 5: 前端卡片展示修改

**Files:**
- Modify: `console/src/pages/Analytics/BusinessOverview/index.tsx:101-181, 647-669`

**Interfaces:**
- Consumes: `OverviewStats`, `getGrowthStats` 返回值
- Produces: 更新后的卡片展示

- [ ] **Step 1: 更新 growthStats 状态类型**

在 `console/src/pages/Analytics/BusinessOverview/index.tsx` 中找到 `growthStats` 状态定义（约第647行），添加新字段：

```typescript
const [growthStats, setGrowthStats] = useState<{
  callsGrowth: number | null;
  tokensGrowth: number | null;
  sessionGrowth: number | null;
  userGrowth: number | null;
  skillGrowth: number | null;
  cronGrowth: number | null;
  avgRoundsGrowth: number | null;
  multiRoundRatioGrowth: number | null;
  avgDurationGrowth: number | null;
  avgSessionsPerUserGrowth: number | null;
  // 新增
  planCustomersGrowth: number | null;
  insightCustomersGrowth: number | null;
  phoneCustomersGrowth: number | null;
}>({
  callsGrowth: null,
  tokensGrowth: null,
  sessionGrowth: null,
  userGrowth: null,
  skillGrowth: null,
  cronGrowth: null,
  avgRoundsGrowth: null,
  multiRoundRatioGrowth: null,
  avgDurationGrowth: null,
  avgSessionsPerUserGrowth: null,
  // 新增
  planCustomersGrowth: null,
  insightCustomersGrowth: null,
  phoneCustomersGrowth: null,
});
```

- [ ] **Step 2: 修改 buildMetricCards 函数参数类型**

找到 `buildMetricCards` 函数（约第101行），更新参数类型：

```typescript
function buildMetricCards(
  overviewStats: OverviewStats | null,
  taskStatusSummary: TaskStatusSummary | null,
  growthStats: {
    callsGrowth: number | null;
    tokensGrowth: number | null;
    sessionGrowth: number | null;
    userGrowth: number | null;
    skillGrowth: number | null;
    cronGrowth: number | null;
    // 新增
    planCustomersGrowth: number | null;
    insightCustomersGrowth: number | null;
    phoneCustomersGrowth: number | null;
  },
): OverviewMetricCard[] {
```

- [ ] **Step 3: 修改 skills 卡片为 customers 卡片**

在 `buildMetricCards` 函数的返回数组中，将最后一个卡片（skills）修改为：

```typescript
{
  key: "customers",
  title: "客户数",
  valueText: (
    <span className={styles.userValueWrap}>
      <span className={styles.userTotal}>
        {formatNumber(overviewStats?.plan_customers ?? 0)}
      </span>
      <span className={styles.userAnnotation}>
        <span className={styles.annotationRow}>
          <span className={styles.annotationDot} style={{ background: "#3b82f6" }} />
          去洞察 {formatNumber(overviewStats?.insight_customers ?? 0)}
        </span>
        <span className={styles.annotationRow}>
          <span className={styles.annotationDot} style={{ background: "#f97316" }} />
          去电访 {formatNumber(overviewStats?.phone_customers ?? 0)}
        </span>
      </span>
    </span>
  ),
  changeText: formatChange(growthStats.planCustomersGrowth),
  changeDirection: toChangeDirection(growthStats.planCustomersGrowth),
  accentColor: METRIC_ACCENT_COLORS[4],
  breakdown: null, // 暂不支持分行分布
},
```

- [ ] **Step 4: 提交卡片展示变更**

```bash
git add console/src/pages/Analytics/BusinessOverview/index.tsx
git commit -m "feat(console): update metric card to show customer click stats"
```

---

### Task 6: 集成测试

**Files:**
- 无新增文件，验证现有功能

- [ ] **Step 1: 启动后端服务验证接口**

```bash
cd monitor && python -m pytest tests/unit/tracing/test_query_service.py -v -k "overview"
```

Expected: 测试通过

- [ ] **Step 2: 验证前端类型检查**

```bash
cd console && npm run type-check
```

Expected: 无类型错误

- [ ] **Step 3: 提交集成变更（如有）**

```bash
git add -A
git commit -m "test: verify customer click stats integration"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - [x] OverviewStats 添加三个字段 ✓ (Task 1)
   - [x] 查询服务添加方法 ✓ (Task 2)
   - [x] 增长率统计添加字段 ✓ (Task 3)
   - [x] 前端类型定义更新 ✓ (Task 4)
   - [x] 卡片展示修改 ✓ (Task 5)

2. **Placeholder scan:**
   - 无 "TBD"、"TODO"、"implement later" 等占位符
   - 所有代码步骤都有完整实现代码

3. **Type consistency:**
   - 后端 `plan_customers` ↔ 前端 `plan_customers` ✓
   - 后端 `insight_customers` ↔ 前端 `insight_customers` ✓
   - 后端 `phone_customers` ↔ 前端 `phone_customers` ✓
   - 增长率字段命名使用 camelCase ✓
