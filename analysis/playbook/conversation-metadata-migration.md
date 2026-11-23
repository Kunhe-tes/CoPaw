# 会话元数据迁移

当前只支持 `mysql-metadata` 迁移：Chat 目录和身份写入 MySQL，Session 和归档继续使用原 workspace 的 NAS 文件。默认在线模式仍为 `legacy`。

1. 确定完整的 workspace 与 scope 映射，停止所有写入，并在同一恢复点备份 MySQL 和 NAS。迁移工具不负责停写或备份。
2. DBA 在目标应用库依次执行 `scripts/sql/conversation_metadata_tables.sql` 和 `scripts/sql/conversation_mysql_metadata.sql`。工具不执行 DDL。
3. 准备 JSON 数组，例如 `[{"root":"/nas/workspace","scope":["service-unit","tenant","source","agent"]}]`。路径须规范且唯一，manifest 放在 workspace 外。
4. 执行 `swe conversation-storage prepare --workspaces /audit/workspaces.json --manifest /audit/manifest.json`。
5. 执行 `swe conversation-storage migrate --manifest /audit/manifest.json --full-audit` 预览，检查所有失败项。
6. 执行相同命令并追加 `--apply`。按 source 发布；失败后保留并重用同一个 manifest，检查结构化结果与错误输出。
7. 设置 `SWE_CONVERSATION_STORAGE_AUTHORITY=mysql-metadata` 和 `CMB_CAAS_SERVICEUNITID`，先在受控实例验证历史、续聊、重启、改名及删除，再恢复流量。

切回旧模式前先停写，保留同一恢复点的 NAS 内容，然后执行 `swe conversation-storage export-metadata --manifest /audit/manifest.json --destination /audit/rollback`。按报告将导出的 `chats.json` 与对应 NAS 内容配套，并验证目标旧镜像。工具不会自动覆盖线上目录或切换镜像。

旧 bundle 存储及迁移命令已移除。`SWE_CONVERSATION_STORAGE_AUTHORITY=mysql` 和 `--mode bundle` 不再受支持。现场 MySQL、共享 NAS、锁及回退需事先演练。
