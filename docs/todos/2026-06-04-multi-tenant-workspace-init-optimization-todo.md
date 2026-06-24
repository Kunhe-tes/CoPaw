# Multi-Tenant Workspace Init Optimization TODO

## Goal
记录多租户工作区初始化链路的性能优化待办，优先减少每次请求的固定开销，并确认哪些对象需要长期复用、哪些对象可以保持请求级创建。

## Current Understanding
- `TenantWorkspacePool` 和 `MultiAgentManager` 是进程级容器，启动时初始化一次。
- `Workspace` runtime 按 `tenant_id:agent_id` 缓存，不是每轮对话都重建。
- 每个请求仍会执行 `ensure_bootstrap()` fast path 检查。
- 每轮 query 仍会重建 `SWEAgent`、toolkit、skills 注册、system prompt、model/formatter、MCP clients。

## TODO

### Phase 1: Add Measurements
- [x] 在 `src/swe/app/middleware/tenant_workspace.py` 记录 `ensure_bootstrap()` 总耗时。
- [x] 在 `src/swe/app/workspace/tenant_pool.py` 区分记录 `bootstrap_fast_path_hit` 和 `bootstrap_fast_path_miss`。
- [x] 在 `src/swe/app/multi_agent_manager.py` 记录 `workspace_cache_hit` 和 `workspace_cache_miss`。
- [x] 在 `src/swe/app/runner/runner.py` 记录 `SWEAgent` 构建耗时。
- [x] 在 `src/swe/app/runner/runner.py` 记录 MCP client connect 耗时。
- [x] 在 `src/swe/agents/model_factory.py` 记录 `create_model_and_formatter()` 耗时。
- [ ] 补一组压测或最小基准，区分首请求和热请求。

### Phase 2: Optimize Bootstrap Fast Path
- [ ] 给 `TenantWorkspaceEntry` 增加内存态 bootstrap 完整性标记。
- [ ] 首次 bootstrap 成功后直接写入该标记，后续热请求优先信任内存态。
- [ ] 仅在显式租户重载、脚手架修复、分发覆盖后失效该标记。
- [ ] 缩小 `TenantWorkspacePool._registry_lock` 持有范围，避免在锁内做磁盘检查。
- [ ] 为 fast path 命中、失效、自愈路径补测试。

### Phase 3: Reduce Per-Turn Rebuild Cost
- [ ] 梳理 `SWEAgent` 初始化流程里哪些步骤只依赖 `workspace/channel/source`，哪些依赖本轮请求。
- [ ] 评估缓存 `effective_skills`、skill-tool registry、system prompt 的可行性。
- [ ] 评估将可复用装配下沉到 `Workspace` 级缓存的方案。
- [ ] 评估 MCP client 长连接复用或连接池方案。
- [ ] 评估 model/formatter 复用方案，重点确认是否会引入会话串扰或租户串扰。

### Phase 4: Guardrails And Verification
- [ ] 明确“绝不缓存整个带请求上下文的 `SWEAgent` 实例”这一边界。
- [ ] 为多租户隔离、source scope、agent scope 补回归测试。
- [ ] 对比优化前后的首请求耗时、热请求耗时、文件系统访问次数。
- [ ] 输出最终结论：哪些对象保留请求级创建，哪些对象提升为进程级或 workspace 级缓存。

## Expected Deliverables
- 一组可观测性埋点和基准数据
- `ensure_bootstrap()` fast path 优化
- 请求级对象重建成本分析结论
- 一份最终优化前后对比报告

## Priority
1. Phase 1: Add Measurements
2. Phase 2: Optimize Bootstrap Fast Path
3. Phase 4: Guardrails And Verification
4. Phase 3: Reduce Per-Turn Rebuild Cost

## Notes
- 第一优先级不是直接做大缓存，而是先量化热路径瓶颈。
- `Workspace` 已有缓存，当前最值得先动的是 `ensure_bootstrap()` 每请求磁盘检查。
- `SWEAgent` / model / MCP 复用的收益可能更高，但需要在隔离边界验证清楚后再动。
