# 会话迁移：失败租户隔离与正常租户独立上线

本篇是 **显式 `--tenant-isolation` 模式**的操作增补。未使用该选项的全量严格流程仍按 `2026-11-02-conversation-migration-and-launch-runbook.md` 执行。本篇覆盖的部分发布顺序、预览连接数据库、runtime v3 和分享最终 DDL 与旧流程不同，不能混用。设计依据是 `2026-11-13-conversation-tenant-cutover-design.md` 和 ADR 0046。

## 2026-11-16：新作业按 source 独立迁移与上线

新版 `prepare --tenant-isolation` 固定 `source_isolation=true`，发布、失败记录和自动重审单位细化为 `(service_unit_id, tenant_id, source_id)`。同 tenant 的 source=A、B、C 中，B 输入损坏仅记录 B，A、C 继续导入、验证和独立上线。一个 source 内全部 Agent、workspace 和可归属分享仍须一起通过。操作仍为 prepare、migrate 两条主命令，资源参数及四个旧 root 同路径、nas_root 独立的原地模式保持不变。下文“账号/租户”在新作业中均指该三元隔离单位。

新作业须由 DBA 预建 `swe_conversation_migration_sources`：新环境执行最新 `scripts/sql/conversation_migration_control_tables.sql`；已有控制表环境可增量执行 `scripts/sql/conversation_migration_source_tables.sql`。CLI 不执行 DDL。所有 source 发布后，分享字段收口使用 `scripts/sql/conversation_source_publication_finalize.sql`；只有部分 source 发布时不执行全库收口，正常 source 可先上线。

旧 manifest 未声明 `source_isolation=true` 时保持 `(service_unit_id, tenant_id)` 语义，不能手改 manifest 或切换控制表。已有 SQL 票据或业务行的作业不可重建身份来绕过。历史细分 discover/freeze 入口保持兼容，不自动升级粒度；新 source 作业使用首选 prepare。

失败 JSON 增加 `source_id`；阶段结果包含 `source_isolation=true`、`counter_unit=sources`。兼容字段 `tenants`、`published`、`completed`、`failed` 在此模式均按 source 计数。共享 DB、EIO、磁盘耗尽、锁丢失、提交结果不确定仍停止整个命令。无法唯一确定归属的旧分享保守阻断所有可能受影响的 source；已删除 Chat 的孤立旧分享只在唯一可信 source 时归属。

运行时逐次检查 SQL source published 状态；同 tenant 的未发布 source 返回 503，已发布 source 可正常读写。Chat/Session 元数据 CRUD 使用完整可信 `(service, tenant, source, agent)` scope。孤立旧分享保留 legacy_share 的空 source 存储契约，访问时按不可变迁移证据中的 token 唯一归属做 source 准入。详见 ADR 0049。本节覆盖本页历史租户粒度描述，旧作业继续原粒度。

## 首选操作：准备、执行两阶段

本分支新增 `prepare` / `migrate`，常规显式租户隔离迁移优先使用本节。下文细分命令保留作诊断与兼容入口；不要将同一个作业反复 prepare，也不要手改 migration ID。先完成第 1、2 节的备份、旧 writer 停止、只读输入、目标库 DDL/DML 权限和独立 NAS 准备，再执行以下命令。

对操作人员只有这两个迁移阶段。发现、冻结复核、盘点、预检是 prepare 的内部步骤；导入、验证、最终源复查、发布是 migrate 的内部步骤，无需再分别调用对应命令。下文第 3 节整组细分命令是兼容流程，不是执行两阶段后追加的操作。第 4 节的发布说明同样适用于 migrate 自动发布；部署、开放流量和 DBA 最终 DDL 仍是外部操作。

```bash
# 仅首次准备；原地模式保留 --in-place，冻结副本模式去掉它
"$SWE_PYTHON" -m swe conversation-storage prepare \
  --tenant-isolation --in-place \
  --services "$AUDIT_DIR/services.json" \
  --boundary "$AUDIT_DIR/boundary.json" \
  --manifest "$AUDIT_DIR/manifest.json" \
  --application-schema "$APP_SCHEMA" "${CS_RESOURCES[@]}"

# 首次执行与后续补迁均重跑这条；--apply 授权导入、校验和租户发布
"$SWE_PYTHON" -m swe conversation-storage migrate \
  --manifest "$AUDIT_DIR/manifest.json" \
  --output-dir "$AUDIT_DIR/runtime" --apply "${CS_RESOURCES[@]}"
```

`prepare` 合并发现、证据固化、盘点和预检，读取目标库，不导入业务行、不发布账号；输出 manifest 及相邻的 `<manifest文件名>.discovery.json`。输出文件必须不存在。可选 `--shares-file`、`--overrides` 使用已审核的完整记录。部分失败仍保留可归属租户和固定作业身份，检查结果后可让正常租户进入 migrate。

`migrate --apply` 对每个可执行账号按依赖顺序完成导入/续跑、完整语义校验、最后源复查和发布；无需再人工运行 verify/finalize 才发布正常账号。已发布账号从 SQL 读取并跳过其旧输入。它不会部署应用、改变外部流量、停止 writer 或自动 chmod。新版服务仍按 SQL published 与凭证动态准入。

每次 migrate 自动重审**进入命令前已失败**的未发布账号，每账号每次至多一次。零业务数据、零迁移票据者才可接受修订后的输入；已有部分提交者保留旧证据和票据，输入未变时核对后续跑，输入改变时报告失败，不自动删除/重绑。准备时正常但执行前发生输入变化的账号，本次隔离并记录失败，下一次执行才进入自动重审，不能在同一次执行静默接纳新输入。

准备、自动重审和执行读取使用作业级有界并发：独立租户的解析、会话正文 IO 和摘要计算可以重叠。执行采用只读 inventory 预取与 owner 导入/校验流水线；所有账号共享 `io-workers` 线程池与解析内存预算，`workers=1` 时无跨租户预取。该预算是解析分配门禁，并非进程 RSS 硬上限；分享列表、清单摘要及 Python/数据库运行时还有常驻开销，须按实际分享量留出内存。SQL、事务、manifest/journal 权威更新及租户发布仍由单 owner 串行执行；同一账号导入→校验→最后源复查→发布不可乱序，不能用多个命令进程绕过同库命名锁。

prepare 的最终预检（以及独立 preflight/预览）在排除已发布和发现失败账号后，最多并行盘点 workers 个账号，共用 IO 池和每槽解析预算。migrate 最多保留 workers-1 个后续账号预读；当前账号获得其余 worker 和对应内存额度，传给 workspace 导入、分享导入、验证及最终盘点。例如 workers=4，尚有三个预读账号时当前账号使用 1 槽；只剩一个当前账号时使用 4 槽。已预读完但尚未消费的账号仍占一份额度，防止驻留数据预算超配。分配在当前账号开始处理时确定，不在账号处理中途抢占或重新分配。

退出 `0` 表示该阶段全部完成；退出 `2` 且有效 JSON 为 `status=partial_success` 表示处理完所有可执行独立租户但仍有失败，查看结果中的 `failure_report`，已发布账号不撤销。共享数据库/磁盘/锁故障、取消、提交结果不确定等是致命停止，不能当作坏租户跳过。Click 参数错误也可能退出 2，必须核对结构化结果，不能只判断退出数字。失败报告只含服务、账号、阶段、代码和安全原因；完整审计材料保存在受限目录。

全部账号发布后仍须执行第 6 节专用 schema 收口，由 DBA 执行 DDL；之后可重跑 migrate 核对作业状态，已发布账号不重盘。真实 NAS、停写/备份及固定旧镜像回滚验收仍是现场责任。

## 1. 边界与上线单位

- 新 prepare 作业以 `(service_unit_id, tenant_id, source_id)` 为发布单位，同 source 的 Agent、workspace 和分享一起通过；旧 manifest 仍以 `(service_unit_id, tenant_id)` 为单位。
- `source_root/config_root/snapshot_root` 是冻结输入；`original_root` 是新版实际工作区根；`nas_root` 是新正文存储。默认冻结副本模式要求输入与所有服务的在线 `original_root` 分离。显式原地模式允许四个旧 root 相同，见第 1.1 节。`snapshot_root` 是旧分享正文根，不等于“在线工作区根”。
- 启动迁移前停止全部旧 writer、定时任务和其他写入口并建立备份；冻结源持续保留。程序接受停写证据引用，不替代停止进程或存储冻结。
- 新运行时仅放行 SQL 状态为 `published` 且凭证核对通过的账号。失败、未注册账号返回 HTTP 503，错误码 `conversation_tenant_not_published`，不回退旧文件。
- 已发布 A 可在新版写入，B 的后续普通预检、导入、续跑、校验和发布直接跳过 A，不再读取其冻结正文。多实例从 SQL 动态读取准入，无需为 B 发布重启 A。
- 无可信账号归属的错误不能随意跳过：会保守阻断受影响服务/账号。MySQL、共享盘 EIO/空间耗尽、锁丢失、提交结果不确定和取消会终止本次命令；不是可忽略的坏租户。

## 1.1 原地迁移：不复制 workspace

如需直接使用原业务目录，首次发现必须同时指定 `--tenant-isolation --in-place`。四个旧 root 必须是同一个已存在、规范、无软链接的绝对目录；`nas_root` 仍须独立且与业务根互不包含：

```json
{
  "services": [{
    "service_unit_id": "SERVICE_A",
    "source_root": "/mnt/business/service-a",
    "config_root": "/mnt/business/service-a",
    "snapshot_root": "/mnt/business/service-a",
    "original_root": "/mnt/business/service-a",
    "nas_root": "/mnt/conversation-body/service-a"
  }]
}
```

```bash
"$SWE_PYTHON" -m swe conversation-storage discover \
  --tenant-isolation --in-place \
  --services "$AUDIT_DIR/services.json" \
  --output "$AUDIT_DIR/discovery.in-place.json" "${CS_RESOURCES[@]}"
```

后续 freeze 的 `--discovery` 指向这份报告，其余 preflight/import/verify/finalize 命令相同；原地模式随 manifest 固定，后续不重复传 `--in-place`。不能手改已有 manifest 切换模式。尚未正式导入时可用新文件名重做发现和冻结；已有 SQL 数据/票据时不能另建作业继续写同一库。

仍须准备 `boundary.json`：`snapshot_id` 在原地模式填写本次停写/输入固化批次的真实唯一编号，不要求虚构存储快照；`captured_at` 填对应固化完成时间，`evidence_refs` 记录原地未发布输入的只读和停写措施。备份与旧镜像摘要仍需真实保留。

原地不要求复制 workspace，也不要求把整个业务树都设为只读。但所有旧 writer 必须停止，未发布账号的会话输入和精确配置/Agent 证据文件须持续只读、内容不变；必要会话入口目录也保持只读。初次发现前准备这些文件和目录的权限，不能在导入时恢复所有账号的写权限。共享业务根及普通业务目录可以可写。发布 A 后仅恢复 A 的在线配置/业务目录所需权限，B 的未发布输入保持原状。CLI 不自动 chmod 或停止服务。

程序跳过已发布 A 的源盘点；A 更新自己的配置、新建 Agent、写新会话以及共享服务根 mtime 变化，不影响未发布 B 的正常续跑。B 自身会话入口成员变化仍检查，配置/Agent 证据另有 SHA-256 与读取前后文件身份核验，不能用保留 mtime 绕过。任意跨账号共享/嵌套 workspace、配置文件或账号目录会使涉及账号失败，其他独立账号继续。

原地模式同样在各阶段只记录可归属的坏租户并继续正常组；数据库/锁/共享 NAS 故障仍中止本次命令。失败账号没有 legacy 回退。恢复 B 输入后，如原数据已有业务行/票据，不允许随意改内容；遵循第 5 节的原样 resume 或零数据证据重审。

原地重审：将原 discovery 完整报告另存为新的审核输入，保留原 `declared_services`、完整冻结 `source_shares` 和审核 overrides，以该文件传给 `retry-review --reviewed-discovery ... --apply`。该文件用于明确授权重审输入，程序在锁内重新发现未发布组并落完整新证据审计；已发布目录仅按旧可信目录映射剪枝，不再读 A 在线配置/正文。不要在 A 已上线后直接将普通 discover 的在线分享表输出当冻结依据。新增未知账号、服务/root 变化或无法证明已发布账号独占目录等全局证据问题，会使该次重审拒绝。能归属到 B 的候选边界冲突（包括指向已发布 A 的目录）则拒绝 B 的候选修订，恢复 B 原有映射与证据并记录失败，其他独立 D 继续重审；不会改动 A。B 已有业务行/票据时，保留 B 完整旧记录、不修订其证据并报告 B 失败，其他独立组仍可继续。

原地不是独立快照，仍需迁移前数据库和 NAS 备份。上线后的整体回滚必须合成 A 最新状态与 B 保留输入，不能直接让旧版读取混合运行目录。

## 2. 环境准备

先按旧手册完成版本/依赖核验、备份、停写与冻结、应用库及 DML 账号准备。除现有会话表、分享 extension 和迁移控制表外，本分支的 `scripts/sql/conversation_migration_control_tables.sql` 还创建 `swe_conversation_migration_tenants`；已有控制表部署也须由 DBA 执行最新幂等建表脚本。迁移 CLI 不执行 DDL。

命令在当前发布镜像/本工作树执行，Python、配置加载方式须与现场一致：

```bash
export SWE_PYTHON=/opt/python/bin/python
export PYTHONPATH="$PWD/src"
export AUDIT_DIR=/audit/conversation-tenant-20261113
export APP_SCHEMA=REPLACE_APPLICATION_SCHEMA
export MIGRATION_WORK_DIR=/migration-work
mkdir -p "$AUDIT_DIR" "$MIGRATION_WORK_DIR"
chmod 700 "$AUDIT_DIR" "$MIGRATION_WORK_DIR"
CS_RESOURCES=(--workers 4 --io-workers 4 --memory-budget-mib 512
  --work-dir "$MIGRATION_WORK_DIR")
"$SWE_PYTHON" -m swe conversation-storage prepare --help
"$SWE_PYTHON" -m swe conversation-storage migrate --help
"$SWE_PYTHON" -m swe conversation-storage discover --help
"$SWE_PYTHON" -m swe conversation-storage retry-review --help
"$SWE_PYTHON" -m swe conversation-storage rollback-tenants --help
```

`AUDIT_DIR` 是受限审计目录，与冻结输入、NAS 根和工作区互不包含；`APP_SCHEMA` 是目标应用数据库名。CLI 读取既有数据库配置，`APP_SCHEMA` 只用于命令参数核对，不会自动覆盖配置中的 `SWE_DB_NAME`。配置已正确加载时无需重复设置环境变量；环境实际解析的库名必须与冻结 manifest 一致。不要把数据库密码写入命令、文档或报告。

执行镜像必须安装项目要求的真实 `trace_sdk`。本地无替身的 CLI help 核验仍因缺少该包而失败；测试套件中的 tracing fake 不能代替镜像依赖验收。上述 help 命令必须在实际执行镜像全部退出 0，才可开始停机迁移；不要将 `tests/fakes` 加入生产 `PYTHONPATH`。

`workers/io-workers` 范围为 1–32，内存预算为 128–65536 MiB。首选两阶段命令支持跨账号有界解析/IO与只读预取；SQL和发布保持单 owner 串行。旧细分执行命令保留原有逐组编排。临时卷须真实可写并与源、NAS 分离。

## 3. 旧细分入口：首次发现、冻结与导入

复用旧手册经审核的 `services.json`（真实绝对目录）、`boundary.json`（真实停写/快照/旧镜像证据）。首次 discovery 使用**新文件名**：

```bash
"$SWE_PYTHON" -m swe conversation-storage discover \
  --tenant-isolation --services "$AUDIT_DIR/services.json" \
  --output "$AUDIT_DIR/discovery.json" "${CS_RESOURCES[@]}"
```

退出 0 表示全部通过；退出 2 且 JSON `status=partial_success` 表示已完成发现但有隔离账号。检查 `discovery.failed-tenants.json` 中账号和原因，以及受限 `discovery.json` 的完整 blockers。不要把任意退出 2（例如 Click 参数错误）都视为成功；退出 1 或无有效报告应先处理共享/配置错误。

发现报告的 `ready=false` 保持“全体无阻断”的含义；隔离模式允许保留失败账号登记并冻结正常组。不要手改 `ready`、tenant state 或删除失败记录：

```bash
"$SWE_PYTHON" -m swe conversation-storage freeze \
  --discovery "$AUDIT_DIR/discovery.json" --boundary "$AUDIT_DIR/boundary.json" \
  --application-schema "$APP_SCHEMA" --manifest "$AUDIT_DIR/manifest.json" \
  "${CS_RESOURCES[@]}"
"$SWE_PYTHON" -m swe conversation-storage preflight \
  --manifest "$AUDIT_DIR/manifest.json" "${CS_RESOURCES[@]}"
"$SWE_PYTHON" -m swe conversation-storage import \
  --manifest "$AUDIT_DIR/manifest.json" --apply "${CS_RESOURCES[@]}"
"$SWE_PYTHON" -m swe conversation-storage verify \
  --manifest "$AUDIT_DIR/manifest.json" "${CS_RESOURCES[@]}"
"$SWE_PYTHON" -m swe conversation-storage finalize \
  --manifest "$AUDIT_DIR/manifest.json" --output-dir "$AUDIT_DIR/runtime" \
  --apply "${CS_RESOURCES[@]}"
```

每一步均检查输出，不因前一步退出 2 自动跳过后续正常组。启用 `set -e` 的脚本须显式保存退出码并解析报告后决定继续，不能用无条件 `|| true`。各步骤在审计目录写入独立时间戳 `*.failed-tenants.json`，仅包含账号、服务、阶段、错误码及安全原因；详细源路径/内容只留受限审计输入。正常租户无需混入失败清单。

**隔离模式的预览也连接数据库**，以可靠排除已发布账号；与旧严格模式无 `--apply` 预览不同。预览不等于发布。普通预览不登记导入状态，但可能恢复上一次中断的证据重审 pending。

会话输入预算只覆盖 `chats.json`、`sessions/`、`dialog/`、经审核的 session override 及关联 ledger，分享按明确记录路径读取。不递归业务附件/代码/技能目录。真正会话输入仍受字节、单条记录和条目预算约束；路径越界、软链接、特殊文件或未映射会话数据仍拒绝。

## 4. 正常租户独立上线

`finalize --apply` 对逐租户语义校验成功、源未变化、路径/目标结构正常的账号提交 `published`；该 SQL 状态是权威，`import` 或 `verify` 不会上线。部分失败时可正常生成每服务 SHA-256 文件名的 `*.runtime.json`，内容是程序签发的 version 3 部署引用，不能手造映射或编辑凭证。

按旧手册的 Kubernetes 配置/密钥/挂载步骤，将**当前服务**生成文件安装到可信只读路径，并设置：

```bash
SWE_CONVERSATION_STORAGE_AUTHORITY=mysql
SWE_CONVERSATION_SCOPE_MANIFEST=/etc/swe/conversation/conversation-scopes.json
CMB_CAAS_SERVICEUNITID=REPLACE_REAL_SERVICE_ID
# SWE_CONVERSATION_ARCHIVE_CURSOR_SECRET 由部署密钥注入，不能为空
```

文件名和挂载名可由部署系统映射，内容不改。服务身份、NAS 根、数据库 server UUID 和 migration ID 必须一致。所有实例升级至支持 v3 准入的同一版本；旧 writer 保持停止。发布后检查正常账号读写、分享访问、失败账号稳定 503。注册账号的可信 scope 与配置仍需正确，任意请求传 tenant ID 不会获得新账号准入。

`published>0` 与整体 `ready=false` 可以同时成立。所有账号发布后，分享列仍允许 NULL 时会返回 `pending_schema_finalize=true`、退出 2；这不撤销已发布账号。

## 5. 失败重试

### 输入未变的失败

修复临时环境/容量问题后，继续**同一 manifest 和迁移 ID**：

```bash
"$SWE_PYTHON" -m swe conversation-storage resume \
  --manifest "$AUDIT_DIR/manifest.json" --apply "${CS_RESOURCES[@]}"
"$SWE_PYTHON" -m swe conversation-storage verify \
  --manifest "$AUDIT_DIR/manifest.json" "${CS_RESOURCES[@]}"
"$SWE_PYTHON" -m swe conversation-storage finalize \
  --manifest "$AUDIT_DIR/manifest.json" --output-dir "$AUDIT_DIR/runtime" \
  --apply "${CS_RESOURCES[@]}"
```

verify/finalize 失败的租户先 resume 恢复完整 imported 状态，再 verify/finalize。不要清控制表、删 bundle、改账号/service ID 或重新 freeze 后写入同一半成品库。

### 首次 discovery 的配置/输入需要修正

初次失败组不会因普通 resume 自动恢复。仅当该账号**尚无业务行且尚无迁移票据**时，可以审核修复冻结输入，再重新设置只读并准备完整审核报告。服务/root、账号集合和原始分享记录必须保持不变；不得修改已发布账号。修改冻结输入是受控证据修订，记录修复人与理由，不是开放旧 writer。

**原地模式按第 1.1 节准备原 discovery 的完整副本，直接执行下面的 `retry-review`，跳过本节提取 shares 和重新 `discover` 的命令。** 已发布 A 的原地配置与正文就是在线数据，普通 discover 不知道 SQL 发布状态，仍会读取它们。保留副本中的原 `declared_services`、`source_shares` 和完整审核 overrides，由 `retry-review` 在锁内重发现未发布组。

原地模式的审核副本及重审命令如下；示例首次发现文件名对应第 1.1 节。目标文件必须不存在；审核副本保留完整原报告，修复的是 B 的实际输入及只读措施，不能手改报告伪造新证据：

```bash
"$SWE_PYTHON" - "$AUDIT_DIR/discovery.in-place.json" "$AUDIT_DIR/discovery.in-place.review-1.json" <<'PYREVIEW'
import os, sys
with open(sys.argv[1], "rb") as stream:
    report = stream.read()
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "wb") as stream:
    stream.write(report)
PYREVIEW
"$SWE_PYTHON" -m swe conversation-storage retry-review \
  --manifest "$AUDIT_DIR/manifest.json" \
  --reviewed-discovery "$AUDIT_DIR/discovery.in-place.review-1.json" \
  --apply "${CS_RESOURCES[@]}"
```

检查本次失败清单后，对可继续的账号执行本节开头的 resume/verify/finalize。已发布 A 无需重新恢复权限或冻结，其在线配置和新 Agent 不应复制回 B 的证据。

以下重新生成 discovery 的步骤仅适用于默认冻结副本模式。新 discover 仍会盘点全部冻结账号的正文，包括已发布 A 的冻结正文；不会读取 A 的在线新正文。`retry-review` 内部再次发现时则使用已发布组的固定映射与计数，跳过其正文盘点。普通 resume/verify/finalize 也跳过已发布组，不能把这几种不同操作混为一谈。

重审须使用原 manifest 的完整 `source_shares`，不能默认读取在线分享表：A 上线后新增分享或增加访问计数属于正常业务，不得写回冻结证据。先只读提取原始完整分享集合；以下命令独占创建私有文件，已存在时拒绝覆盖：

```bash
"$SWE_PYTHON" - "$AUDIT_DIR/manifest.json" "$AUDIT_DIR/shares.frozen-review-1.json" <<'PY'
import json, os, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    shares = json.load(stream)["source_shares"]
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    json.dump({"shares": shares}, stream, ensure_ascii=False)
PY
"$SWE_PYTHON" -m swe conversation-storage discover \
  --tenant-isolation --services "$AUDIT_DIR/services.json" \
  --shares-file "$AUDIT_DIR/shares.frozen-review-1.json" \
  --output "$AUDIT_DIR/discovery.review-1.json" "${CS_RESOURCES[@]}"
"$SWE_PYTHON" -m swe conversation-storage retry-review \
  --manifest "$AUDIT_DIR/manifest.json" \
  --reviewed-discovery "$AUDIT_DIR/discovery.review-1.json" \
  --apply "${CS_RESOURCES[@]}"
```

首次使用过 overrides 时，重审 discover 也须传入完整审核后的 `--overrides` 文件，保留未修改账号的可信身份映射。新报告可能仍退出 2；核对剩余失败集合符合审核结果后，才继续 retry-review。

接着执行上一节 resume/verify/finalize。重审会重新核对完整配置覆盖，对可修改组更新证据和同步起点，保留已发布组；SQL CAS、只读快照及 pending 文件用于审计和中断恢复。不要删除 `*.review-pending.json` 或修订快照；重跑命令会在命名锁内判断 SQL 已提交还是未提交，未知状态拒绝继续。

已有迁移业务行/票据的账号不支持直接修改输入后 retry-review，也不提供自动删除部分数据的 reset。该账号保持完整旧证据并记录失败，不阻断其他可重审账号；应保持其隔离，另行制定受控数据修复/恢复方案。

## 6. 全部账号完成后的分享 schema 收口

DBA 确认全部登记 source 均 published，并安排元数据锁维护窗口后，用 fail-fast 客户端执行。旧 tenant 粒度 manifest 则仍用 `conversation_tenant_publication_finalize.sql`，不要混用：

```bash
mysql --defaults-extra-file="$DBA_CNF" --database="$APP_SCHEMA" \
  < scripts/sql/conversation_source_publication_finalize.sql
```

此专用脚本**不删除分享**，未全部发布或定位/归属不完整会拒绝 ALTER。不要在部分上线期间执行旧 `conversation_share_service_unit_finalize.sql`（含 DELETE）。之后重跑同一 `migrate --apply`（旧细分流程可用 `finalize --apply`），整体才能进入 ready；已发布账号仍跳过源盘点。

## 7. 部分上线后的整体回滚

上线后的 A 有新 SQL/NAS 数据，不能简单恢复全部旧快照。必须停止新旧全部 writer、GC 和迁移，确认 IO 排空，审核当前配置完整覆盖；导出 A 的最新权威状态，并合并 B 的冻结会话输入。初次 discovery 失败导致输入闭包无法证明时拒绝合成，先补齐证据。

`rollback-tenants` 的 `--rollback-inputs` 是 JSON：含 `boundary`（SourceBoundary）、`writers_stopped_ref`、`io_drained_ref`、`current_config_review_ref`，以及 `target`（`image_digest`、`session_version`、`checkpoint_version`）和 `current_configs` 数组。每项配置映射恰为 `service_unit_id/tenant_id/source_id/config_path/review_ref`，路径必须在对应 original_root 内，真实身份与 Agent 配置必须核对。版本数值以固定旧镜像实际支持为准。

```bash
"$SWE_PYTHON" -m swe conversation-storage rollback-tenants \
  --manifest "$AUDIT_DIR/manifest.json" \
  --rollback-inputs "$AUDIT_DIR/rollback-inputs.json" \
  --output-dir "$AUDIT_DIR/rollback-new" --apply "${CS_RESOURCES[@]}"
```

输出必须是全新目录，不覆盖旧数据。CLI 只生成可审查内容，**没有运行固定旧镜像的读取并继续写入验证**，因此 `rollback_ready=false`、退出 2。停写引用只是运维声明。只有固定旧镜像逐服务根实际读取并继续写入通过，且隔离验证不破坏待恢复副本后，才可按受控恢复流程切换旧版。真实 NAS 与旧镜像验证必须另行完成；本地/隔离 MySQL 测试不代替现场验收。
