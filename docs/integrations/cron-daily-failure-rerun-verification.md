# 当日失败补跑：需求与验证核对

对应需求：`docs/brainstorms/2026-10-27-cron-daily-failure-rerun-requirements.md`。
对应计划：`docs/plans/2026-10-27-001-feat-daily-failure-rerun-plan.md`。

## 需求覆盖

| 需求 | 实现位置 | 主要验证 |
| --- | --- | --- |
| R1–R4：来源入口、异步调用记录、无额外访问限制 | daily_failure_retry 路由、daily_retry_store | 无 Header 的 202、独立调用 ID、严格来源、参数拒绝、缺表 503、脱敏日志 |
| R5：北京时间实际失败窗口与固定截止 | daily_retry_policy、daily_retry_scan | 日窗口、队列高水位、异步最终失败确认日、受理后失败留后续调用 |
| R6：只看最新自动执行，manual 不参与 | daily_retry_scan | 新成功/排队挡住旧失败、手动成功不掩盖、事务复核来源和协议 |
| R7：只补最终失败批成员 | daily_retry_enqueue、daily_retry_scan | 原生第 1/2 次跳过、第 3 次受理；批父/批子只补自身、不创建新批回执 |
| R8–R9：排除错误与执行条件 | daily_retry_policy、daily_retry_scan | 三个错误文本、认证过期、失联未知、停用/删除/未读暂停/管理未就绪；仅批入口暂停允许补跑 |
| R10：独立无限补跑、跨日 | daily_retry_enqueue | 普通与批成员均验证超过三次后继续，根执行和独立次数保留，跨日按新失败确认时间扫描 |
| R11–R12：最新定义、原身份、并发去重 | ExecutionStore、daily_retry_service | 最新定义快照、入队不伪造历史/state、并发两个调用只产生一条对应新执行、模型解析不持业务事务锁 |
| R13–R15：新历史、state、原子最终标识 | managed_daily_retry、managed_history、ExecutionWriter | 新历史落标、普通/批同链 is_final 0/1、其他周期不动、错误时整体回滚、较旧完成不覆盖新结果 |
| R16：异步整轮与执行前失效 | managed_daily_retry、ExecutionSettlement | 主成功异步未确认不补、最终失败才补、新调度成功使待执行补跑跳过、已开始不打断 |
| R17：原通知、报告/未读/自动暂停 | managed_history、原 SWE 结果链 | 原通知时点前/后均保持目标时间、成功未读、阈值暂停；既有报告/通知回归 |
| R18：扫描进度与实际业务结果区分 | daily_retry_audit、GET 路由 | completed 时新执行仍 queued、事件分页、实时执行与 settled 状态分开返回 |
| R19：逐项失败与持久恢复 | daily_retry_service、daily_retry_store、ManagedRecoveryWorker | 单项回滚后续项继续、扫描级故障记录与退避、分页重启恢复、旧租约不能提交、缺表不阻断旧工作域 |
| R20：一张新表、手工 SQL、原分支隔离 | scripts/sql 两份 SQL、现有运行/事件/历史/state 表 | 不改历史列、不自动 DDL、不合入旧 16 个本地提交、不新增前端或结果回执接口 |

实现核对覆盖 U1–U4、F1–F2、AE1–AE12。测试位于 `tests/unit/scheduler/test_daily_failure_retry*.py`、`tests/unit/app/test_managed_daily_retry.py`；使用真实管理/入队/SWE 历史服务和 SQLite 事务适配，只替换外部平台/模型边界。

## 自检中已处理的问题

- 部分受理失败没有调用级错误码：补充 items_failed，调用 completed_with_errors；单项插入和游标保持同事务。
- 扫描整页故障只能等租约超时：补充持久 scan_failed、60 秒退避和原游标恢复；数据库本身不可用时仍靠租约恢复。
- 候选仅依赖首次 SQL 来源过滤：锁内再次复核来源、入口类型及协议。
- 当日两种失败时间的 OR 查询：改为两支索引查询各取有界页再归并，单独提供手工索引 SQL。
- 原跨租户历史测试漏掉模型查询替身：已在 HEAD 原入库代码上复现相同配置错误；只补测试替身，未放宽身份断言或修改生产解析逻辑。

本次遵照仓库要求由主线程顺序自检，没有运行独立多代理评审；GitNexus 因本地 LadybugDB WAL 异常无法读取，未删除 WAL，改为源码调用点核对。

## 验证边界

- 2026-10-27 最终回归：全部 Scheduler 单元测试与 SWE `test_managed*.py` 共 718 项通过；其中本功能新增 50 项。全部本次 Python 路径的本地 pre-commit 通过，包含复杂度上限 15、mypy、black、flake8、pylint 与密钥检查。
- 本地 pytest 和 pre-commit 覆盖后端链路；不声称已完成行内验收。
- 首次扩大到整个 app 测试目录时，收集被缺失的 `skills/wplus-sop-miner/scripts/validate_stage_sop.py` 阻断；后续明确选择全部 Scheduler 测试与 SWE managed 执行测试。
- SQLite 适配存在 Python 3.12 datetime adapter 弃用警告，不是业务失败。
- 未连接行内 MySQL，未执行建表/建索引，未验证真实 MySQL 行锁和 EXPLAIN；未调用真实外部平台、模型或通知渠道。
- 预发布部署顺序、Postman 和只读 SQL 验证步骤见 `docs/integrations/cron-daily-failure-rerun.md`。
