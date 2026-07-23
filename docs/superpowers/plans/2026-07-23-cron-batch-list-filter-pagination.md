# Cron Batch 列表全局筛选与固定分页计划

## 问题与边界

当前“所有 Batch”先由服务端按页返回 20 条，再由前端只筛选当前页；列表同时依赖内部滚动，窄宽度下任务名、标识和状态信息较拥挤。本次只调整 Batch 概览列表，不改变日期/状态过滤、详情、Intent、Worker 或 Batch 状态语义。

## 验收要求

- 每次列表请求固定 `page_size=4`，分页器不再允许切换每页条数。
- 搜索覆盖当前日期、状态和渠道范围内的全部 Batch，匹配 Batch ID、父任务 ID、外部任务 ID、租户、provider、model、agent。
- 搜索条件由服务端参与总数统计和分页；搜索变化回到第 1 页，并避免旧请求覆盖新结果。
- 列表一页恰好展示最多 4 行，无内部纵向滚动；长文本稳定截断，状态与进度对齐。
- 空状态、结果计数、搜索框文案明确表达“全局筛选”。

## 实施单元

1. `tests/unit/monitor/test_cron_dispatch_monitor.py`、`monitor/src/monitor/app/services/cron/query_service.py`、`monitor/src/monitor/app/routers/cron.py`
   - 先补查询词参与 SQL 条件、参数顺序、总数与分页的失败测试。
   - 路由接收可选 `query`，查询服务使用参数化 `LIKE` 对约定字段做不区分大小写的包含匹配。

2. `console/src/pages/Monitor/CronBatchDispatch/index.test.tsx`、`console/src/pages/Monitor/CronBatchDispatch/index.tsx`、`console/src/api/modules/monitor.ts`
   - 先补固定 4 条请求、搜索词发往服务端、搜索回到第 1 页、无当前页客户端过滤的失败测试。
   - 删除客户端当前页过滤，固定分页尺寸，更新计数、空态与可访问性文案。

3. `console/src/pages/Monitor/CronBatchDispatch/index.module.less`
   - 移除 Batch 列表内部滚动；用四行固定布局、紧凑间距和更清晰的状态进度组合改善窄屏展示。

## 验证

- `& .\.venv\Scripts\python.exe -m pytest tests/unit/monitor/test_cron_dispatch_monitor.py -q`
- `& .\console\node_modules\.bin\vitest.cmd run console/src/pages/Monitor/CronBatchDispatch/index.test.tsx`（按 console 工作目录调整路径）
- 前端 typecheck/lint 或构建中的可用定向命令。
- GitNexus `detect_changes(scope="all")`，确认仅影响预期 Batch 查询与页面符号。

## 补充：显示定时任务名称

- `swe_cron_dispatch_batches.parent_job_id` 关联
  `swe_cron_jobs.id`，由查询层返回 `parent_job_name`。
- Batch 列表首行和详情标题显示 `parent_job_name`，不再把外部任务 ID
  或父任务 ID 当作任务名称。
- 无法关联的任务统一显示“未命名定时任务”，下方仍保留 ID
  供排障。
- 全局筛选同时匹配定时任务名称。
- 后端测试覆盖联表、名称映射和名称搜索；前端测试覆盖列表及详情标题。
