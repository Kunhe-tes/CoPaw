# 10: 完成组合场景验收与操作说明

**What to build:** 运维人员获得最终优化组合的正确性、故障恢复、预算及同环境性能对照结果，并能用原有两阶段流程安全执行。

**Blocked by:** 01 — 补齐迁移性能观测与可复现基线；02 — 消息批量写入与已提交记录批量核对；03 — 消息票据批量分配与安全续跑；04 — 扩展身份票据批量分配；05 — 收窄消息关联锁并实现集合加锁；06 — 安全复用 bundle 打开与索引解析；07 — 消除 source 注册与选择阶段的重复工作；08 — 失败 source 自动重审复用票据归属分析；09 — 减少完整 binding 与 manifest 镜像重复处理。

**Status:** claimed

- [ ] 使用现有 prepare → migrate 集成入口，在同冻结输入、worker/IO/资源预算与数据库环境下比较基线和最终实现，报告阶段墙钟、SQL、事务及 bundle IO。
- [ ] 覆盖多个小 source、单大 source、多 Session/Turn/Message、分享/归档/事件/checkpoint、大字段和跨块预算场景。
- [ ] 覆盖同租户坏 source 跳过、正常 source 独立发布、部分提交后重启续跑及已发布 source 持续新增数据的保护。
- [ ] 覆盖源新增/删除/修改/替换、危险路径、锁丢失、连接变化、共享 IO、磁盘耗尽、取消和 UnknownCommit，检查全局停止与 IO 排空。
- [ ] 真实 MySQL 验证批量身份和关联锁；本地目录及可控延迟验证 IO，明确未进行真实 NAS、万级或生产放行验收。
- [ ] 验证票据事务、INSERT、核对 SELECT 按块增长，单次多块读取索引只解析一次；数据和运行时读取语义全量一致。
- [ ] 运行会话存储与相关 CLI 全套回归、项目提交检查，汇总资源峰值、收益、回归风险和可独立回退范围。
- [ ] 更新操作说明和指标口径，保持 prepare/migrate 主要命令、退出语义、旧作业兼容及恢复要求，不承诺未经测量的耗时倍数。


## Progress

- Implementer branch `feat/migration-perf-10`, isolated worktree; latest integration (01–09) merged before reporting. No production logic changes in this ticket.
- `c5f52b4a1`: true same-tenant two-source prepare→migrate integration; centralized isolated MySQL **1 passed in 35.47 s**. Bad source stays closed; healthy sibling publishes/admitted by exact source. Original manifest repair preserves online rows/config/new Agent and never re-reads poisoned published old session input.
- `8bbfaacc9`: reports binding/manifest metrics in fixed harness, documents verified locks (2 passed/13.38 s), fault recovery (3 passed/108.24 s), operations/recovery and limits. Project commit hooks passed without bypass.
- Final local combined regression: **1829 passed, 5 skipped in 72.52 s** (all storage unit, related CLI, database unit and legacy roundtrip collection). Five DB-dependent legacy roundtrip skips are not MySQL acceptance evidence.
- Final same-environment representative performance run and independent review are still pending. Do not resolve this ticket from intermediate timings or local skipped cases. Detailed report: `docs/superpowers/plans/2026-11-16-conversation-migration-performance-acceptance.md`.
