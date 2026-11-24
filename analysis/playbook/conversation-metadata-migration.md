# 会话元数据迁移

当前只支持 `mysql-metadata` 迁移：Chat 目录和身份写入 MySQL，Session 和归档继续使用原 workspace 的 NAS 文件。默认在线模式仍为 `legacy`。

1. 确定完整的 workspace 与 scope 映射，停止所有写入，并在同一恢复点备份 MySQL 和 NAS。迁移工具不负责停写或备份。
2. 新库由 DBA 依次执行 `scripts/sql/conversation_metadata_tables.sql`、`scripts/sql/conversation_mysql_metadata.sql` 和 `scripts/sql/conversation_metadata_performance.sql`。已初始化的元数据库只需应用第三份脚本，建议在迁移或切换窗口执行并核对索引。CLI 的职责是导入数据。
3. 准备 JSON 数组，例如 `[{"root":"/nas/workspace","scope":["service-unit","tenant","source","agent"]}]`。路径须规范且唯一，manifest 放在 workspace 外。
4. 执行 `swe conversation-storage prepare --workspaces /audit/workspaces.json --manifest /audit/manifest.json`。
5. 执行 `swe conversation-storage migrate --manifest /audit/manifest.json --full-audit` 预览，检查所有失败项。
6. 执行相同命令并追加 `--apply`。按 source 发布。单个 workspace 校验或写入失败时，迁移会继续处理同来源及后续来源的 workspace，并在最终报告的 `failed` 中列出范围、路径、阶段和错误。仅包含全部验收成功 workspace 的来源可发布。若失败原因可在保留冻结输入的前提下排除，重用原 manifest 续跑。
   真正为空的 workspace 可以缺少 `chats.json`。迁移会冻结这个状态，并在导入前再次检查。

7. 设置 `SWE_CONVERSATION_STORAGE_AUTHORITY=mysql-metadata` 和 `CMB_CAAS_SERVICEUNITID`，先在受控实例验证历史、续聊、重启、改名及删除，再恢复流量。

`migrate --apply` 把已完成校验的 workspace 写入 manifest 旁的 `<manifest 文件名>.progress.json`。续跑时，记录与目标库中的 workspace 路径、注册表摘要和已导入条数相符即可跳过，并在最终报告的 `skipped_workspaces` 中列出。旧迁移若没有完成记录，会补做一次校验。进度文件读写失败时，迁移记录警告，并按正常的校验和发布流程继续处理。`--full-audit` 只复用通过完整审计的记录。

未发布来源如果有预检失败的 workspace 需要修正，保留原 manifest。用该来源的完整 workspace 列表重新执行 `prepare`，再执行 `migrate --manifest /audit/repaired.json --apply --resume-from /audit/manifest.json`。续跑会检查来源的 workspace 集合，以及所有已绑定 workspace 的路径和注册表摘要。已发布来源继续使用各自的原 manifest，续跑后发布的来源使用修正后的 manifest 导出。 保留原 manifest 旁的进度文件，续跑会复用匹配的记录。

## 切换后 Chat 列表返回 `conversation_tenant_not_published`

来源发布和 workspace 绑定检查先于 `/api/chats` 的分页逻辑。首屏和游标请求都可能返回同一个 HTTP 503。先用失败请求实际命中的实例配置及请求解析出的逻辑租户、来源和 Agent 查应用库。

```sql
SET @service_unit_id = '<CMB_CAAS_SERVICEUNITID>';
SET @tenant_id = '<logical tenant ID>';
SET @source_id = '<source ID>';
SET @agent_id = '<agent ID>';

SELECT DATABASE() AS application_schema;

SELECT s.migration_id, s.published,
       CONVERT(w.workspace_root USING utf8mb4) AS workspace_root
FROM swe_conversation_metadata_sources AS s
LEFT JOIN swe_conversation_metadata_workspaces AS w
  ON w.service_unit_key = s.service_unit_key
 AND w.tenant_key = s.tenant_key
 AND w.source_key = s.source_key
 AND w.agent_key = CAST(@agent_id AS BINARY)
WHERE s.service_unit_key = CAST(@service_unit_id AS BINARY)
  AND s.tenant_key = CAST(@tenant_id AS BINARY)
  AND s.source_key = CAST(@source_id AS BINARY);
```

- 查不到来源行时，先核对线上实例与迁移进程的 MySQL 实例、库名和服务单元。配置一致时，检查原清单是否覆盖该来源以及 `migrate` 的 `failed` 是否有登记前失败。若扫描漏掉了来源，按实际 NAS 路径为遗漏范围准备清单。
- `published=0` 时，按报告中的失败阶段修正并用原清单续跑 `migrate --apply`。由迁移命令完成校验和发布，避免直接更新 SQL 发布位。 [迁移续跑与失败处理](../../docs/deployment/conversation_nas_mysql_migration.md#5-续跑和失败处理)
- `published=1` 且有 `workspace_root` 时，核对它与故障实例解析出的 workspace 真实绝对路径，特别是 Pod 的 NAS 挂载路径。若 `workspace_root` 为空，先确认 Agent 及其 workspace 是否在迁移范围内。运行时只会为已发布来源的空 workspace 自动创建绑定。
- 若首屏成功而续页报 503，按两次请求实际命中的实例对照服务单元、数据库和 NAS 挂载，并核对解析出的租户、来源和 Agent。 [发布与绑定检查](../../src/swe/app/conversation_storage/runtime.py)

## 清单中有 workspace，迁移报告出现 `phase=preflight`

扫描可将含 `scan_error` 的 workspace 写入清单，正式导入会读取当前源文件重新校验。整个目录文件无法解析时，workspace 无法进入 SQL 导入。单个 Session 校验失败时，同一 workspace 中通过预检的 Session 继续入库，来源保持未发布。

- `Expecting value`、`Unterminated string` 和 `Extra data` 分别指向缺少 JSON 值、字符串未闭合和完整 JSON 值之后存在额外内容。`UnicodeDecodeError` 指向非法编码字节。应先核对 `chats.json`。使用 `--full-audit` 时，错误也可能来自关联 Session 或归档，当前解析错误只报告 workspace 路径。
- 在迁移容器内按报告中的绝对路径读取原始字节，记录文件大小和 SHA-256，并检查错误位置。JSON 行列以解码后的字符计数，UTF-8 解码错误的位置以字节计数。迁移读取整个 `chats.json`，扫描和预检分别读取文件，事后打开的内容可能来自另一个版本。
- `multiple Session identities map to ...` 由 `chats.json` 中的 Chat 触发。对照冲突项的 `user_id`、`channel` 和 `session_id`。旧文件名只使用清理后的用户和 Session ID，可能因不同渠道或字符替换发生碰撞。多个 Chat 共用完全相同的 Session 身份可以通过预检。
- 扫描从目录名解码租户和来源。迁移只处理 `user_id` 与清单租户 ID 相同的 Chat。排查冲突时，以记录自己的 `user_id` 和 `session_id` 计算旧文件名。

## 批量导入与性能验收

- 导入按原 Chat 顺序每 100 条提交。每批查询一次 Chat 冲突和工作区排序上限，按完整 Session 身份去重，再批量写入 Session 和 Chat。Session 写入后按 NAS 文件名回读并校验完整身份。写入与进度同事务提交，旧版本已提交的前缀可用原 manifest 继续迁移。批量语句按行数、参数数和数据库包大小拆分，超过批量包安全预算的单条 Chat 沿用原参数化文本插入。
- 发布前使用 `(registry_order, id)` 分页按顺序比较 SQL 和冻结目录。新增索引也覆盖工作区最新排序号及 Session 首条未删除 Chat 查询。使用与生产相近的工作区分布和扩展元数据体积，记录每批 SQL 数、迁移总耗时与发布校验耗时，并用 `EXPLAIN ANALYZE` 核对工作区排序及 Session 首条查询。
- 已登记且已发布的 Session 续聊采用无行锁点查，新建 Session 仍走事务认领。并发验收覆盖同工作区不同 Session、同名文件冲突，以及断点续跑。旧 `/chats` 提供完整目录及精确总数契约，列表型调用可使用 `/chats/-/summaries` 游标接口。

本地 MySQL 8.4.7 对 1,000 条合成 Chat 的 `migrate --apply` 前后对比，语句执行次数从 7,048 降至 108，耗时从 2.01 秒降至 1.02 秒，事务提交均为 11 次。语句数按应用的 `db_statement` 计数，事务控制单独统计。执行计划显示排序上限和回读分页使用 `ix_conv_chat_registry`，含 600 条 Chat 的 Session 首条查询使用 `ix_conv_chat_session_first`。现场吞吐及 DDL 耗时以目标库演练为准。

切回旧模式前先停写，保留同一恢复点的 NAS 内容，然后执行 `swe conversation-storage export-metadata --manifest /audit/manifest.json --destination /audit/rollback`。按报告将导出的 `chats.json` 与对应 NAS 内容配套，并验证目标旧镜像。工具不会自动覆盖线上目录或切换镜像。

旧 bundle 存储及迁移命令已移除。`SWE_CONVERSATION_STORAGE_AUTHORITY=mysql` 和 `--mode bundle` 不再受支持。现场 MySQL、共享 NAS、锁及回退需事先演练。

审批审计和 Run/Attempt 追踪随 NAS 会话执行路径工作。业务轮次覆盖率依赖原 bundle 历史读取器，当前存储模式下返回 HTTP 503。新消息证据从 NAS 中已持久化的消息生成引用，详情按 Chat、Session、消息 ID 和内容摘要定位。无法唯一定位到 NAS 消息的旧引用返回 `unavailable`。
