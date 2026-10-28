# SubAgent 功能完成报告

日期：2026-10-27。依据已确认 Q1–Q13 与设计稿实现，基线 `ab5d8ad12`。

## 完成行为

| 用户入口 | 可用能力 |
| --- | --- |
| 选择器明确指定专家 | 仅所选有效专家，不受发现开关影响；不可用时报错，无替代或临时回退 |
| 当前输入命中固定关键词或结构化启用，开关关闭 | 临时 run-scoped 定义与当前有效 Skill-owned 定义 |
| 上述意图且开关开启 | 再加入当前租户、当前 Profile 有效且已启用的专家 |
| 无新意图但有当前 Chat/session 保留运行 | 仅 get/wait/cancel |
| 无意图且无保留运行 | 不注册子代理工具 |

固定词为“子代理”“子智能体”“subagent”“sub-agent”，英文忽略大小写；字面命中只开放工具，不强制执行。普通“专家”不触发。临时定义不持久保存、不自动加载 Skill，继承父 Agent 已启用的内置工具与 MCP，继续服从权限和审批。

Source 系统配置页新增默认关闭的“允许自主选择我的专家”。隐藏专家既不展示也不按名解析。Skill-owned 生命周期独立。Plan 中继续只读，SubAgent、completion judge 和 Goal finalization 不获得委派工具。

本地专家沿用声明依赖与模型解析。社区专家按实际专家初始化 Chat 私有冻结视图，再生成运行快照；支持不同专家并发及同专家首次并发复用，父 context 和通用资源不污染。

管理工具每次访问按 Chat/session 校验；wait 不消耗其他 Chat 的终态结果。普通 Query 的保留记录扫描在 worker 完成。

Goal 初始意图跨澄清、提案、确认保存；后续真实 Steering 可提升授权，自动轮、恢复及重启继续有效。持久字段放现有 JSON，兼容旧记录，无数据库列迁移。存储层单调 OR 防止并发旧快照降级；Source 开关和目录每轮刷新。模式退出清理草拟授权，客户端和模型 Contract 不可伪造。

## 审查收敛

独立审查推动修复：Plan MCP 只读旁路、社区专家并发首次初始化、普通 Chat 同步扫描阻塞事件循环、Goal 授权并发写回降级、/plan 未退出草拟 Goal，以及服务端内部 meta 被前端回传触发 400。复审无剩余 P0/P1/P2 阻塞。GitNexus 对共享 Chat/Goal 接口报告 HIGH，已核对局部 diff、调用路径、类型与专项测试；当前图不含本工作树全部新增符号，未声称完整 PDG/taint 覆盖。

## 提交

- `20cbd6627`：术语、ADR 0041、设计与实施计划。
- `d4ca8466f`：意图门禁、专家目录、Source 开关与 Plan 权限。
- `343ee43c7`：Chat 运行隔离、专家依赖视图与并发修复。
- `740db02db`：Goal 持久授权、前端传递、原子保存及异步预读。

已快进合并到 `perf/event-loop-optimization`。重叠的 CONTEXT 与 Playbook 索引做了逐项合并，其他原有未提交文件按 SHA-256 验证保留；旧的未跟踪设计草稿在 `/private/tmp/subagent-intent-integration-backup/original-draft-design.md` 备份，当前路径为最终已确认稿。合并后 289 项后端专项与 116 项前端专项通过，TypeScript 通过。测试证据和限制见同目录测试报告。未推送远端或创建 PR。
