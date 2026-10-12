# Swe Playbook

`analysis/playbook/` 用于沉淀重复问题的处理经验，重点记录报错样式、定位入口、日志入口和排查顺序。

## 文档索引

| 文档 | 摘要 |
|------|------|
| [agent-config-read-consistency.md](agent-config-read-consistency.md) | agent 控制面读写一致性边界、排查入口和与 console agent switching 的职责分界 |
| [common-errors.md](common-errors.md) | 常见报错模式、典型触发点和第一落点 |
| [external-job-list.md](external-job-list.md) | 外部 jobs 列表的无初始化接口、原接口契约及任务绑定的只读边界 |
| [location-paths.md](location-paths.md) | 按问题类型给出代码、配置与命令入口，包含财富任务动态指标与经营分组 |
| [log-entrypoints.md](log-entrypoints.md) | 运行日志、daemon logs、query error dump、Tracing 的实际入口 |
| [my-mcp-manual-validation.md](my-mcp-manual-validation.md) | MyMCP 在本地环境下按用户、来源、应用和管理员身份进行手工验证的方法 |
| [performance-optimization-plan.md](performance-optimization-plan.md) | freshness 扫描优化与官方 MySQL 异步驱动迁移的方案表、风险和验收标准 |
| [python-memory-hotspots.md](python-memory-hotspots.md) | Python 后端前五内存热点、引用持有链、已有保护及运行时验证方法 |
| [skill-freshness-and-span-write-performance.md](skill-freshness-and-span-write-performance.md) | 技能递归 freshness 检查与 Tracing 批量写入的 CPU 成本、隔离基准及优化边界 |
| [skill-freshness-optimization-detail.md](skill-freshness-optimization-detail.md) | freshness 调用窗口、token 兼容性、锁优化、manifest 一致性及分阶段验收方案 |
| [tool-result-truncation.md](tool-result-truncation.md) | MCP / read_file 工具返回出现 `<<<TRUNCATED>>>` 时的截断点和临时调大配置 |
| [troubleshooting-order.md](troubleshooting-order.md) | 从复现、取证、收敛到验证的推荐顺序 |

## 使用建议

1. 先看 [troubleshooting-order.md](troubleshooting-order.md)，确定排查顺序。
2. 遇到明确错误消息时，再查 [common-errors.md](common-errors.md)。
3. 遇到 agent 控制面读写不一致时，先看 [agent-config-read-consistency.md](agent-config-read-consistency.md)。
4. 需要做 MyMCP 手工联调时，看 [my-mcp-manual-validation.md](my-mcp-manual-validation.md)。
5. 工具返回出现 `<<<TRUNCATED>>>` 时，看 [tool-result-truncation.md](tool-result-truncation.md)。
6. 需要找入口时，看 [location-paths.md](location-paths.md) 和 [log-entrypoints.md](log-entrypoints.md)。
