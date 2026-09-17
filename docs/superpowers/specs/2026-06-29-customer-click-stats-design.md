# 运营看板客户点击统计卡片设计

## 背景

运营看板的"技能调用次数"卡片需要改为展示客户点击行为统计，帮助运营人员了解客户在定时任务推送的 HTML 页面中的点击行为。

## 需求

将"技能调用次数"卡片改为"客户数"卡片，主数值显示"查看方案客户数"，右侧显示两个小指标：

| 指标 | 数据来源 | 统计逻辑 |
|------|----------|----------|
| 查看方案客户数（主指标） | button_type='plan' | 按 cron_task_id + customer_id 去重 |
| 去洞察客户数（小指标） | button_type='insight' | 按 cron_task_id + customer_id 去重 |
| 去电访客户数（小指标） | button_type='phone' | 按 cron_task_id + customer_id 去重 |

数据来源表：`swe_html_preview_click_events`

时间范围筛选：与运营看板其他指标一致，支持日期范围和分行筛选。

增长率：支持环比计算，与其他指标一致。

## 设计方案

### 后端修改

#### 1. 数据模型 (monitor/src/monitor/app/models/tracing.py)

在 `OverviewStats` 类添加三个字段：

```python
class OverviewStats(BaseModel):
    """Overview dashboard statistics."""

    # ... existing fields ...

    # 客户点击统计
    plan_customers: int = 0      # 查看方案客户数
    insight_customers: int = 0   # 去洞察客户数
    phone_customers: int = 0     # 去电访客户数
```

#### 2. 查询服务 (monitor/src/monitor/app/services/tracing/query_service.py)

**新增方法 `_get_customer_click_stats`：**

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
    db = get_db_connection()

    # 构建 WHERE 条件
    conditions = ["source_id = $1", "clicked_at >= $2", "clicked_at < $3"]
    params = [source_id, start_date, end_date]

    if bbk_ids:
        bbk_list = bbk_ids.split(",")
        conditions.append(f"bbk_id IN ({','.join(f'${i+4}' for i in range(len(bbk_list)))})")
        params.extend(bbk_list)

    where_clause = " AND ".join(conditions)

    # 查询各 button_type 的去重客户数
    query = f"""
        SELECT
            button_type,
            COUNT(DISTINCT CONCAT(cron_task_id, '|', customer_id)) as customer_count
        FROM swe_html_preview_click_events
        WHERE {where_clause}
            AND button_type IN ('plan', 'insight', 'phone')
            AND cron_task_id IS NOT NULL
            AND customer_id IS NOT NULL
        GROUP BY button_type
    """

    rows = await db.fetch_all(query, params)

    result = {
        "plan_customers": 0,
        "insight_customers": 0,
        "phone_customers": 0,
    }

    for row in rows:
        button_type = row["button_type"]
        if button_type == "plan":
            result["plan_customers"] = row["customer_count"]
        elif button_type == "insight":
            result["insight_customers"] = row["customer_count"]
        elif button_type == "phone":
            result["phone_customers"] = row["customer_count"]

    return result
```

**修改 `_fetch_overview_data`：**

在 `asyncio.gather` 中添加新查询：

```python
async def _fetch_overview_data(...):
    return await asyncio.gather(
        # ... existing queries ...
        self._get_customer_click_stats(source_id, start_date, end_date, bbk_ids),  # 新增
    )
```

**修改 `_build_overview_stats`：**

添加新参数并传递到 OverviewStats：

```python
def _build_overview_stats(
    self,
    # ... existing params ...
    customer_click_stats: dict[str, int] = {},  # 新增
) -> OverviewStats:
    return OverviewStats(
        # ... existing fields ...
        plan_customers=customer_click_stats.get("plan_customers", 0),
        insight_customers=customer_click_stats.get("insight_customers", 0),
        phone_customers=customer_click_stats.get("phone_customers", 0),
    )
```

**修改 `get_overview_stats`：**

更新解包和传参：

```python
async def get_overview_stats(...):
    (
        # ... existing unpack ...
        customer_click_stats,  # 新增
    ) = await self._fetch_overview_data(...)

    return self._build_overview_stats(
        # ... existing params ...
        customer_click_stats=customer_click_stats,
    )
```

#### 3. 增长率统计

需要新增增长率计算接口或在现有 `getGrowthStats` 中添加字段。

**方案：新增独立接口 `get_customer_click_growth`**

```python
async def get_customer_click_growth(
    self,
    source_id: str,
    start_date: datetime,
    end_date: datetime,
    time_range: str = "day",
    bbk_ids: Optional[str] = None,
) -> dict[str, float | None]:
    """计算客户点击统计的环比增长率."""
    # 计算当前周期和上一周期的数据
    # 返回各 button_type 的增长率
```

或在现有增长率接口中添加字段，前端统一调用。

### 前端修改

#### 1. API 类型定义 (console/src/api/modules/tracing.ts)

更新 `OverviewStats` 接口：

```typescript
export interface OverviewStats {
  // ... existing fields ...

  // 客户点击统计
  plan_customers: number;      // 查看方案客户数
  insight_customers: number;   // 去洞察客户数
  phone_customers: number;     // 去电访客户数
}
```

更新 `getGrowthStats` 返回类型（如果使用统一接口）：

```typescript
getGrowthStats: async (...) => {
  // ... existing fields ...

  // 客户点击增长率
  planCustomersGrowth: number | null;
  insightCustomersGrowth: number | null;
  phoneCustomersGrowth: number | null;
}
```

#### 2. 卡片构建逻辑 (console/src/pages/Analytics/BusinessOverview/index.tsx)

修改 `buildMetricCards` 函数中的 skills 卡片：

```tsx
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
  breakdown: mapBreakdown(overviewStats?.branch_breakdown?.customers),  // 如果需要分行分布
},
```

#### 3. 状态管理

如果需要分行分布数据，需要在 `OverviewBranchBreakdown` 中添加 `customers` 字段。

### 样式

复用现有"活跃用户数"卡片的小指标样式：
- `.userValueWrap` - 包裹主数值和小指标
- `.userAnnotation` - 小指标容器
- `.annotationRow` - 单个小指标行
- `.annotationDot` - 颜色圆点

颜色选择：
- 去洞察客户数：蓝色 `#3b82f6`
- 去电访客户数：橙色 `#f97316`

### 文件清单

| 文件 | 修改内容 |
|------|----------|
| `monitor/src/monitor/app/models/tracing.py` | OverviewStats 添加三个字段 |
| `monitor/src/monitor/app/services/tracing/query_service.py` | 新增查询方法，修改现有方法 |
| `console/src/api/modules/tracing.ts` | 更新接口类型定义 |
| `console/src/pages/Analytics/BusinessOverview/index.tsx` | 修改卡片构建逻辑 |

### 测试要点

1. 后端查询正确性：验证 SQL 去重逻辑
2. 时间范围筛选：确保与现有指标一致
3. 分行筛选：确保正确传递 bbk_ids 参数
4. 增长率计算：验证环比逻辑
5. 前端展示：验证样式和数值显示

### 注意事项

1. `swe_html_preview_click_events` 表可能在 `src/swe/` 数据库，需要确认数据库连接
2. 增长率计算需要获取上一周期数据，确保时间计算正确
3. 如果数据量较大，考虑查询性能优化

## 实现顺序

1. 后端模型添加字段
2. 后端查询服务添加方法
3. 后端整合到现有接口
4. 前端类型定义更新
5. 前端卡片展示修改
6. 测试验证