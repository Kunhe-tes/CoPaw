# 趋势图增强实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为运营看板趋势图增加 4 个新指标（已读任务数、查看方案客户数、去洞察客户数、去电访客户数），并将 SVG 手绘改为 echarts 实现。

**Architecture:** 后端修改两个趋势查询方法，增加三个子查询合并结果；前端删除 SVG 相关代码，使用 echarts 渲染双 Y 轴折线图。

**Tech Stack:** Python/FastAPI (后端), TypeScript/React/echarts (前端), MySQL (数据库)

## Global Constraints

- 数据来源表：`swe_html_preview_click_events`（客户点击）、`swe_cron_executions`（已读任务）
- 去重逻辑：`COUNT(DISTINCT CONCAT(COALESCE(cron_task_id, ''), '|', COALESCE(customer_id, '')))`
- button_type 取值：`plan`、`insight`、`phone`
- 时间范围筛选：与现有指标一致
- 小时趋势也需要同样修改

---

### Task 1: 后端修改 get_daily_trend 方法

**Files:**
- Modify: `monitor/src/monitor/app/services/tracing/query_service.py:964-1026`

**Interfaces:**
- Consumes: `source_id`, `start_date`, `end_date`, `bbk_ids`
- Produces: 每条记录新增 `read_tasks`, `plan_customers`, `insight_customers`, `phone_customers` 字段

- [ ] **Step 1: 添加已读任务数子查询**

在 `get_daily_trend` 方法中，找到现有的查询语句后（约第1015行），添加已读任务数查询逻辑。

在现有查询获取 `rows` 后，添加：

```python
        # 查询已读任务数
        read_tasks_query = f"""
            SELECT
                DATE(e.actual_time) as date,
                COUNT(*) as read_tasks
            FROM swe_cron_executions e
            INNER JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE e.actual_time >= %s AND e.actual_time <= %s
              AND j.status != 'deleted'
              AND j.deleted_at IS NULL
              AND e.read_at IS NOT NULL{bbk_filter_sql.replace('bbk_id', 'j.bbk_id')}
            GROUP BY DATE(e.actual_time)
        """
        read_tasks_rows = await self._db.fetch_all(read_tasks_query, params)
        read_tasks_map = {
            row["date"].strftime("%Y-%m-%d") if row["date"] else "": row["read_tasks"] or 0
            for row in read_tasks_rows
        }
```

- [ ] **Step 2: 添加客户点击统计子查询**

在已读任务查询后，添加客户点击统计：

```python
        # 查询客户点击统计
        click_query = f"""
            SELECT
                DATE(clicked_at) as date,
                button_type,
                COUNT(DISTINCT CONCAT(COALESCE(cron_task_id, ''), '|', COALESCE(customer_id, ''))) as customer_count
            FROM swe_html_preview_click_events
            WHERE clicked_at >= %s AND clicked_at <= %s
              AND button_type IN ('plan', 'insight', 'phone')
              AND cron_task_id IS NOT NULL
              AND customer_id IS NOT NULL{bbk_filter_sql}
            GROUP BY DATE(clicked_at), button_type
        """
        click_rows = await self._db.fetch_all(click_query, params)

        # 按日期和类型组织数据
        click_map: dict[str, dict[str, int]] = {}
        for row in click_rows:
            date_key = row["date"].strftime("%Y-%m-%d") if row["date"] else ""
            if date_key not in click_map:
                click_map[date_key] = {"plan": 0, "insight": 0, "phone": 0}
            btn_type = row["button_type"]
            if btn_type in click_map[date_key]:
                click_map[date_key][btn_type] = row["customer_count"] or 0
```

- [ ] **Step 3: 修改返回结果合并新数据**

找到返回语句（约第1016行），修改为：

```python
        return [
            {
                "date": (
                    row["date"].strftime("%Y-%m-%d") if row["date"] else ""
                ),
                "calls": row["calls"] or 0,
                "tokens": row["tokens"] or 0,
                "users": row["users"] or 0,
                "read_tasks": read_tasks_map.get(
                    row["date"].strftime("%Y-%m-%d") if row["date"] else "", 0
                ),
                "plan_customers": click_map.get(
                    row["date"].strftime("%Y-%m-%d") if row["date"] else {}, {}
                ).get("plan", 0),
                "insight_customers": click_map.get(
                    row["date"].strftime("%Y-%m-%d") if row["date"] else "", {}
                ).get("insight", 0),
                "phone_customers": click_map.get(
                    row["date"].strftime("%Y-%m-%d") if row["date"] else "", {}
                ).get("phone", 0),
            }
            for row in rows
        ]
```

- [ ] **Step 4: 提交变更**

```bash
git add monitor/src/monitor/app/services/tracing/query_service.py
git commit -m "feat(monitor): add read_tasks and customer stats to daily trend"
```

---

### Task 2: 后端修改 get_hourly_trend 方法

**Files:**
- Modify: `monitor/src/monitor/app/services/tracing/query_service.py:1028-1106`

**Interfaces:**
- Consumes: `source_id`, `start_date`, `end_date`, `bbk_ids`
- Produces: 同 Task 1，新增 4 个字段

- [ ] **Step 1: 添加已读任务数子查询（按小时）**

在 `get_hourly_trend` 方法中（约第1093行后），添加：

```python
        # 查询已读任务数（按小时）
        read_tasks_query = f"""
            SELECT
                HOUR(e.actual_time) as hour_bucket,
                COUNT(*) as read_tasks
            FROM swe_cron_executions e
            INNER JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE e.actual_time >= %s AND e.actual_time <= %s
              AND j.status != 'deleted'
              AND j.deleted_at IS NULL
              AND e.read_at IS NOT NULL{bbk_filter_sql.replace('bbk_id', 'j.bbk_id')}
            GROUP BY HOUR(e.actual_time)
        """
        read_tasks_rows = await self._db.fetch_all(read_tasks_query, params)
        read_tasks_hour_map = {
            int(row["hour_bucket"]): row["read_tasks"] or 0
            for row in read_tasks_rows
        }

        # 查询客户点击统计（按小时）
        click_query = f"""
            SELECT
                HOUR(clicked_at) as hour_bucket,
                button_type,
                COUNT(DISTINCT CONCAT(COALESCE(cron_task_id, ''), '|', COALESCE(customer_id, ''))) as customer_count
            FROM swe_html_preview_click_events
            WHERE clicked_at >= %s AND clicked_at <= %s
              AND button_type IN ('plan', 'insight', 'phone')
              AND cron_task_id IS NOT NULL
              AND customer_id IS NOT NULL{bbk_filter_sql}
            GROUP BY HOUR(clicked_at), button_type
        """
        click_rows = await self._db.fetch_all(click_query, params)

        click_hour_map: dict[int, dict[str, int]] = {}
        for row in click_rows:
            hour_key = int(row["hour_bucket"])
            if hour_key not in click_hour_map:
                click_hour_map[hour_key] = {"plan": 0, "insight": 0, "phone": 0}
            btn_type = row["button_type"]
            if btn_type in click_hour_map[hour_key]:
                click_hour_map[hour_key][btn_type] = row["customer_count"] or 0
```

- [ ] **Step 2: 修改返回结果合并新数据**

找到返回语句（约第1098行），修改为：

```python
        return [
            {
                "date": f"{day_prefix} {hour:02d}:00",
                "calls": hour_map.get(hour, {}).get("calls", 0),
                "tokens": hour_map.get(hour, {}).get("tokens", 0),
                "users": hour_map.get(hour, {}).get("users", 0),
                "read_tasks": read_tasks_hour_map.get(hour, 0),
                "plan_customers": click_hour_map.get(hour, {}).get("plan", 0),
                "insight_customers": click_hour_map.get(hour, {}).get("insight", 0),
                "phone_customers": click_hour_map.get(hour, {}).get("phone", 0),
            }
            for hour in range(max_hour + 1)
        ]
```

- [ ] **Step 3: 提交变更**

```bash
git add monitor/src/monitor/app/services/tracing/query_service.py
git commit -m "feat(monitor): add read_tasks and customer stats to hourly trend"
```

---

### Task 3: 前端类型定义更新

**Files:**
- Modify: `console/src/pages/Analytics/BusinessOverview/types.ts:62-66`
- Modify: `console/src/api/modules/tracing.ts`

**Interfaces:**
- Consumes: 后端返回的新数据结构
- Produces: 更新后的 TypeScript 接口

- [ ] **Step 1: 更新 TrendDatum 接口**

在 `console/src/pages/Analytics/BusinessOverview/types.ts` 中找到 `TrendDatum` 接口，修改为：

```typescript
export interface TrendDatum {
  date: string;
  calls: number;
  users: number;
  read_tasks: number;        // 新增
  plan_customers: number;    // 新增
  insight_customers: number; // 新增
  phone_customers: number;   // 新增
}
```

- [ ] **Step 2: 更新 API 返回类型**

在 `console/src/api/modules/tracing.ts` 中找到 `getDailyTrend` 方法返回类型，确认包含新字段：

```typescript
getDailyTrend: async (
  startDate?: string,
  endDate?: string,
  bbkIds?: string,
): Promise<{
  trendData: TrendDatum[];
}> => {
  // ...
},
```

- [ ] **Step 3: 运行类型检查**

```bash
cd console && npx tsc --noEmit
```

Expected: 无类型错误

- [ ] **Step 4: 提交变更**

```bash
git add console/src/pages/Analytics/BusinessOverview/types.ts
git add console/src/api/modules/tracing.ts
git commit -m "feat(console): update TrendDatum type for new metrics"
```

---

### Task 4: 前端趋势图改用 echarts

**Files:**
- Modify: `console/src/pages/Analytics/BusinessOverview/index.tsx`

**Interfaces:**
- Consumes: `TrendDatum[]`
- Produces: echarts 渲染的趋势图

- [ ] **Step 1: 删除 SVG 相关状态和函数**

在 `BusinessOverviewPage` 组件中：

1. 删除 `activeTrendIndex` 状态（约第700行）：
```typescript
const [activeTrendIndex, setActiveTrendIndex] = useState<number | null>(null);
```

2. 删除以下状态和计算：
```typescript
const trendSvg = useMemo(() => buildTrendSvgData(trendData), [trendData]);
const activeTrendZone = activeTrendIndex === null ? null : trendSvg.hoverZones[activeTrendIndex] ?? null;
const trendTooltipStyle = activeTrendZone ? { ... } : undefined;
```

3. 删除以下函数（约第500-630行）：
- `getNiceAxisMax`
- `getBarWidth`
- `getLabelInterval`
- `buildTrendAxisTicks`
- `buildTrendSvgData`
- `formatTrendAxisLabel`

- [ ] **Step 2: 添加 buildTrendChartOption 函数**

在删除的函数位置添加新函数：

```typescript
function buildTrendChartOption(trendData: TrendDatum[]) {
  const dates = trendData.map((item) =>
    item.date.includes(":")
      ? dayjs(item.date).format("HH:mm")
      : dayjs(item.date).format("MM-DD"),
  );

  return {
    tooltip: {
      trigger: "axis" as const,
      axisPointer: { type: "cross" as const },
    },
    legend: {
      data: [
        "调用次数",
        "调用用户",
        "已读任务数",
        "查看方案客户数",
        "去洞察客户数",
        "去电访客户数",
      ],
      bottom: 0,
    },
    grid: {
      left: 60,
      right: 60,
      top: 20,
      bottom: 40,
    },
    xAxis: {
      type: "category" as const,
      data: dates,
      axisLabel: { interval: "auto" as const },
    },
    yAxis: [
      {
        type: "value" as const,
        name: "调用/用户/任务",
        position: "left" as const,
      },
      {
        type: "value" as const,
        name: "客户数",
        position: "right" as const,
      },
    ],
    series: [
      {
        name: "调用次数",
        type: "line" as const,
        yAxisIndex: 0,
        data: trendData.map((i) => i.calls),
        smooth: true,
        itemStyle: { color: "#2563eb" },
      },
      {
        name: "调用用户",
        type: "line" as const,
        yAxisIndex: 0,
        data: trendData.map((i) => i.users),
        smooth: true,
        itemStyle: { color: "#22c55e" },
      },
      {
        name: "已读任务数",
        type: "line" as const,
        yAxisIndex: 0,
        data: trendData.map((i) => i.read_tasks),
        smooth: true,
        itemStyle: { color: "#f97316" },
      },
      {
        name: "查看方案客户数",
        type: "line" as const,
        yAxisIndex: 1,
        data: trendData.map((i) => i.plan_customers),
        smooth: true,
        itemStyle: { color: "#3b82f6" },
      },
      {
        name: "去洞察客户数",
        type: "line" as const,
        yAxisIndex: 1,
        data: trendData.map((i) => i.insight_customers),
        smooth: true,
        itemStyle: { color: "#8b5cf6" },
      },
      {
        name: "去电访客户数",
        type: "line" as const,
        yAxisIndex: 1,
        data: trendData.map((i) => i.phone_customers),
        smooth: true,
        itemStyle: { color: "#ec4899" },
      },
    ],
  };
}
```

- [ ] **Step 3: 替换趋势图渲染部分**

找到趋势图渲染部分（约第1315-1468行），将整个 `<article className={styles.panelLarge}>` 内的内容替换为：

```tsx
        <article className={styles.panelLarge}>
          <div className={styles.panelHeader}>
            <h3 className={styles.panelTitle}>调用量趋势</h3>
          </div>
          <div className={styles.trendChart}>
            <ReactECharts
              option={buildTrendChartOption(trendData)}
              style={{ height: 280 }}
            />
          </div>
        </article>
```

- [ ] **Step 4: 删除未使用的导入**

检查并删除未使用的导入：
- `TrendingUp`, `TrendingDown` - 如果只用于趋势图 tooltip 可以删除

- [ ] **Step 5: 运行类型检查**

```bash
cd console && npm run type-check
```

Expected: 无类型错误

- [ ] **Step 6: 提交变更**

```bash
git add console/src/pages/Analytics/BusinessOverview/index.tsx
git commit -m "feat(console): replace SVG trend chart with echarts"
```

---

### Task 5: 样式清理和测试

**Files:**
- Modify: `console/src/pages/Analytics/BusinessOverview/index.module.less`

- [ ] **Step 1: 删除 SVG 相关样式（可选）**

在 `index.module.less` 中，可以删除以下未使用的样式类（如果没有其他地方使用）：
- `.trendSvg`
- `.gridLine`
- `.trendBar`
- `.trendBarActive`
- `.trendLine`
- `.trendPoint`
- `.trendPointActive`
- `.trendHoverZone`
- `.trendGuideLine`
- `.trendTooltip`
- `.axisLeft`
- `.axisRight`

保留：
- `.trendChart`
- `.trendLegend`
- `.legendItem`
- `.legendBarMark`
- `.legendLineMark`

- [ ] **Step 2: 运行前端完整构建**

```bash
cd console && npm run build
```

Expected: 构建成功

- [ ] **Step 3: 提交变更**

```bash
git add console/src/pages/Analytics/BusinessOverview/index.module.less
git commit -m "style: remove unused SVG trend chart styles"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - [x] 已读任务数统计 - Task 1 & 2
   - [x] 查看方案客户数统计 - Task 1 & 2
   - [x] 去洞察客户数统计 - Task 1 & 2
   - [x] 去电访客户数统计 - Task 1 & 2
   - [x] 前端类型定义更新 - Task 3
   - [x] echarts 替换 SVG - Task 4
   - [x] 双 Y 轴支持 - Task 4

2. **Placeholder scan:**
   - 无 "TBD"、"TODO"、"implement later" 等占位符
   - 所有代码步骤都有完整实现代码

3. **Type consistency:**
   - `read_tasks` ↔ `read_tasks` ✓
   - `plan_customers` ↔ `plan_customers` ✓
   - `insight_customers` ↔ `insight_customers` ✓
   - `phone_customers` ↔ `phone_customers` ✓
