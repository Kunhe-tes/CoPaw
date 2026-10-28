---
title: feat 按来源异步补跑当日失败定时任务
type: feat
status: completed
date: 2026-10-27
origin: docs/brainstorms/2026-10-27-cron-daily-failure-rerun-requirements.md
---

# 按来源异步补跑当日失败任务

## Summary

以一张持久调用表驱动分页扫描，逐项复核后复用新版执行队列。处理明细复用已有执行事件表，SWE 在实际执行时透传补跑标记、维护同链历史和状态，不另建执行结果系统。

## Requirements

完整覆盖 origin 的 R1–R20、F1–F2、AE1–AE12。沿用用户确认的无鉴权入口、指定来源、北京时间实际失败日、最新调度/补跑尝试、无限次数、原通知时点、持久恢复及同链最终历史约束。

## Scope Boundaries

不合入旧 16 个提交，不自动注册平台任务、不改前端/旧接口、不增加认证或限流配置，不自动执行 DDL。数据库与外部平台的实际联调不以单元测试代替。

## Context & Research

- `managed/executions.py` 已有确定性执行身份、定义快照及队列入库。
- `managed/batch_retry.py` 已有父定义→回执→目标定义→执行→成员的锁顺序。
- `managed/recovery.py` 已有独立恢复工作域，新增工作域不能阻断已有派发。
- `managed/storage.py` 保证事务连接一致；`managed/dispatch_events.py` 已有事件表及唯一键。
- `src/swe/app/crons/managed_results.py` 已有运行态、历史事务和批重试最终历史更新；当前只支持批历史替换，普通补跑需定向扩展。
- `src/swe/app/crons/managed_history.py` 的历史 meta 是受限结构，需显式透传补跑标记，并保留必需执行身份。
- 当前分支没有批自动重试服务。按既有行为常量（三次原生业务尝试）及成员指针识别其结束；自动重试仍有资格时不抢跑。无法确认关系时跳过并审计，不迁入自动重试服务。
- 持久队列、租约、事件和事务已有直接模式，主要采用本地代码证据；GitNexus WAL 异常无法提供可信图谱，按调用点核对。遵照用户约定顺序实现/自检，不启用子代理，也不把自检称为独立审查。

## Key Technical Decisions

- POST `/api/scheduler/cron/failure-reruns`，Body 只含 `source_id`，202 返回调用记录；GET `/api/scheduler/cron/failure-reruns/{call_id}` 按同来源查询扫描计数及分页处理明细/当前执行事实。调用 ID 由服务生成，不依赖平台 Header。
- 新表 `swe_cron_failure_retry_calls` 保存日期、UTC 窗口、受理时队列高水位、扫描游标、计数、租约及版本。每个正常受理请求一行；不存在逐项明细新表。
- 执行事件使用调用 ID 的固定前缀作为事件唯一键范围，复用现有唯一索引做明细分页。每个候选的入队、审计、游标/计数在同一事务提交，恢复不会漏项或重放。
- 候选分页按受理高水位固定；按完整身份、协议及非 manual 执行的登记顺序判断最新尝试。实际处理时再次读取最新事实，避免覆盖受理后的成功/在途工作。
- 排除认证过期与两个已确认错误文本；失联/派发未确认不视为明确失败。批成员同时复核当前指针、清单身份及原生重试是否仍有资格，父/子只处理自身。
- 单次原失败的补跑身份确定且与调用 ID 无关；多次调用可以各自有记录，但只能对同一原失败受理一次。新补跑失败后拥有新的执行身份，允许下一轮再次受理。
- Agent 模型解析在持有调用/业务行锁之前完成；入事务后复核定义版本。现有执行入库增加可选的已解析模型参数，不改变旧调用方行为，避免批量扫描持锁等待 HTTP。
- `daily_failure_retry` 元数据包含调用 ID、根执行、上次失败、独立补跑次数及冻结的通知目标。业务定义用最新，逻辑执行轮次和原通知时点保留；批成员指针/业务尝试按原规则更新。
- SWE 开始前只对带此标记的执行检查更新调度成功；跳过陈旧补跑，不中断已开始执行。历史新增与上次同链历史置非最终在同一事务完成；只扩展本功能，不改变普通周期和人工旧路径语义。
- 调用的 completed 表示扫描处理结束，不代表全部业务完成。SQL 未部署时仅新接口不可用，新恢复域应退避诊断，不影响原有队列。

## Implementation Units

### U1. 持久调用表与审计仓库

**Requirements:** R1–R5、R18–R20；A1–A3、F1。
**Dependencies:** 无。
**Files:** `scripts/sql/cron_daily_failure_retry.sql`；新增 `managed/daily_retry_store.py`、`managed/daily_retry_policy.py`；测试 `tests/unit/scheduler/test_daily_failure_retry_store.py`、`tests/fakes/daily_failure_retry.py`。
**Approach:** 中文表/列 comment 的手工 DDL；调用窗口/高水位、租约 fencing、事务计数与已有事件明细。仓库不执行建表。
**Execution note:** 测试先行，使用现有 SQLite 事务适配执行真实查询。
**Test scenarios:** Covers AE1/AE2/AE8/AE12：合法/非法来源、北京时间午夜、无候选、两个调用租约竞争、过期持有者不能推进、恢复游标、事件唯一键及分页来源隔离、缺表错误不变假成功。
**Verification:** 调用行/事件/计数可由真实 SQL 核验；DDL 不进入启动建表逻辑。

### U2. 候选筛选与逐项补跑受理

**Requirements:** R5–R12、R19；F1、F2。
**Dependencies:** U1。
**Files:** 新增 `managed/daily_retry_scan.py`、`managed/daily_retry_service.py`、`managed/daily_retry_enqueue.py`；修改 `managed/executions.py`；测试 `tests/unit/scheduler/test_daily_failure_retry.py`。
**Approach:** 失败时间分页、最新记录/在途/定义复核、原生批最终失败检查、共同排除规则、原失败确定性去重、最新定义快照及通知目标保存。事务遵循原锁顺序；模型网络读取在事务外。
**Test scenarios:** Covers AE2–AE8：旧失败被成功/在途覆盖、manual 不参与、跨天、补跑超过三次、黑名单大小写、普通/批父/批子、原生批重试中间失败、仅关闭批入口、停用/删除、配置已修改、多实例重复处理、单项故障回滚后继续。
**Verification:** 原定义/平台定时器不变；每个原失败只有一个补跑，原生重试与新接口计数不混用。

### U3. SWE 执行前检查、历史落标与最终记录

**Requirements:** R13–R17；A4、F2。
**Dependencies:** U1 的元数据契约。
**Files:** 新增 `src/swe/app/crons/managed_daily_retry.py`；修改 `managed_results.py`、`managed_history.py`；测试 `tests/unit/app/test_managed_daily_retry.py`。
**Approach:** 仅对本功能标记生效，保留旧路径；检查更新调度成功、透传历史标记、普通与批同链旧历史原子置 0、保留通知时点。既有状态写入及并发保护不旁路。
**Test scenarios:** Covers AE9–AE11：入队不伪造历史、失败/成功新历史、其他身份/周期不受影响、异常回滚、新成功使未开始补跑跳过、manual 成功不影响、已开始不中断、通知目标未到/已过、未读/旧结果保护、异步主成功不是整轮成功。
**Verification:** 新运行→新历史→state→原历史 is_final 全链在数据库中可核对。

### U4. 无 Header 接口、恢复域与运维交付

**Requirements:** R1–R4、R18–R20；A1–A4、F1。
**Dependencies:** U1、U2。
**Files:** 新增 `routers/daily_failure_retry.py`，修改 `routers/__init__.py`、`managed/recovery.py`、`managed/storage.py`；新增 `docs/integrations/cron-daily-failure-rerun.md`；测试 `tests/unit/scheduler/test_daily_failure_retry_api.py`、`test_daily_failure_retry_runtime.py`。
**Approach:** 严格 Body、持久受理、独立恢复 lane、源过滤查询和可定位脱敏错误日志；新增表不就绪时仅新功能失败。文档给出中文 SQL、Postman 请求、进度/状态验收及无鉴权暴露面。
**Test scenarios:** Covers AE1/AE8/AE12：无 Header、额外字段拒绝、202/404/422/503、参数/DB 异常可定位、不消费后台执行结果冒充同步成功、worker 重启接续及异常域隔离。
**Verification:** API/后台/SQL/SWE 集成测试通过，既有 Scheduler/SWE 执行相关回归及复杂度检查通过。未连接行内数据库时明确列出该验证限制。

## System-Wide Impact

外部平台只负责触发和配置频率。Scheduler 负责调用状态和受理；SWE 负责真实业务状态及结果。三者通过已有共库身份关联；不新增回执链。新表没有部署不能接受新补跑，但不关闭正常任务恢复和派发。Monitor 继续读取原表，不新增看板。

## Risks and Verification

- 无鉴权是用户确认的行为，不能宣称来源筛选防止越权触发。
- 同一执行链可能跨日无限补跑；排除规则、任务暂停和成功覆盖依旧必须生效。
- 行锁、模型网络解析和租约恢复须测试取消/异常路径，防止批量扫描放大锁等待。
- 需求中的所有 AE 与条件行为均应有相应测试；不得用少数 happy path 宣称全部完成。代码注释/文档采用既有中文约定，普通函数复杂度不超过 15。

## Sources & References

- Origin: `docs/brainstorms/2026-10-27-cron-daily-failure-rerun-requirements.md`。
- 代码模式：`scheduler/src/scheduler/app/services/cron/managed/`、`src/swe/app/crons/managed_results.py`、`tests/unit/scheduler/test_managed_cron_executions.py`。

## Execution Posture

用户已明确“完成设计直接开始开发和测试”，不再等待计划菜单。按仓库约定主线程顺序测试先行、自检，不启动子代理；未运行独立子代理审查。不自动提交、推送或执行外部数据库 DDL。
