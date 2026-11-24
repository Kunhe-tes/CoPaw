# NAS 会话元数据迁移操作手册

适用存储模式 `mysql-metadata`。将旧 `chats.json` 中的 Chat 目录和逻辑 Session 关联迁入 MySQL。会话正文、Turn 和归档由应用继续在原 NAS workspace 读写。

## 1. 准备数据库、目录和停写窗口

1. 为当前服务单元确认 NAS 工作目录根。普通租户使用 `<NAS 根>/<scope-id>/workspaces/default/chats.json`，其中 `scope-id` 使用线上采用的无前缀 scope 编码。source 系统级 `default` 用户使用 `<NAS 根>/default_<source-id>/workspaces/default/chats.json`。扫描会跳过该用户的编码目录，即使对应的未编码目录缺失。迁移进程和线上实例应看到同一个 workspace 绝对路径。
2. 确认迁移镜像中 `swe conversation-storage prepare --help`、`migrate --help` 和 `export-metadata --help` 均能执行。将 `CMB_CAAS_SERVICEUNITID` 设置为当前服务单元真实标识，并按应用现有配置注入目标 MySQL 连接参数和凭据。核对 `SWE_DB_NAME`。
3. 由 DBA 在目标应用库先安装基础会话表，再安装元数据模式扩展。已有会话表时，由 DBA 先核对结构，再应用缺失的 DDL。 [基础会话表](../../scripts/sql/conversation_metadata_tables.sql) · [元数据模式扩展](../../scripts/sql/conversation_mysql_metadata.sql)
4. 在正式迁移前停止会修改这些目录及会话的旧服务、任务和其他写入口，等在途写入完成。为数据库和 NAS 保留同一恢复点的备份，并记录旧镜像版本。可以提前运行扫描来检查范围，正式执行时必须保持扫描覆盖的 workspace 集合正确，并维持停写直至完成切换验收。

完成后，目标库具备 Chat、Session 和迁移状态表，NAS 和数据库均有可用的恢复点。

以下命令在能访问 NAS 和目标 MySQL 的环境中执行。将示例值替换为现场配置。审计目录应提前创建并可写，且位于业务 workspace 之外。

```bash
export CMB_CAAS_SERVICEUNITID='your-service-unit'
export SWE_DB_NAME='your-app-schema'
NAS_ROOT='/nas/swe'
AUDIT_DIR='/audit/conversation-migration'
MANIFEST="$AUDIT_DIR/workspace-scan.json"
```

## 2. 扫描 workspace

```bash
swe conversation-storage prepare \
  --workspace-root "$NAS_ROOT" \
  --manifest "$MANIFEST" \
  --workers 4
```

扫描按固定路径读取每个 scope 的 `workspaces/default`，检查 `chats.json` 的基本格式。清单记录 `migration_id`、目标库、NAS 根、每个 workspace 的路径和作用域，以及扫描异常。文件内容摘要由后续导入阶段处理。

根目录扫描默认最多使用 4 个线程，可用 `--workers` 调整。`--workers 1` 按顺序扫描。这个参数只影响 NAS 扫描，与数据库连接池独立。

| 输出 | 操作 |
| --- | --- |
| `prepared`，退出 0 | 核对 workspace 数量、路径和 scope。核对 NAS 上预期参与的租户和来源都在清单中。 |
| `partial_success`，退出 2，顶层 `scan_errors` 有记录 | 同一份清单可用于预览和导入。`migrate` 跳过这些目录，在 `failed` 中报告扫描错误，并继续处理已识别的 workspace。需要补迁时，先确认目录归属及线上路径，再为待补迁来源准备清单。 |
| `partial_success`，退出 2，某个 workspace 带 `scan_error` | 检查对应路径和文件。清单仍包含该 workspace，若仅修复其读取权限或 `chats.json`，可用原清单重新预览。 |

扫描结果文件必须是新文件。扫描范围只覆盖各 scope 的默认 Agent。扫描后如果新增了 workspace，在首次导入前重新扫描。默认 workspace 已存在、`chats.json` 缺失且 `sessions/` 和 `dialog/` 均为空时，工具按空工作区处理。

## 3. 只读预览

```bash
swe conversation-storage migrate \
  --manifest "$MANIFEST"
```

预览重新读取当前 `chats.json`，校验 Chat 身份、元数据和 Session 文件名映射。加上 `--full-audit` 后，还会只读解析存在的关联 Session 和归档。预览不连接目标库，数据库结构和连接仍需按第 1 步核对。

完成后，`status=preview` 的 `validated` 列出通过的来源。若返回 `partial_success`，检查 `failed` 中的 `phase`、`scope`、`root` 和 `detail`。预览的文件版本只对应当次检查，正式执行时会重新读取。

## 4. 导入、校验并发布

```bash
swe conversation-storage migrate \
  --manifest "$MANIFEST" \
  --apply
```

命令连接目标库并获取该库的迁移命名锁。每个 workspace 以执行时读取的 `chats.json` 为准，每批最多写入 100 条 Chat。SQL 业务数据和批次进度同事务提交。工作区首次导入时，摘要与首批写入同事务提交。全部批次完成后，程序读回 SQL 目录并核对源文件，再按 `(service_unit_id, tenant_id, source_id)` 发布。

`--full-audit` 为可选项，预览和正式导入都可以启用。默认导入仍会校验 `chats.json`、NAS 路径和文件类型，并读回 SQL 数据核对。额外审计会解析存在的 Session 和归档，增加 NAS 读取和解析时间。

预览和导入默认最多并行处理 4 个独立来源，可用 `--workers` 调整。同一来源内的 workspace 及各自批次按顺序处理。正式导入并发还受进程环境变量 `SWE_DB_MAX_CONN` 限制，默认值为 10。在执行迁移的终端运行 `export SWE_DB_MAX_CONN=10`，或在运行迁移的容器中设置同名环境变量。`SWE_DB_MIN_CONN` 默认值为 2，须小于或等于连接池上限。为对比耗时，可在相同输入和数据库条件下分别使用 `--workers 1` 和 `--workers 4`。

| 结果字段 | 含义 |
| --- | --- |
| `published` | 本次导入、校验并发布的来源。 |
| `already_published` | 同一清单下此前已发布的来源，本次直接跳过。 |
| `skipped_workspaces` | 进度回执与 SQL 记录匹配，本次跳过的 workspace。 |
| `failed` | 失败来源或 workspace，可能已有部分批次提交。只要该来源存在失败，它就保持未发布。 |

`ready` 且退出 0 表示本次清单中的来源已全部处理。退出 2 时查看结构化结果，确认是否为 `partial_success`。部分成功时，其他来源已经完成的发布有效。保留原始清单、命令输出以及生成的 `<清单文件名>.progress.json`。

## 5. 续跑和失败处理

| 场景 | 操作及效果 |
| --- | --- |
| 命令中断、连接故障或命名锁被占用 | 确认旧进程退出或连接恢复后，用原清单重跑第 4 步。相同输入可依据数据库进度继续。 |
| workspace 的预检失败，或首批写入失败并已回滚 | 修复原路径下的文件后，用原清单重跑。导入会重新读取修好的版本。 |
| workspace 已有已提交的导入批次，随后 `chats.json` 改变 | 恢复与数据库绑定摘要一致的文件后，使用原清单续跑。无法恢复时保留现场并核对已提交数据，避免在清单中替换摘要或手工调整进度。 |
| 来源需要绑定修复后的新清单 | 仅用于未发布来源。新旧清单中该来源的 workspace 成员必须一致，已绑定 workspace 的路径和摘要必须匹配。使用 `migrate --manifest <新清单> --resume-from <原清单> --apply --full-audit`。新清单应只包含拟修复来源，已发布来源保留各自原清单。 |

## 6. 切换并验收

在应用部署配置中设置 `SWE_CONVERSATION_STORAGE_AUTHORITY=mysql-metadata`，沿用匹配的 `CMB_CAAS_SERVICEUNITID`、目标 MySQL 和原 NAS 挂载路径。

先启动受控实例，检查已发布来源的 Chat 列表、旧历史和续聊，确认新消息写到预期的原 NAS 路径，重启后能读回。核对未发布来源仍被拒绝。验证通过后，由现场恢复对应来源的写入与流量。

完成后，Chat 目录以 MySQL 为准，应用继续用原 NAS 文件读写会话内容。切换后的版本应独占这些 workspace 的业务写入。

## 7. 回退

若新模式尚未承接业务写入，可使用停写时保留的原目录和 NAS 恢复点启动旧版。若新模式已接收写入，先停止新旧写入入口，记录当前 NAS 恢复点，再从当前 SQL 导出旧版目录。

```bash
swe conversation-storage export-metadata \
  --manifest "$MANIFEST" \
  --destination "$AUDIT_DIR/rollback-export"
```

导出目录必须尚不存在。结果含 `report.json` 和每个已发布 workspace 的旧格式 `chats.json`。若多个清单分别发布了互不重叠的来源，分别导出至独立目录，并按各自报告核对范围。若原清单包含曾通过 `--resume-from` 改绑并发布的来源，使用原清单导出会报绑定冲突，整次导出停止。遇到此情况，应在恢复窗口前核对各来源的发布绑定并准备逐来源恢复方案。

根据报告，将导出目录与同一恢复点的 NAS 配套。未发布来源使用各自保留的旧目录。先验证旧版能读取历史并继续写入，再切换流量。
