# 专家分发接口修复与依赖交付

状态：用户已确认完整范围，已实现并验证，2026-10-26。

## 已明确的目标

1. 修复专家分发 HTTP 接口读取不存在请求字段而失败的问题。
2. 分发专家时，其绑定的 Skill 与 MCP 必须作为专家私有依赖一并交付，不注册为接收方普通资源。
3. 交付使用已发布社区专家版本中的冻结依赖；源资源变更后须重新发布专家再分发。

用户确认：Q1 A、Q2 A。此选择沿用 ADR 0028 及现有领域词汇，不新增同义术语或重复 ADR。

## 当前事实

- `ExpertDistributionRequest` 声明 `target_type/target_values`。分发路由记录日志时却读取 `target_tenant_ids/overwrite`，在 service 调用前触发 AttributeError。
- 现有接口测试 `tests/unit/market/test_experts_market.py::test_distribution_and_recall_require_manager` 已复现此故障。请求与 Console 调用契约一致，修复应从路由的错误字段引用着手。
- `publish_expert_from_profile()` 在发布时收集专家显式声明的 Skill/MCP，并保存到社区版本包。
- `_stage_expert_install()` 已将版本包中的 `skills/` 与 `mcp/` 复制到接收专家的 `<definition-id>.dependencies/`，而非接收方普通 Skill/MCP 注册区。
- `distribute_expert()` 调用同一安装路径，目标为用户 Default Agent Profile；用户主动接收可指定 Profile。
- CONTEXT.md 的 Community Expert Version Snapshot、Session-scoped Expert Dependency View、Expert Private Dependency Directory，以及 ADR 0028，已定义发布版本冻结和私有依赖边界。

参考：

- [ADR 0028](../../adr/0028-community-experts-use-frozen-private-dependencies.md)
- [当前实现分析，第 14 节](../../../analysis/subagent-current-implementation-report.md)
- `market/src/market/app/routers/experts_market.py:226`
- `market/src/market/marketplace/schemas.py:96`
- `market/src/market/marketplace/service.py:2164`、`:2680`、`:2818`

## 已确认决策及沿用的边界

```text
修复专家分发及交付绑定依赖
├── HTTP 契约：保留当前 target_type/target_values，修正错误字段引用
├── 依赖交付范围：专家私有依赖（用户已确认）
├── 版本来源：已发布版本的冻结依赖（用户已确认）
└── 沿用现有语义，不扩展产品范围
    ├── 管理员分发到目标用户 Default Agent Profile
    ├── 普通 Skill/MCP 同名资源互不覆盖
    ├── 同一社区专家更新保留启用状态，替换其定义与私有依赖
    └── 逐用户报告成功/失败，校验失败不交付缺依赖的专家
```

## 实施范围与验收场景

- 管理员合法分发请求能够进入 service 并返回逐用户结果；非管理员继续被拒绝。
- 无依赖的目标用户收到专家与其 Skill/MCP 后，能在选定专家执行中加载依赖。
- 校验复制的是完整资源内容和 MCP 配置，而非仅声明名称。
- 接收方即使没有同名普通资源，也能从私有依赖目录加载；若有同名普通资源，其内容和配置不被覆盖。
- 发布后修改源 Skill/MCP，但不重新发布，分发仍收到已发布版本；重新发布后分发收到新版本。
- 更新已有接收专家时，定义、Skill 和 MCP 内容对应同一社区版本，保留原启用状态。
- 绑定依赖缺失/损坏或交付失败时报告该目标失败，已有定义与依赖保留；其他目标按现有逐用户处理继续。
- 优先复用现有安装/快照实现，补足缺失回归；仅在测试证明存在缺口时调整依赖复制逻辑。

本轮不改变分发请求/响应契约，不引入普通 Skill/MCP 安装、分发时实时取源依赖、跨 source 分发或运行中任务切换版本。

## 实现与验证结果

生产代码仅修正分发路由的日志参数为 `target_type/target_values`。专家私有依赖交付复用现有发布、安装与运行快照链路，没有另建复制机制。

新增回归覆盖三类分发目标的请求转发、HTTP 到实际 service 的私有依赖交付、Skill 嵌套文件、MCP env/headers、同名普通资源隔离、发布快照冻结、重新发布后的双依赖更新与禁用保持，以及单用户复制失败后旧内容保留和其他用户继续。

相关 pytest 共 58 项通过；三个修改 Python 文件的 pre-commit 全部通过。服务文件测试在 fixture 中模拟远端 Agent reload，未验证真实 reload、LLM 或 MCP 服务连通性。

具体执行与验证命令见 [实施计划](../plans/2026-10-26-expert-distribution-dependencies.md)。领域定义沿用 CONTEXT.md 和 ADR 0028，无新增 ADR。
