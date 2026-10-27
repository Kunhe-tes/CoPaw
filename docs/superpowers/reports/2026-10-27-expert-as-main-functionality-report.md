# Expert-as-Main 功能完成报告

日期：2026-10-27。依据已确认的 Q1–Q26、Q16a/Q16b、ADR 0042 与实施计划。基线：`9873823c42d83e0e68304cba965bba6edcc13664`；实施分支：`feat/expert-as-main`，位于 `.worktrees/expert-as-main`。

## 功能范围

Source 管理员可在系统配置开启“所选专家作为主 Agent”（`feature_switches.expert_as_main_enabled`），缺省关闭。关闭时保留既有单条消息选择专家、通过 SubAgent 执行再由 Main Agent 汇总的路径，与自主专家发现开关相互独立。

开启后，普通 Chat 选择专家会立即保存精确 ID 绑定，刷新及重新读取仓储后恢复；下一条消息直接由专家流式回复并保存启动时身份，不创建该次执行的 SubAgent 监控记录或默认 Agent 二次总结。切换专家或默认 Agent 立即保存，只影响后续消息。正文提及专家不建立绑定。

绑定使用服务端修订与 JSON 仓储锁内 CAS，普通 Chat 更新不能覆盖该字段。旧页面提交返回 409、同步最新绑定，并保留文本与附件引用供手动重发；不会自动重试。进入 Plan/Goal、`/new`/`/clear` 解除绑定，`/compact` 保留。Source 关闭后在下次进入或发送时解除，重新开启不自动恢复旧绑定。

每条消息使用最新有效本地专家配置及私有 Skill/MCP 的一致快照；在途消息与审批续接保留原身份、资源和预算。禁用、删除、撤回或依赖校验失败会阻止执行并保留不可用身份，同一个 ID 恢复后可再次发送，同名重建的不同 ID 不能接替。

专家角色替代 Profile 角色，保留平台、安全、环境和 Source 公共约束。能力取专家与父策略交集，不继承未声明资源，也不能继续委派。可用专家模型优先，否则使用聊天模型；预算逐消息计算，逐维取专家和适用 Main 全局限制的更严格值，内部重试与审批续接不重置。停止、失败或超限保留绑定并输出终止原因。

当前 Chat 的历史、summary、checkpoint 和自动压缩可以继续使用；单独的 Chat memory facade 不开放 Profile 长期记忆检索或 summary 写入。人工审批与停止沿用主聊天交互。

## 审查与收敛

独立审查覆盖 Source 开关、绑定原子性、快照一致性、运行时、前端和实际浏览器交互。已据此修复 Bootstrap 角色泄漏、历史恢复覆盖当前角色、推理预算重复计数、异步清理与准备任务取消竞态、Source 关闭时并发删除、模式切换保存竞态、恢复交互参数污染和首条消息冲突时的可见草稿恢复。具体回归节点与浏览器结果见测试及覆盖报告。

GitNexus 对共享 Runner/命令/Guard 路径报告 HIGH/CRITICAL，已在修改前告知并核对源码调用面。索引部分新增符号及重复 UID 无法可靠解析，UNKNOWN 不视为安全；专项测试与独立复核补足，未声称完整静态分析覆盖。

## 交付与边界

- 代码在独立 feature worktree 中按配置（`0a1f18390`）、绑定（`1a30ed216`）、快照（`b785d529f`）、执行链（`6d9258a3b`）、前端（`52e1ed45b`）及文档拆分提交；原主工作区既有修改不纳入本功能。未推送、未创建 PR、未自动合并到原脏工作区。最终提交清单由 `git log 9873823c4..feat/expert-as-main --oneline` 查看。
- Chat 绑定持久化；pending 专家审批执行 lease 为进程内状态。服务重启或请求落到缺少原 lease 的 worker 时返回 409，提示重新发起任务，不用最新配置重放旧工具。真实分布式审批恢复未实现。
- 本地两独立 Python 进程验证 CAS；尚未完成 Kubernetes 多副本、Linux 3.15、共享 NAS 锁、MySQL/Redis 真实部署验收。
- 浏览器使用隔离 Chromium、Vite 和 API mock；未调用真实收费模型、真实网络工具或社区分发服务。报告不代表生产端到端验收。
- 既有命令 memory 创建和共享 MemoryCompactionHook 的配置读取仍有同步 I/O，本次未扩大为通用事件循环重构。

配套材料：[测试报告](2026-10-27-expert-as-main-test-report.md)、[决策覆盖矩阵](2026-10-27-expert-as-main-coverage.md)、[浏览器验证](2026-10-27-expert-as-main-browser-validation.md)。
