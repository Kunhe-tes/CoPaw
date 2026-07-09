# 运营看板趋势图增强设计

## 背景

运营看板的调用量趋势图当前使用 SVG 手绘实现，仅展示"调用用户"和"调用次数"两个指标。需要增加 4 个新指标并改用 echarts 实现，提升图表交互性和可扩展性。

## 需求

### 新增指标
- 已读任务数
- 查看方案客户数
- 去洞察客户数
- 去电访客户数

### 保留原有指标
- 调用用户
- 调用次数

### 技术改进
- 将 SVG 手绘改为 echarts 实现
- 使用双 Y 轴适配不同数量级

## 设计方案

### 指标分组与 Y 轴分配

| 左 Y 轴 | 右 Y 轴 |
|---------|---------|
| 调用次数（折线） | 查看方案客户数（折线） |
| 调用用户（折线） | 去洞察客户数（折线） |
| 已读任务数（折线） | 去电访客户数（折线） |

分组依据：左 Y 轴指标数量级较大（调用相关），右 Y 轴指标数量级较小（客户相关）。

### 后端修改

#### 1. 修改 get_daily_trend 方法

文件：`monitor/src/monitor/app/services/tracing/query_service.py`

在现有查询基础上，新增两个子查询并合并结果：

**已读任务数查询：**
从 `swe_cron_executions` 表统计每日已读任务数：
```sql
SELECT
    DATE(actual_time) as date,
    COUNT(*) as read_tasks
FROM swe_cron_executions
WHERE read_at IS NOT NULL
    AND actual_time >= ? AND actual_time <= ?
GROUP BY DATE(actual_time)
```

**客户点击统计查询：**
从 `swe_html_preview_click_events` 表按 button_type 和日期分组：
```sql
SELECT
    DATE(clicked_at) as date,
    button_type,
    COUNT(DISTINCT CONCAT(COALESCE(cron_task_id, ''), '|', COALESCE(customer_id, ''))) as customer_count
FROM swe_html_preview_click_events
WHERE clicked_at >= ? AND clicked_at <= ?
    AND button_type IN ('plan', 'insight', 'phone')
    AND cron_task_id IS NOT NULL
    AND customer_id IS NOT NULL
GROUP BY DATE(clicked_at), button_type
```

**返回数据结构：**
```python
{
    "date": "2026-06-30",
    "calls": 1000,           # 调用次数（原有）
    "users": 50,             # 调用用户（原有）
    "read_tasks": 20,        # 已读任务数（新增）
    "plan_customers": 15,    # 查看方案客户数（新增）
    "insight_customers": 10, # 去洞察客户数（新增）
    "phone_customers": 5,    # 去电访客户数（新增）
}
```

### 前端修改

#### 1. 更新类型定义

文件：`console/src/api/modules/tracing.ts`

更新 `getDailyTrend` 和 `getHourlyTrend` 返回类型：
```typescript
trendData: {
  date: string;
  calls: number;
  users: number;
  read_tasks: number;        // 新增
  plan_customers: number;    # 新增
  insight_customers: number; // 新增
  phone_customers: number;   # 新增
}[];
```

文件：`console/src/pages/Analytics/BusinessOverview/types.ts`

更新 `TrendDatum` 接口：
```typescript
export interface TrendDatum {
  date: string;
  calls: number;
  users: number;
  read_tasks: number;        // 新增
  plan_customers: number;    # 新增
  insight_customers: number; # 新增
  phone_customers: number;   // 新增
}
```

#### 2. 替换 SVG 为 echarts

文件：`console/src/pages/Analytics/BusinessOverview/index.tsx`

**删除：**
- `buildTrendSvgData` 函数及相关辅助函数
- `getNiceAxisMax`、`formatTrendAxisLabel`、`buildTrendAxisTicks` 等函数
- SVG 渲染相关代码
- `trendSvg`、`activeTrendIndex`、`trendTooltipStyle` 状态

**新增：**
- `buildTrendChartOption` 函数生成 echarts 配置
- 使用 `ReactECharts` 组件替代 SVG

**echarts 配置示例：**
```typescript
function buildTrendChartOption(trendData: TrendDatum[]) {
  const dates = trendData.map(item =>
    item.date.includes(":")
      ? dayjs(item.date).format("HH:mm")
      : dayjs(item.date).format("MM-DD")
  );

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: {
      data: ['调用次数', '调用用户', '已读任务数', '查看方案客户数', '去洞察客户数', '去电访客户数'],
      bottom: 0
    },
    grid: {
      left: 60,
      right: 60,
      top: 20,
      bottom: 40
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { interval: 'auto' }
    },
    yAxis: [
      {
        type: 'value',
        name: '调用/用户/任务',
        position: 'left'
      },
      {
        type: 'value',
        name: '客户数',
        position: 'right'
      }
    ],
    series: [
      {
        name: '调用次数',
        type: 'line',
        yAxisIndex: 0,
        data: trendData.map(i => i.calls),
        smooth: true
      },
      {
        name: '调用用户',
        type: 'line',
        yAxisIndex: 0,
        data: trendData.map(i => i.users),
        smooth: true
      },
      {
        name: '已读任务数',
        type: 'line',
        yAxisIndex: 0,
        data: trendData.map(i => i.read_tasks),
        smooth: true
      },
      {
        name: '查看方案客户数',
        type: 'line',
        yAxisIndex: 1,
        data: trendData.map(i => i.plan_customers),
        smooth: true
      },
      {
        name: '去洞察客户数',
        type: 'line',
        yAxisIndex: 1,
        data: trendData.map(i => i.insight_customers),
        smooth: true
      },
      {
        name: '去电访客户数',
        type: 'line',
        yAxisIndex: 1,
        data: trendData.map(i => i.phone_customers),
        smooth: true
      }
    ]
  };
}
```

#### 3. 样式调整

文件：`console/src/pages/Analytics/BusinessOverview/index.module.less`

删除 SVG 相关样式（可选保留用于其他场景）：
- `.trendSvg`
- `.trendPlotArea`
- `.axisLeft`
- `.axisRight`
- 等手绘 SVG 样式

新增或保留 echarts 容器样式：
```less
.trendChart {
  height: 280px;
  padding: 12px;
}
```

### 文件清单

| 文件 | 修改内容 |
|------|----------|
| `monitor/src/monitor/app/services/tracing/query_service.py` | 修改 get_daily_trend、get_hourly_trend 方法 |
| `console/src/api/modules/tracing.ts` | 更新返回类型 |
| `console/src/pages/Analytics/BusinessOverview/types.ts` | 更新 TrendDatum 接口 |
| `console/src/pages/Analytics/BusinessOverview/index.tsx` | SVG 改为 echarts |
| `console/src/pages/Analytics/BusinessOverview/index.module.less` | 样式调整 |

### 测试要点

1. 后端查询正确性：验证新增指标的 SQL 统计逻辑
2. 时间范围筛选：确保与现有指标一致
3. 分行筛选：确保正确传递 bbk_ids 参数
4. 小时趋势：同样需要修改 get_hourly_trend 方法
5. echarts 渲染：验证双 Y 轴、图例、工具提示功能

### 注意事项

1. `swe_html_preview_click_events` 表用于客户点击统计
2. `swe_cron_executions` 表用于已读任务数统计
3. 小时趋势（get_hourly_trend）同样需要修改
4. 保持图表响应式布局