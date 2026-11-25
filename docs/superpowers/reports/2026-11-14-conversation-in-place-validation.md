# 原地会话迁移验证记录

日期：2026-11-14。工作树：`.worktrees/conversation-mysql-nas`。

## 已实现范围

显式 `discover --tenant-isolation --in-place` 允许 `source_root/config_root/snapshot_root/original_root` 使用同一规范绝对目录，`nas_root` 独立，不复制 workspace。模式随 manifest 和 SQL 作业绑定固定。可归属的租户错误写入脱敏失败报告，其他独立租户继续；只有 SQL 发布状态为 `published` 的租户可进入新版业务。

未发布账号的会话输入和精确配置/Agent 证据仍须只读且不变。已发布 A 可恢复自身权限、修改配置、新建 Agent 和写入会话；普通补迁跳过 A，原地证据重审使用原 discovery 完整审核副本。已有数据/票据的 B 保留完整旧证据；恢复旧映射引起的候选冲突迭代核对，冲突账号局部失败，独立组继续。

## 已执行验证

- 单元和 CLI 回归覆盖原有严格流程、固定输入范围、只读与变化检查、租户归属、SQL 状态和运行时准入、失败报告及证据重审。最终结果见本记录下方交付核验。
- 真实 MySQL 场景一：A/C 发布、B 失败；A 上线后修改配置、新建 Agent 并新增 SQL 会话，再续跑并发布 B，断言 A 不再盘点、在线数据保留。`1 passed in 90.51s`，本地日志 `/tmp/tenant-in-place-mysql-final.log`。
- 真实 MySQL 场景二：B 首次配置失败；A 发布并在线写入后，修复 B，使用原 discovery 副本进行锁内重审，再发布 B。`1 passed in 67.13s`，本地日志 `/tmp/tenant-in-place-review-mysql.log`。两场景在读取前保护修复后合并重跑，`2 passed in 95.73s`，日志 `/tmp/tenant-in-place-mysql-delivery.log`。
- MySQL 场景仅使用随机独立的 `test_conversation_*` 测试库，记录并核验准确测试库清理；合并重跑结束后按本次身份记录逐一查询，父库及两个子库均不存在。未对应用库执行迁移、DDL 或清理。
- 独立子代理复核发现并推动修复了三个边界：已有票据租户恢复旧映射后的连锁候选冲突；显式 profile/override 越入已发布租户输入时必须在读取前拦截；跨服务同名账号的分享须按冻结 token 归属限定重审，避免探测已上线账号。

## 交付核验

- 最终单元与 CLI 完整回归：`1540 passed in 57.75s`，日志 `/tmp/conversation-in-place-delivered.log`，JUnit `/tmp/conversation-in-place-delivered.xml`。包含三个最终边界修复及原严格流程回归。
- 最终分享归属修复后，独立子代理只读复核未发现新的阻断问题；MySQL 两场景结果来自此前读取前保护修复后的合并重跑，最后的跨服务分享分支另有定向已知/未知/歧义归属回归。
- MySQL 用例及单元运行有 pytest 旧临时目录清理警告；测试返回 0，数据库精确清理查询通过。格式及静态检查覆盖本轮 Python 改动；自动格式修正后，69 项定向测试和最终 pre-commit 均稳定通过（mypy、Black、flake8、pylint）。`git diff --check` 通过。

## 具体边界

- 本轮使用本地目录和隔离 MySQL 验证实现逻辑；未做真实 NAS、万级容量或性能验收。
- 旧 writer、定时任务和其他旧写入口必须停止。原地模式不提供双写、在线增量追赶，也不允许提前恢复未发布账号写权限。CLI 不自动停进程或修改文件权限。
- 数据库断连、未知提交、锁丢失、共享挂载/EIO/盘满和程序错误仍终止当前命令；不能把这类错误当坏账号忽略。无法可信归属的冲突保守阻断受影响服务。
- 未发布账号已有业务行/票据时，不自动删除、重置或按新语义重绑；只保留原证据并报告，需按手册审核处理。
- 本地真实 CLI help 尚缺 `trace_sdk`。测试使用仓库已有 tracing fake，不构成执行镜像依赖验收，严禁将 fake 引入生产。上线镜像必须用真实依赖完成 help 和启动检查。
- 未验收固定旧镜像回滚读写；部分上线后的回滚须保留已上线账号最新 SQL/NAS 提交，不得直接恢复最初快照。

操作以 [租户迁移操作手册](../plans/2026-11-13-conversation-tenant-migration-operations.md) 第 1.1 节原地流程为准。
