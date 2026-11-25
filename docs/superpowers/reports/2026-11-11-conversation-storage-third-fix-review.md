# 会话迁移与 CRUD 第三轮修复复核

日期：2026-11-11。源码固定：`703de41fcbf8f5b1ceec88aeac14343f246c2ab2`。
主代理与三个子代理实际阅读历史查询、内部写入调用方、迁移及恢复生命周期。历史正文生成新 bundle 是正确目标。本轮仅新增报告；保留用户已有 runbook 未提交修改，未改实现或操作现场数据。

## 结论

上一轮三项具体遗漏在最新提交中均已修复。但继续枚举内部调用方后，确认 **Runner finally 清理仍无条件保存长时间持有的完整 Chat，能够覆盖问答期间已经提交的新元数据**。因此整个 CRUD 仍不能判为正确完备。

不能以静态审计或若干测试通过给出全系统“100% 正确”保证；当前更有明确的剩余反例。以下区分已关闭的具体交错与尚未闭环的通用写入契约。

## 最新修复复核

| 上轮问题 | 代码机制与结论 |
| --- | --- |
| 共享 Session compact/prune 后 B 在途读取返回旧消息 | `history.py:354` 对 snapshot 所有非 archive occurrence 批量重查 current_visible/deleted_at，并比较完整 ID 集合；`collection_queries.py:75` 同时限定 service/Session。detail、tracing、answer-turn 都经过 `_assemble` 的读前及返回前检查。reset epoch 检查仍保留。原交错关闭 |
| batch-delete 缺授权快照 | `runner/api.py:1479` 收集 expected_chats，贯穿 manager/repository 锁内 ownership 校验；冲突返回 409。原批量 ownership 转移交错关闭 |
| 自动标题完整旧 spec 覆盖新 meta | `runner/manager.py:478` 修改前深拷贝 expected_chat，条件更新方法存在时使用 update_chat_if_unchanged；SQL repository 既有 expected 比较与最终 revision CAS 共同保护。原自动标题交错关闭 |

路径除特别注明外相对于 `src/swe/app/conversation_storage/`。

## U1 — P2：Runner 清理保存旧完整 Chat，覆盖运行期间的新元数据

这是与此前陈旧整对象写入相同的根因，但位于另一个正常执行入口；不是否认自动标题和 HTTP patch 的具体修复。

实际调用链：

1. `runner/query_runtime.py:446/451` 构造 runtime 时保存当时的 resources.chat。
2. 模型/工具执行期间，HTTP patch 可以更新同一 Chat 的轻量 metadata；同 Session 活动 Turn 不禁止此类属性更新，禁止 busy rebind 与此不同。
3. `runner/query_attempt.py:1175` 外层 finally 无条件调用 `_cleanup_query_resources`；`runner/runner.py:6193` 转给 query_cleanup。
4. `runner/query_cleanup.py:276` 调用 update_chat_during_cleanup；`:154` 执行 `owner._chat_manager.update_chat(runtime.chat)`，没有 expected_chat，也不是字段 patch。
5. `runner/manager.py:420/443` 只有传 expected_chat 才比较并调用条件更新；此入口跳到 `:448` 的 update(spec)。repository `chat_repository.py:816` 又读取当前数据库行及最新 metadata_revision，最终 `chat_mutations.py:316` 将传入旧 spec 的完整 metadata_text 写回。

可达顺序：运行开始时 runtime.chat.meta 的 plan_mode_enabled=false；用户在问答期间通过 HTTP 成功提交 true；问答结束，cleanup 用旧 runtime.chat 保存 false。repository 取得的是新 revision，CAS 可以成功，true 被覆盖。**同一进程也能发生**：manager 锁只覆盖每次方法调用，不覆盖整轮运行；不需要多 Pod。

`_should_keep_generated_title` 只提供标题特例；即使触发 `_keep_generated_title`，合并顺序也是旧 incoming meta 覆盖已有同名字段，不能保护 plan/goal 等属性。被覆盖的设置已经收到成功响应，影响后续会话行为；不是仅 updated_at 的显示差异。

建议先明确 cleanup 的必要写入意图：若仅更新最近使用时间，应在锁定当前行上更新该字段；若有其他字段，应以显式 patch 合并当前值。若仍保存完整对象，则必须保存原读取版本并条件提交，妥善处理冲突，不能只重新读取新 revision 配给旧对象。

回归须覆盖“真实 Runner runtime 建立 → HTTP 修改已提交 → finally cleanup”交错，验证新字段保持；仅测自动标题方法或条件更新 helper 不能证明该链路安全。

## 内部更新调用方仍需统一契约

本轮枚举到以下无 expected 的整对象写入点。它们证明风险面不止标题；除 U1 的完整可达链外，不将每个点机械当成独立 bug。

| 入口 | 源码位置 | 检视建议 |
| --- | --- | --- |
| 正常/blocked runtime 清理 | `runner/query_cleanup.py:154/44` | 正常 finally 已确证 U1；blocked 分支也应按实际字段意图处理 |
| 请求 Chat 补 agent identity、请求模式更新、Goal delegation | `runner/runner.py:3901/3930/4195` | 不应把局部字段意图扩成无条件完整对象替换 |
| W+ proposal/会话投影 | `wplus_sop/service.py:1351/1481` | 投影字段与其他 metadata 需要事务内合并或条件版本，不应以业务 outbox 成功代替 Chat 并发检查 |
| 已有会话自动注册时合并 meta | `runner/manager.py:295` | get 后 upsert(existing) 在多实例中仍须处理旧快照 |
| Goal 创建后清 delegation、Console proposal、Cron 元数据 | `goals/router.py:158`、`routers/console.py:2092`、`crons/manager.py:1936`、`crons/managed_resources.py:82` | 子代理枚举的其他默认无 expected 调用，尚未逐个证明业务交错；应纳入统一契约治理 |

建议统一审查 manager/repository 的“替换完整对象”和“更新指定字段”契约，而不是每轮只给一个调用方补 expected 参数。保留可信系统清理按 ID 删除与外部授权删除的区别，不将所有内部无 expected 调用都归为越权。

## 读取专项新增覆盖

| 范围 | 代码推导结论 |
| --- | --- |
| 可见性检查分批 | collection runner 按 packet/键数分批，汇总全部 ID，超预算显式失败；不只检查首批 |
| detail/tracing/answer-turn | 均进入 `_assemble` 读前/返回前重验；typed Turn、问题 occurrence 及 scope/user/channel/session 关联检查存在 |
| archive_page | HMAC cursor 绑定 scope/Chat/epoch/high，固定 high keyset；独立 Chat 归档不随另一 Chat 在线 prune 获得其归档 |
| checkpoint | 捕获 epoch/revision/active pointer/high，读后重新核对，范围连续与数量精确，超预算失败而非静默截断 |
| Chat 删除/重绑 | snapshot 的 Chat identity、版本及 locator 变化被拒绝；授权回调在 hydration 后及返回前执行 |

本轮读取专项未确认新的确定性缺陷。返回前重验提供有效性检查点，不承诺响应发出后数据库永不变化。

## 迁移专项新增覆盖

| 范围 | 本轮实际代码与判断 |
| --- | --- |
| discovery 覆盖 | `migration/discovery.py:202/348` 同时核对 config profiles、Agent ID、agent.json，并扫描 source_root 中未登记的 agent.json/chats.json/sessions/dialog；未知候选阻断而非忽略 |
| 分享来源 | `discovery.py:397` 保留八字段、验证 snapshot_key 与正文模型，要求 snapshot 在服务集合中唯一匹配，缺失/多服务歧义阻断 |
| discovery ready | `discovery.py:543` 校验唯一 scope、NAS 与源/配置/分享根不重叠，再合并实际语义 inventory blockers |
| 稳定票据和续跑 | `journal.py:70/116/217` 拒绝其他作业/未知业务行，按 migration_id/kind/source_key 复用 target ID、operation、scope/path；SQL 状态是权威，本地文件为镜像 |
| 完成边界 | `conversation_storage_v3_cmd.py:213` 固定 named lock/连接 UUID，执行后再次比较 inventory、原分享集合与 schema baseline；finalize 正式 verify 后 ready，再落同一 authority receipt |
| 冻结检查 | `inventory_v3.py:245` 同时建立 workspace/分享的 service/tenant 同步起点并重读源；mtime 不独立证明保留时间戳的任意源替换，因此停写冻结仍必需 |

已读正常固定源迁移链未确认新确定性缺陷；不能据此替代整个 CRUD 的审计结论。

## 验证与边界

定向回归：`test_history.py`、`test_chat_repository.py`、`tests/unit/app/test_chat_api_update.py`、`test_chat_manager_agent_metadata.py`：**63 passed，0 failed，0.91 秒**。U1 由上述调用链与交错推导，不以这些测试通过为正确性证明。

未连接生产 MySQL/TDSQL、业务 NAS 或 Kubernetes；未穷举任意旧格式损坏组合和所有外部调用者。此前的 retained_history 释放能力、HA 身份重绑定及部署恢复、源冻结与存储耐久假设仍是边界。当前报告不足以授权生产放行，也不宣称全系统正确。
