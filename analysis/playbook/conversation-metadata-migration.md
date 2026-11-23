# 会话元数据迁移

当前只支持 `mysql-metadata` 迁移：Chat 目录和身份写入 MySQL，Session 和归档继续使用原 workspace 的 NAS 文件。默认在线模式仍为 `legacy`。

1. 确定完整的 workspace 与 scope 映射，停止所有写入，并在同一恢复点备份 MySQL 和 NAS。迁移工具不负责停写或备份。
2. 新库由 DBA 依次执行 `scripts/sql/conversation_metadata_tables.sql`、`scripts/sql/conversation_mysql_metadata.sql` 和 `scripts/sql/conversation_metadata_performance.sql`。已初始化的元数据库只需应用第三份脚本，建议在迁移或切换窗口执行并核对索引。CLI 的职责是导入数据。
3. 准备 JSON 数组，例如 `[{"root":"/nas/workspace","scope":["service-unit","tenant","source","agent"]}]`。路径须规范且唯一，manifest 放在 workspace 外。
4. 执行 `swe conversation-storage prepare --workspaces /audit/workspaces.json --manifest /audit/manifest.json`。
5. 执行 `swe conversation-storage migrate --manifest /audit/manifest.json --full-audit` 预览，检查所有失败项。
6. 执行相同命令并追加 `--apply`。按 source 发布。单个 workspace 校验或写入失败时，迁移会继续处理同来源及后续来源的 workspace，并在最终报告的 `failed` 中列出范围、路径、阶段和错误。仅包含全部验收成功 workspace 的来源可发布。若失败原因可在保留冻结输入的前提下排除，重用原 manifest 续跑。
   真正为空的 workspace 可以缺少 `chats.json`。迁移会冻结这个状态，并在导入前再次检查。

未发布来源如果有预检失败的 workspace 需要修正，保留原 manifest。用该来源的完整 workspace 列表重新执行 `prepare`，再执行 `migrate --manifest /audit/repaired.json --apply --resume-from /audit/manifest.json`。续跑会检查来源的 workspace 集合，以及所有已绑定 workspace 的路径和注册表摘要。已发布来源继续使用各自的原 manifest，续跑后发布的来源使用修正后的 manifest 导出。
7. 设置 `SWE_CONVERSATION_STORAGE_AUTHORITY=mysql-metadata` 和 `CMB_CAAS_SERVICEUNITID`，先在受控实例验证历史、续聊、重启、改名及删除，再恢复流量。

## 批量导入与性能验收

- 导入按原 Chat 顺序每 100 条提交。每批查询一次 Chat 冲突和工作区排序上限，按完整 Session 身份去重，再批量写入 Session 和 Chat。Session 写入后按 NAS 文件名回读并校验完整身份。写入与进度同事务提交，旧版本已提交的前缀可用原 manifest 继续迁移。批量语句按行数、参数数和数据库包大小拆分，超过批量包安全预算的单条 Chat 沿用原参数化文本插入。
- 发布前使用 `(registry_order, id)` 分页按顺序比较 SQL 和冻结目录。新增索引也覆盖工作区最新排序号及 Session 首条未删除 Chat 查询。使用与生产相近的工作区分布和扩展元数据体积，记录每批 SQL 数、迁移总耗时与发布校验耗时，并用 `EXPLAIN ANALYZE` 核对工作区排序及 Session 首条查询。
- 已登记且已发布的 Session 续聊采用无行锁点查，新建 Session 仍走事务认领。并发验收覆盖同工作区不同 Session、同名文件冲突，以及断点续跑。旧 `/chats` 提供完整目录及精确总数契约，列表型调用可使用 `/chats/-/summaries` 游标接口。

本地 MySQL 8.4.7 对 1,000 条合成 Chat 的 `migrate --apply` 前后对比，语句执行次数从 7,048 降至 108，耗时从 2.01 秒降至 1.02 秒，事务提交均为 11 次。语句数按应用的 `db_statement` 计数，事务控制单独统计。执行计划显示排序上限和回读分页使用 `ix_conv_chat_registry`，含 600 条 Chat 的 Session 首条查询使用 `ix_conv_chat_session_first`。现场吞吐及 DDL 耗时以目标库演练为准。

切回旧模式前先停写，保留同一恢复点的 NAS 内容，然后执行 `swe conversation-storage export-metadata --manifest /audit/manifest.json --destination /audit/rollback`。按报告将导出的 `chats.json` 与对应 NAS 内容配套，并验证目标旧镜像。工具不会自动覆盖线上目录或切换镜像。

旧 bundle 存储及迁移命令已移除。`SWE_CONVERSATION_STORAGE_AUTHORITY=mysql` 和 `--mode bundle` 不再受支持。现场 MySQL、共享 NAS、锁及回退需事先演练。

审批审计和 Run/Attempt 追踪随 NAS 会话执行路径工作。业务轮次覆盖率依赖原 bundle 历史读取器，当前存储模式下返回 HTTP 503。新消息证据从 NAS 中已持久化的消息生成引用，详情按 Chat、Session、消息 ID 和内容摘要定位。无法唯一定位到 NAS 消息的旧引用返回 `unavailable`。
