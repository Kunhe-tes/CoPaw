# Conversation MySQL/NAS 离线切换

## 当前迁移入口

新版会话存储使用 Chat、Session、Turn、Publication 和 Retention 五张 MySQL 元数据表。恢复快照和归档 bundle 保存在 NAS；消息正文、顺序、可见性及重复消息 ID 的出现位置由 bundle 记录。备份与回收沿发布指针和依赖记录追踪文件。

DBA 使用当前分支的 SQL 脚本准备空目标库，服务和 CLI 使用同一版本。先用 `prepare` 登记 workspace 与 source，然后对同一 manifest 执行 `migrate --apply`。导入器读取旧 `chats.json`、`sessions` 和 `dialog`。中断后用原 manifest 续跑，已发布 source 会跳过。历史分享处于迁移排除范围。

### 隔离环境实测（2026-11-20）

远端隔离 MySQL、测试机本地 bundle 目录、3 个 source、3 个 workspace。样本包含 257 条旧归档消息及一个 128 条消息的 Session。导入保留 1 个归档边界，形成 3 个归档数据块，完整审计按页逐条比对原文。远端链路当天的数据库等待明显高于此前本机记录，因此耗时用于同一版本的 SQL 形态与相对分析，不能替代生产容量测试。

| 命令阶段 | 耗时（秒） | SQL 语句尝试数 | 已提交事务 |
|---|---:|---:|---:|
| `prepare` | 5.15 | 11 | 0 |
| `import --apply` | 291.31 | 1,191 | 164 |
| fast `verify` | 34.34 | 90 | 4 |
| `verify --full-audit` | 475.22 | 2,009 | 162 |
| `migrate --apply` 发布已导入的 source | 139.48 | 379 | 79 |
| 同一 manifest 重跑 | 5.98 | 13 | 1 |

业务元数据包含 3 个 Session、3 个 Chat 和 15 条 Publication。迁移控制表包含 15 条批次票据、15 条发布票据及 7 条保护票据，消息票据为 0。另一个实库用例在两个 source 发布后执行 DBA finalize，再使用同一 manifest 重跑，CLI 返回退出码 0 和 `ready`。

10k workspace、2 个 source、500 个有数据的 workspace、1 worker 的容量样本未完成。dataset、preflight 分别约 24.42 秒、28.94 秒；进入 import-and-resume 后运行 2,094.34 秒，在远端数据库单次操作超过 30 秒时抛出 `Database operation timed out`。超时前记录约 17,754 次 SQL cursor 调用（累计 1,577.35 秒）、247 次 bundle publish 和 247 次 inspect；进程 RSS 峰值约 573 MiB，spool 峰值约 18.8 MiB。该结果说明 10k、1 worker 路径没有在本次测试窗口内完成，不能作为容量验收通过。

迁移只读审计确认以下风险仍待容量验证：

- `manifest-v1` 新版路径绕过 workspace 输入预检；旧归档和 checkpoint events 仍通过 `read_text().splitlines()` 整文件载入内存，再保留全部消息。
- 默认预检启用时，512 MiB 内存预算按 4 个 worker 切分后，每个 workspace 可分配约 8 MiB，大型 workspace 可能过早被拒绝。
- 完整审计和快速校验按 archive chunk 查询 Publication；完整审计还会逐 bundle inspect/read，形成 chunk 数量相关 SQL 和串行 NAS I/O。
- source 会经过 fingerprint、spooled inventory recheck 和逐 Chat 临时目录复制等多次扫描；消息分块先编码计算大小，写入时再次编码。
- SQL 由单一 owner task 串行执行。代表性样本队列峰值很低，但 10k 单 worker 的数据库超时表明仍需在生产链路评估延迟、重试和超时边界。

发布前还应以单 Chat 100k 消息或数 GB 归档覆盖 100 个以上 chunk，记录 parser/spool RSS、临时磁盘、SQL 行数、bundle open/read 次数和分页耗时。

## 历史流程与故障记录

下文保留旧版 staging 安装、回退和故障排查记录。旧版的表数、分享导入及安装命令适用于对应历史版本。

## 启动期循环导入（2026-11-13）

`aedfa7bb8` 在 `tenant_workspace.py` 顶层引入 `conversation_storage.tenant_admission` 后，启动会触发以下循环：

```text
_app → tenant_workspace → conversation_storage.__init__ → chat_repository
→ publications → commit_plan → shares → chat_sharing.__init__ → service
→ runner.api → runner.utils → agents.utils.tool_summary → agent_context
→ tenant_workspace.TenantWorkspaceContext（尚未执行到类定义）
```

这发生在 MySQL/NAS 初始化之前。本地复现命令（在该 worktree）：`PYTHONPATH=src:tests/fakes ../../venv/bin/python -c 'import swe.app._app'`。`tests/fakes` 仅补齐本地测试环境缺少的 trace_sdk，部署不应使用 fake。

修复将 `conversation_storage.__init__` 的 `MySQLChatRepository` 改为惰性导出，切断包级提前加载并保留公开接口。新增 `tests/unit/app/test_conversation_storage_import.py`，在全新子进程验证中间件导入及仓库公开接口，避免缓存模块或 stub 掩盖导入顺序问题。修复后独立进程导入 `_app` 成功，相关单元测试 1458 项通过；未执行连接真实 MySQL/NAS 的完整生命周期启动验证。

## 当前操作入口与历史说明

2026-11-15 起，显式租户隔离流程首选 `prepare --tenant-isolation --in-place` 与 `migrate --apply` 两阶段；同一 manifest 重跑 migrate 自动重审此前失败账号并按断点续跑，校验通过后逐租户自动发布。准备后新变化的账号本次隔离，下次执行才重审；有数据/票据不自动重建。部分成功退出 2 必须结合结构化报告判断。详见租户操作增补的首选操作章节。旧严格流程及下面历史命令不因此改变。

当前 v3 全量严格迁移以 [全量手册](../../docs/superpowers/plans/2026-11-02-conversation-migration-and-launch-runbook.md) 为准；显式租户隔离与独立上线以 [租户操作增补](../../docs/superpowers/plans/2026-11-13-conversation-tenant-migration-operations.md) 为准。`discover --tenant-isolation` 的有效 partial_success 报告允许正常账号继续；失败/未登记账号仍不可用。共享 SQL/IO/锁故障不能当作坏租户跳过，verify/finalize 失败先 resume，修改已有导入数据的输入不支持直接 retry-review。 原地迁移显式使用 `discover --tenant-isolation --in-place`，四个旧输入/业务 root 完全相同、NAS 新正文根独立；未发布账号的精确会话及身份输入持续只读，已发布账号自己的在线写入不阻断其他账号续跑。跨账号重叠输入仅阻断受影响账号。默认冻结副本模式仍要求输入与在线根分离。

以下 v2 安装/换表内容仅供历史排查，不能用于当前 v3 写入、授权配置或权限准备。v3 CLI 使用预建表与 DML 连接，不要求迁移执行账号拥有 CREATE/ALTER/DROP。

## 准备和清单

使用审核过的源码 checkout（安装器读取该 checkout 的 `scripts/sql/`）；普通 wheel 不包含这些离线 DDL。运行账号需要目标实例的 schema/global CREATE、ALTER、DROP、INSERT、SELECT、UPDATE、DELETE，以及 information_schema / performance_schema 可见权限。仅通过 role 获得的权限保守拒绝，须另行审核。

先使用 `MigrationManifest.create(path, SourceBoundary(...), workspaces)` 创建 v2 持久化清单。`SourceBoundary` 必须包含最终只读快照身份、带时区时间、`old-image@sha256:<64 hex>` 和停 writer / 只读挂载证据引用。每个 workspace 显式记录源快照 `root`、`service_unit_id`、`tenant_id`、`source_id`、`agent_id`；可选 registry/sessions/dialog 相对路径及 `session_paths: [{user_id, channel, session_id, path}]`。不得根据散列/文件名或当前机器环境变量猜测旧数据的服务归属。

清单增加以下 `offline` 配置；路径示例须替换为已有挂载和审计目录：

```json
{
  "offline": {
    "application_schema": "shared_business_schema",
    "nas_roots": {
      "LQ13.03@a_prd": "/existing/service-a/nas",
      "LQ13.03@b_prd": "/existing/service-b/nas"
    },
    "shares": [],
    "export": {
      "services": {
        "LQ13.03@a_prd": {
          "backup_path": "/audit/service-a-backup",
          "destination": "/audit/service-a-empty-export"
        },
        "LQ13.03@b_prd": {
          "backup_path": "/audit/service-b-backup",
          "destination": "/audit/service-b-empty-export"
        }
      },
      "session_version": 3,
      "checkpoint_version": 2
    }
  }
}
```

`shares` 是在同一最终边界导出的完整旧分享八字段，另加 `snapshot_workspace_index` 和 `snapshot_path`；服务归属来自明确指定的 workspace。没有分享时才使用空列表。不得漏掉已删除 Chat 的永久分享。安装器会把原分享表八字段全部行与 staging 对比，包含 token、访问计数和时间。

全部服务必须在一个协调作业中分配全局整数 ID 并安装共享七表；`nas_roots` 必须精确覆盖源服务，且原 NAS 根彼此隔离。导入回填分享归属后执行 `scripts/sql/conversation_share_service_unit_finalize.sql`，再通过最终 schema 检查。旧 v1 清单和三项 scope 不会自动补服务。

MySQL authority 启动必须设置稳定的 `CMB_CAAS_SERVICEUNITID`。同服务全部副本使用同一个原 NAS；运行时 scope manifest 为 v2，包含顶层 `service_unit_id`、`nas_root` 和 `workspaces`，其中 `scope` 顺序为 `[service_unit_id, tenant_id, source_id, agent_id]`。部署环境、顶层服务和每个 workspace 的服务必须一致。服务在启动时读取并绑定，运行中不随环境变量变化。

staging 名称固定为 `conversation_staging_<migration_id 去掉连字符>`，旧 share 名称固定为 `swe_chat_shares_old_<同一后缀>`。不能任填 staging 或 SQL 表名。导入器把 schema/NAS/migration 绑定持久化到 manifest。目标 NAS 必须为原来的、已存在的根目录；冻结源应为独立只读快照挂载，不能把它用作目标 NAS。新 bundle 只占用生成路径，不删除旧目录或旧文件。

报告引用：所有命令 stdout 是 JSON，应保存到审计目录。安装器另写 `<manifest>.install.json`，其中含验证覆盖清单、同实例能力探针、执行前/后名称、精确正/逆 SQL。该文件是持久化切换凭据，应在变更记录中与 manifest 一同引用。禁止改一个 `passed: true` 绕过核验；`install --apply` 总会重跑完整语义核验并核对每个对象和源文件覆盖。

## 连续停机步骤

每步审计记录同一组字段：作业 ID、操作者、UTC 开始/结束时间、命令（脱敏）、退出码、report 路径、证据路径、判断、恢复动作。任何一步失败都保持入口关闭，不向后跳步。

1. **停入口。** 关闭 HTTP/通道入口、定时触发、自动重试和外部调用。记录开关状态和部署版本。验证没有新增请求。
2. **排空。** 等待全部实例活跃 Turn 收敛。核查 admitted/running/stopping/settling/unknown、进程内队列和任务写入。排空超时：取消本轮、保留旧版和当前数据，按旧版流程结算；不得把未结算 Turn 改成 completed。
3. **停全部 writer。** 停所有 Pod、cron、后台 worker、迁移脚本和 GC；验证副本均为零且无自动伸缩重启。分享访问会更新计数，也属于 writer。保存调度器与 Pod/进程证据。
4. **最终备份和边界。** 在 writer 全停后建立 NAS 只读快照、完整 workspace mapping、源 registry/session/archive、旧 share 八字段快照、旧镜像 digest。对源目录及文件去写权限，并验证挂载本身只读。记录 snapshot ID/时间和恢复演练报告。备份失败：保持停机或恢复旧入口，不能继续导入。
5. **Inventory / Plan。** 执行下列只读命令，保存报告并审核身份映射、原 NAS 根、生成 staging 和阻断项。所有预览都不连接数据库、不写文件。任何源可写、路径/身份冲突、未识别历史或未固定镜像都会停止。
6. **Import。** 先执行无 `--apply` 的预览；再显式导入。只创建作业生成的 staging schema 和七张表，share 使用原表 `CREATE TABLE ... LIKE` 保持八字段定义和索引，再应用扩展。导入使用有界批次和持久化 manifest，重跑保持原 ID/operation key。导入失败：业务表未切换，保留 staging/manifest 定位后续跑；不删除 NAS bundle。
7. **Verify。** 运行只读完整语义核验。任何 blocker 都禁止安装；报告不完整也禁止安装。该命令不更新 manifest 的 batch 状态。
8. **Install。** 审核预览后执行 `--apply`。安装器核对同实例、七张表结构/索引、原 share 全量行、触发器、外键、视图、权限和 MDL；在两个全新隔离 schema 中实测冲突失败全回退及成功七表切换。探针结束会清理自己的 schema。旧业务已有任一六张新表时拒绝覆盖。正式安装只运行一条包含八个 rename 对的原子 RENAME：原 share → staging 的生成旧名，七张 staging 表 → 业务原名。不会触碰其他业务表。
9. **启动前审核点。** 保存 `<manifest>.install.json`，核对 phase、before、after：staging 仅剩生成旧 share，业务七张目标名均存在，其他业务表不变。此时尚未启动任何新版进程。
10. **受控启动和冒烟。** 首次启动一个新 Pod前记录 UTC 时间和不可逆回退分支切换。从启动动作本身开始，统一按“可能已有新写”处理。验证相同原 workspace/NAS、历史、checkpoint、分享 token、Turn、并发和恢复。启动失败或冒烟失败仍保持入口关闭，进入完整反向导出分支。
11. **恢复入口。** 全部冒烟/监控/审计签字后扩容并恢复入口。保存首笔新写时间、版本 digest、NAS 验收和停机预算实测。没有真实双 Pod/NAS 与旧镜像读写验收，不宣称生产可发布。

```bash
swe conversation-storage inventory --manifest /audit/manifest.json
swe conversation-storage plan --manifest /audit/manifest.json
swe conversation-storage import --manifest /audit/manifest.json
swe conversation-storage import --manifest /audit/manifest.json --apply
swe conversation-storage verify --manifest /audit/manifest.json
swe conversation-storage install --manifest /audit/manifest.json
swe conversation-storage install --manifest /audit/manifest.json --apply
swe conversation-storage inspect --manifest /audit/manifest.json
```

## 回退分支和故障演练

**安装前失败：** 旧 share 和全部旧文件未改变。排空失败先结算旧 Turn；备份失败重新备份；导入失败使用同 manifest 续跑；验证失败修复明确 blocker 后重验；原子能力/MDL/权限失败停止安装。决定取消时仅恢复原镜像和原 workspace/NAS/入口，保留 staging、bundle、报告供审计。不执行共享业务库整体恢复，不批量 unlink NAS。

**安装后、任何新版启动动作之前：** 必须有连续停 writer 的审计证据，而且确实没有任何新进程初始化、冒烟、分享读取或管理员写入。先保持入口关闭并再次检查没有 writer/MDL，审核 receipt 的精确实际名称。仅此窗口可执行 receipt 中 `reverse_sql_before_any_startup_or_write`，一条原子 RENAME 把七表移回 staging、原 share 移回业务原名；旧 NAS 本来就未改。核对原 share 八字段/所有 token、六张新表均不在业务 schema、原快照文件不变后，以固定旧镜像启动。receipt 的 phase 只记录安装时状态，**不能证明此后没有写入**；无法证明从未启动则走下一分支。CLI 不提供盲目自动逆向。

**任何新版启动、初始化、冒烟、分享访问或新写之后：** 禁止执行逆向 RENAME、恢复旧 NAS 快照或恢复整个共享业务库。这会丢新会话和计数。重新停入口、排空并停全部 writer，使用 conversation 一致性备份能力记录全部 scope 的当前七表和所引用 NAS bundle；每个 scope 使用非空即拒绝的独立导出目录执行 export。清单 `offline.export.services` 必须精确覆盖全部服务，每项 `backup_path` 指向该服务的一致性 backup；导出的 `rollback_ready` 默认 false。必须在固定旧镜像隔离实例上验证全部原生格式可读且能继续写，形成每个 scope 的旧镜像验收证据，再由审核过的定向导入恢复原 workspace 和分享索引。任何源格式/完整性不支持则保持新数据和停机，不能部分恢复。

```bash
swe conversation-storage export --manifest /audit/manifest.json
swe conversation-storage export --manifest /audit/manifest.json --apply
```

**RENAME 响应丢失或检查失败：** receipt 保持 `rename_pending`。这表示结果未知，不表示回滚成功。保持全部 writer 停止，独立连接查询两个 schema 的精确七表及生成旧 share 名；核对只有“完整旧态”或“完整新态”。不得直接重跑 install（已有 receipt 会拒绝），不得手改 phase 伪造成功。若业务六表存在且 staging 只剩旧 share，按完整新态处理；若观察到混合态，保留数据并升级数据库诊断。只有完成状态对账和审核后才能采取对应回退分支。

演练至少逐项记录：排空超时、备份不可读、导入批次中断并续跑、故意缺失正文的 verify blocker、原子探针冲突/不支持、MDL 阻塞、RENAME 响应丢失、启动失败、冒烟后新会话和分享计数更新。最后两项必须证明选择完整反向导出而非直接恢复旧快照。

本地隔离副本的十阶段 operator ledger：
`/private/tmp/conversation-local-stages-20261101-r2/ledger/report.json`。
十阶段 exit 0，总 98.1515 秒；逐阶段 UTC/argv/exit 和边界见
`docs/superpowers/reports/2026-11-01-conversation-local-simulation.md`。
该证据覆盖一个历史 Session/Chat、独立旧 writer 超时/停止和当前树 legacy 续写；
不覆盖目标 ingress、全部队列/Pod writer 排空、全 scope 或固定旧镜像。

## 本地证据与生产门禁

`tests/integrated/conversation_storage/test_install.py` 的真实数据库用例只创建/删除随机生成的隔离 schema；覆盖探针失败原子性、七表安装、启动前逆向、无关业务表保持不变。连接缺失时跳过，不能把 skip 视为验收。运行时应使用项目虚拟环境及测试数据库环境变量，不输出连接配置/凭据。

生产门禁仍需目标数据库实例的完整探针/权限/MDL验收、真实原 NAS 原语与双 Pod、停机预算、固定旧镜像读取并继续写、以及全 scope 新写后反向导出。代码测试通过不能替代这些环境证据。

## SQL authority 进程退出后的结算

请求仍在本进程登记时，Runner 使用已关闭并排空 IO 的 IndexedQuery 对原 operation 对账；这不证明进程重启后的恢复。进程退出、Pod 被删除或一致性 restore 后，由离线 recover 命令从 SQL 重建原 Session/Turn/publication 身份。禁止凭 lease 到期判断进程死亡；先关闭该 scope 入口和全部重试，核查精确 Pod UID/进程 incarnation 已退出、模型/工具子任务已终止、NAS 写入已排空。保存控制面和 IO 排空证据。外部工具的业务副作用不会重放或撤销。

建立经过人工核对的 JSON 证据；owner_key、generation、turn_id 来自原准入 publication 和 Turn，不使用当前 Session generation 猜测；scope/Session 必须为原始逻辑身份。原 NAS 和 workspace 必须已经存在。

    {
      "version": 2,
      "service_unit_id": "LQ13.03@a_prd",
      "schema": "shared_business_schema",
      "workspace_root": "/existing/workspace",
      "nas_root": "/existing/original/nas/root",
      "scope": {"service_unit_id": "LQ13.03@a_prd", "tenant_id": "tenant", "source_id": "source", "agent_id": "agent"},
      "session": {"user_id": "alice", "channel": "console", "session_id": "original-session"},
      "turn_id": 123,
      "owner": {
        "owner_key": "exact-original-owner-incarnation",
        "generation": 7,
        "evidence_ref": "change-record/pod-uid-exit-and-io-drain",
        "operator": "reviewed-operator",
        "owner_stopped": true,
        "io_drained": true
      }
    }

    swe conversation-storage recover --evidence /audit/owner-exit.json
    swe conversation-storage recover --evidence /audit/owner-exit.json --apply --confirm-ended-owner exact-original-owner-incarnation --receipt /audit/recovery.jsonl

预览不连接数据库、不写文件；apply 要求确认字符串与原 owner 完全相同，且配置中的数据库与证据 schema 一致。命令在任何 DB 写入前将完整证据写入并 fsync receipt，结束记录 completed 或 unavailable。证据是操作者核实的声明，CLI 无法自行验证 Kubernetes/进程退出，自动化调用必须通过 EndedOwnerRecovery.verify_stopped 接入真实控制面验证。命令不初始化业务 workspace、不执行 DDL。

恢复先校验完整关联、原 owner/generation 和 active Turn，再 fence writer。已有 durable prepared 结果按原 key 和原不可变正文提交；缺失且尚未确认 durable 的原操作留下 aborted tombstone；未准入且没有正文的 reservation 标为 rejected 并释放。没有可提交终态时，以已确认完整 recovery root（含未知模块/Cron receipts）发布 interrupted；Stop 已获胜则发布 stopped。任何已确认正文缺失/截断、身份漂移、另一 owner 或未能确定提交结果都保持 busy/unavailable，修复后用相同证据重试，不伪造 completed、不重跑模型或工具。receipt 中 unavailable 不表示回滚。还需在目标 NAS 和真实 Pod 崩溃环境演练本段流程。

## 多 scope 七表整体恢复

备份仍按 scope 捕获。恢复同一业务库的多个 scope 时，必须把完整备份路径列表一次传给
`restore_backup(database, bundles, backup_paths, evidence=RestoreEvidence(...))`；不能逐个
恢复到已含数据的目标。单一路径调用保持原语义。目标仍必须是生成的隔离测试/staging
schema，七表和目标 NAS 目录均为空；不直接覆盖共享业务库，也不初始化业务 workspace。

操作者必须在捕获整组备份前停止全部相关 scope writer、重试及 GC，并保持停止直至捕获结束；
保存同一源库、完整 scope 清单和停止边界证据。代码验证源 schema 相同、scope 无重复及
每份备份完整性；它不能从给定路径自行推断是否漏掉某个业务 scope。

恢复先合并并校验全部元数据与引用。同 `(service_unit_id, tenant)` 的 legacy_share publication、分享记录及
正文必须一致，重复共享记录只写一次；不同 scope 的非共享 ID 冲突直接拒绝。共享 reader/
backup_fence 的 active→released 差异仅按已停源证据结算，其余字段不得漂移。
任何冲突在目标目录创建和 SQL 安装前阻断。七表随后在一个事务中安装，完整比对并逐 scope
核验真实 reader。多 scope 报告使用 `backup_ids`、`snapshot_refs`、`scopes` 和聚合计数，
不要把单份备份的验证报告当成全部 scope 的恢复证据。

跨服务恢复必须传 `service_unit_id → BundleStore` 的显式映射；各目标根必须为空且互不重叠（不存在时只创建隔离恢复目标根），不能把不同服务复制进同一 NAS。完整集合的 scope、服务归属、全局 ID/token 和引用先校验，再复制和单事务安装。单个 BundleStore 只接受单服务集合。

长期 Session 的恢复引用和发布前历史读取按每批最多 4096 个 publication pin；整个引用集
仍在同一事务快照内授权，NAS IO 排空后释放全部批次。提交阶段的依赖锁定也按 ID 顺序分批，
依赖安装仍在同一事务内完成，不通过删除 Cron/task 历史绕过规模问题。
修复与验证范围见[专项报告](../../docs/superpowers/reports/2026-11-01-conversation-r1-r2-fixes.md)。
