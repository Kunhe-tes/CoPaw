# 会话迁移性能验收

本说明复用 `prepare → migrate --apply`，不增加现场迁移阶段。性能规格以 `.scratch/conversation-migration-performance/spec.md` 为准。禁止通过放宽源冻结、完整校验、fsync、单 SQL owner 或 source 准入来降低耗时。

## 隔离范围

使用项目虚拟环境、固定代码版本、本地临时输入目录及专用空 MySQL 测试库。`SWE_TEST_DB_NAME` 必须以 `test_` 开头或 `_test` 结尾，且不得等于应用库；测试 fixture 再新建随机子库，只删除自己创建的子库。数据库凭据由环境或 Secret 注入，不写进报告或提交。该测试会执行 CREATE/DROP DATABASE，须使用获准的测试实例及账号。

```bash
cd /path/to/isolated/worktree
export PYTHONPATH=src
export SWE_TEST_DB_HOST=获准测试实例
export SWE_TEST_DB_PORT=3306
export SWE_TEST_DB_USER=获准测试账号
export SWE_TEST_DB_NAME=test_conversation_performance
# SWE_TEST_DB_PASSWORD 由 Secret 注入，值是实际密码，不经过 SWE_DB_ACCESS 前缀处理。
/path/to/project/venv/bin/python -m pytest \
  tests/integrated/conversation_storage/test_performance_workflow_mysql.py \
  -q -s --disable-warnings \
  -o cache_dir=/private/tmp/conversation-performance-cache \
  --basetemp=/private/tmp/conversation-performance-run
```

缺少测试库配置时 pytest 会 skipped；skipped 不作为 MySQL 验收通过证据。基线与最终版本须使用不同 `basetemp`，相同 Python/依赖、数据库实例、worker/IO/预算和测试数据。记录两个 commit SHA、操作系统、数据库版本、延迟条件与日志；比较输出的 `representative_prepare_migrate` JSON，不比较不同输入的总时长。

用例固定三个小 source/workspace，其中一个包含 128 条消息；另一路覆盖运行中 Turn 导致的 source 失败、其他 source 发布、修复后重跑。资源固定 workers=3、io-workers=2、memory=128 MiB。第二次运行使用原 manifest；不重新 prepare，不删除票据。已有更广的 source 保护、分享/归档/事件/checkpoint 和中断恢复用例由最终组合验收一并运行。本用例不代替这些语义回归。

## 指标口径

- `db_calls/db_seconds`：迁移 DML 门面调用及累计等待，含失败；一次 prepared 门面调用可能执行多块。
- `db_statement_attempts/db_statement_seconds`：普通 execute 或每个 prepared 分块的执行尝试及累计执行耗时，包含失败/取消，不含协议 prepare/reset、建连、读取结果和清理。
- `db_executemany_calls/db_executemany_seconds`：驱动 executemany 调用单列；内部 SQL 数未知，不能当作一条真实 SQL。
- `db_transaction_begins/commits/rollbacks`：底层边界调用尝试，嵌套事务不重复计数；提交次数不是提交成功证明，UnknownCommit 仍全局停止。
- `bundle_opens/bundle_index_parses`：实际打开与索引解析尝试；生命周期限于一次安全读取，不跨命令缓存。
- `stage_wall_seconds`：同名阶段累计墙钟，含当前阶段。并发预读可能重叠；`io_seconds` 是累计 IO 时间，不能相加为墙钟。
- `rss_peak_bytes/temp_peak_bytes`：现有进度的采样进程 RSS/已登记临时数据峰值；解析门禁不是进程 RSS 硬上限。

数据库层各口径有重叠，禁止求和。性能日志不包含正文、凭据、SQL 参数或源路径。prepare 测量由测试外层观察上下文捕获；migrate 使用现有 CLI 进度。失败时报告实际退出码和阶段，不能将 partial_success 解释为全部 source 成功。

## 结果边界

结果须区分本地单测、真实隔离 MySQL、本地目录与受控延迟 IO。未执行真实 NAS、万级基线、生产部署或现场旧镜像回滚时明确标注。SQL 形态/计数改善不等于承诺现场总耗时倍数；数据库身份或命名锁丢失仍须排查连接/代理原因。

## 2026-11-16 基线实测

优化前 SQL 路径加观测的版本 `cb6430e73`，macOS 本地目录、项目 Python 3.12、获准远程隔离 MySQL、无人工 IO 延迟；测试新建专用空父库与随机子库，结束后均清理。执行上述代表性用例：`2 passed in 491.26s`。每例为 3 source、3 workspace、128 条输入消息，workers=3/io-workers=2/128 MiB。

| 场景 | 首次 migrate 墙钟 | execute 尝试 | BEGIN/COMMIT 尝试 | 后续原作业 migrate |
|---|---:|---:|---:|---:|
| 三个正常 source | 229.499 s | 2922 | 358/358 | 2.800 s，25 execute |
| 一个 running Turn source 失败，其余正常 | 217.765 s | 2723 | 329/329 | 修复后25.754 s，267 execute |

全部正常场景导入阶段92.278 s、完整验证129.430 s；数据库 execute 累计183.310 s，不与墙钟相加。首次 RSS 采样峰值约192 MiB、登记临时数据峰值81854字节。失败场景正常source完成发布，修复后原manifest重跑达到3个published。CLI退出2为预期：前者仍待schema最终收口，后者还包括失败source；不表示共享故障。

该基线尚未接入bundle计数钩子，输出中的0表示未观测，不能解释为没有文件IO。最终实现须使用接线后的版本另报该指标；SQL/事务对照仍使用相同观察边界。该次未做真实NAS、万级或生产验收。该段记录基线时点；最终对照、组合故障及收口结果见下文。

## 最终组合验收记录

截至2026-11-16，01–09的实现已合入集成分支；09采用测量后的保守决策：记录binding序列化和manifest持久化次数、字节、耗时，保留原有准确序列化及全部检查点。30 source的隔离本地测量中编码约0.000741秒，尚不足以证明增加可变证据缓存值得其可靠性成本；该测量不含数据库/业务导入，不代表端到端加速。最终CLI报告同时保留`binding_*`及`manifest_*`指标。

### 已取得的真实MySQL证据

由中央运行器使用获准远程隔离MySQL取得；本文不包含连接信息、正文或SQL参数。每次运行仅清理本次创建的父/子测试库。

| 验证 | 版本/范围 | 结果 | 含义 |
| --- | --- | --- | --- |
| 五类身份票据、自增间隙 | ticket04已合入版本 | 5 passed | 不以连续自增ID推算映射 |
| 关联集合锁与回滚 | `41075904a`/`52d590a6e` | 2 passed，13.38 s | 持锁时既有行UPDATE与缺失ID INSERT均返回1205；回滚后成功；既有ID查询EXPLAIN使用PRIMARY |
| SQL owner、锁丢失与未知提交恢复 | `52d590a6e` | 3 passed，108.24 s | 并行IO仍为单SQL owner；KILL锁连接后全局停止并排空IO，原manifest恢复；真实驱动丢失COMMIT响应后恢复 |

关联锁测试最初错误地在`DatabaseSession`调用事务接口，已由`ce15aea3a`修正并通过上述实际运行；不将修正前失败计为通过。中间版本正常源性能试跑为184.963秒、2419次execute、232次事务，只含01/02/03/06；混合场景遇到网络2013并全局停止、`io_drained=true`，此失败不是最终验收成功证据，也不用于性能收益结论。

### 最终同环境性能对照

中央运行器在01–09全部合入版本`ce182a17f`（随后`8bbfaacc9`仅格式化指标捕获）执行相同代表性fixture，**2 passed in 255.95 s**。与`cb6430e73`基线同为macOS/Python 3.12、本地临时输入、同一获准远程MySQL环境、3 source/3 workspace/128输入消息、workers=3/io-workers=2/128 MiB，无人工IO延迟；父/子测试库全部清理。远程时延和服务器负载存在波动，不以一次墙钟差异承诺普遍倍数。

| 场景 | 基线墙钟→最终 | execute尝试 | BEGIN/COMMIT尝试 |
| --- | ---: | ---: | ---: |
| 三个正常source首次migrate | 229.499→124.960 s | 2922→2421 | 358/358→231/231 |
| 一个running Turn失败、其余发布 | 217.765→104.449 s | 2723→2218 | 329/329→202/202 |
| 修复失败source，原manifest重跑 | 25.754→14.889 s | 267→264 | 34/34→33/33 |
| 全部已发布后原manifest重复运行 | 2.800→1.269 s | 25→18 | 最终1/1 |

最终正常场景prepare 1.150秒；migrate阶段import 32.734秒、verify 87.200秒、最后源复查1.186秒、publish 0.826秒，数据库execute累计104.557秒。完整验证仍是主要瓶颈，继续保留全部语义比较。混合场景prepare 1.260秒、import 21.800秒、verify 78.558秒；修复重跑automatic_review 1.864秒、import 9.253秒、verify 1.685秒。并发阶段、数据库累计等待不能相加。

最终bundle打开/索引解析为：正常首次36/29，全部已发布重复0/0，混合首次26/21，修复重跑10/8；基线未接线，故不宣称这些计数的前后下降比例。单次多块读取索引一次由本地真实文件计数回归独立证明。

正常首次binding编码7次/43652字节/0.000596秒，manifest写6次/129913字节/0.018726秒；混合首次6次/37416字节/0.000349秒，manifest写6次/127269字节/0.012101秒；修复重跑8次/49932字节/0.000418秒，manifest写3次/112355字节/0.009243秒。全部已发布重复运行manifest写0次。09保留检查点的决定符合实测，未以缓存或降低持久性争取收益。

正常首次RSS采样峰值214515712字节（约204.6 MiB）、登记临时数据81638字节；混合首次119062528/81743字节，修复重跑121044992/4326字节。128 MiB是解析/共享资源门禁，进程RSS包含解释器及依赖，并非RSS硬上限；相对基线约192 MiB未证明进程内存下降。各次migrate退出2符合待schema最终收口语义；混合首轮另含坏source，修复后3个published且failed=0。

SQL形态另有确定性计数证据：513条Message为6个100行上限INSERT，513条已提交记录为3次最多256 ID查询，批量票据受100行/256 KiB/服务器packet预算限制；这些本地协议回归已在1829项组合通过中，不将整条CLI execute数误称为只有业务INSERT。

最终独立复核发现单个合法8 MiB artifact加元数据时聚合读取上限误拒绝；以上性能fixture未触发该边界。修复`4aa7b1558`已通过独立复核并合入：调用方最多读取两个extent，固定聚合预算16 MiB；每extent的8 MiB限制、安全文件复查及共享IO门禁保持有效。该修复未重新运行上述性能fixture，不把边界修复后的墙钟收益作为新测量结果。

### 本地组合回归

边界修复前测试分支`8bbfaacc9`运行全部`tests/unit/app/conversation_storage`、五个相关CLI模块、`tests/unit/database`及`test_legacy_roundtrip.py`：**1829 passed，5 skipped，72.52 s**。五项skip是本地未配置真实数据库的legacy roundtrip用例，不作为MySQL语义验收证据；本地门禁/文件/领域回归全部通过。新增测试及指标捕获修改均通过正常项目提交hooks（AST、编码、密钥扫描、格式、mypy、flake8、pylint），未跳过检查。最终数据库性能结果见前节；后续完整语义回归与独立复核修正见下文。

### 覆盖与边界

复用现有测试，避免新建一套迁移入口：

| 要求 | 主要用例 | 证据层级 |
| --- | --- | --- |
| 原prepare→migrate、多个小source及128消息source | `test_performance_workflow_mysql.py` | 真实MySQL：2 passed，255.95 s；详见最终对照 |
| 同租户双source、坏source跳过、独立准入、补迁不重读线上兄弟旧输入 | `test_tenant_workflow_mysql.py::test_same_tenant_source_retry_preserves_published_sibling` | `c5f52b4a1`真实MySQL：1 passed，35.47 s |
| 分享、归档、事件、checkpoint、多Session/Turn/Message及中断后原作业恢复 | `test_parallel_import_mysql.py`复用`test_v3_migration_mysql.py`；既有`test_legacy_roundtrip.py` | 组合回归与中央MySQL结果分开报告 |
| 空/满/跨块、字段形态、packet、大字段、逐行语义核对及回滚 | `test_offline_record_batching.py`、`test_batch_tickets.py` | 本地协议/领域测试；真实身份另见上表 |
| 同一次多块读取仅一次打开/索引解析、软链接/特殊文件/截断/替换拒绝 | `test_bundle.py` | 本地真实文件IO和可控取消 |
| 源新增/删除/修改/替换、源边界与最后复查 | `test_workspace_input_mutations.py`、`test_source_freshness_boundaries.py`、`test_tenant_workflow_mysql.py` | 本地真实文件与CLI测试 |
| 共享IO/磁盘容量错误、取消、UnknownCommit全局停止与排空 | `test_tenant_orchestration.py`、`test_migration_parallel.py`、`test_offline_{write,commit,confirm,verify}_stages.py` | 故障注入；真实锁/COMMIT另见上表 |
| 共享worker/IO/内存/临时盘预算 | `test_shared_migration_resources.py`、`test_disk_manifest.py`、`test_registration_performance.py` | 门禁与采样指标，不等同RSS硬上限 |

新增用例已在`c5f52b4a1`真实MySQL通过（1 passed，35.47 s），父/子测试库已清理。用例针对可能的tenant级误准入或补迁误覆盖：两个source同属alice，四个旧根完全相同且NAS独立；正常兄弟发布后增加Agent、更新标题并新增Chat，破坏其旧session输入使重读可被观察，再修复坏source并使用原manifest迁移。断言未指定source、坏source及未知source不能准入，线上兄弟完整行与config保持不变，修复后只有对应source获得准入。

最终范围仍不包括真实NAS、万级基线、生产部署、现场放行或固定旧镜像回滚。同租户CLI已由中央运行器真实验证；8 MiB聚合读取预算修正、独立复核及下述组合回归均完成，ticket10与最终审查已收口；单项通过仍不代替现场验收。

## 最终复核与收口

- 边界修复：`4aa7b1558`修复合法8 MiB artifact加metadata的误拒绝。实现者报告先在direct/threaded/prefetched三路径复现RED（3 failed、4 passed），另为超过两个extent的数量限制取得RED（1 failed、7 passed）；独立审查者也复现原缺陷。修复后会话存储与五个相关CLI模块1771 passed、67.76 s，合并ticket10后focused 87 passed、0.67 s。RED数字由实现者提供，独立审查确认原缺陷可复现。
- 独立复核：fresh reviewer针对`4aa7b1558`给出APPROVE，独立focused **86 passed、0.68 s**，原P2已解决且无剩余发现；修复通过正常项目hooks，无绕过。
- 真实MySQL完整语义：`test_legacy_roundtrip.py::test_complete_legacy_import_reentry_and_semantics[v3-interrupted-message-batch]` **1 passed、1 warning、253.94 s**；覆盖消息批次中断后的重入及完整语义，父/子隔离测试库清理成功。运行使用`--disable-warnings`，日志未展示warning详情，不能称无警告。
- 本地回归历史：边界修复前最终单元组合 **1828 passed、70.88 s**；与早先含legacy roundtrip collection的1829 passed/5 skipped运行范围不同，不相加、不将skip当成MySQL通过。最终合并后的精确组合结果见下一条。
- 最终合并组合回归：1836 passed、68.73 s（全部会话存储单元、五个会话CLI模块、database单元；无skip）；合并后extent/bundle/prefetch/parallel focused另为65 passed、0.52 s。
- 规格与tracker审计：权威spec未改；tickets01–09均resolved且无未完成验收checkbox；ticket10验收项完成，OpenSpec任务10/11关闭。严格OpenSpec校验与正常项目hooks通过，未push、未部署生产。

## 运维执行与恢复

1. 保留原有`prepare`及`migrate --apply`两步。准备前停写、冻结源输入，保留边界证据；in-place场景source/original/config/snapshot四根须相同，NAS独立。预检拒绝后先修复证据，不创建替代作业绕过检查。
2. 记录manifest、原始作业ID、代码SHA及资源参数。后续使用同一manifest执行`migrate --apply`；不要重新prepare、删除票据或手工改写已提交ID。旧票据与稳定身份仍有效。
3. 按source查看结果。`partial_success`/退出2只表示仍有失败source或待schema最终收口；不能视为所有source成功。已发布source可按准确tenant/source准入，失败者保持维护状态。修复失败source后原作业自动重审，已发布者不再读取旧输入或覆盖线上数据。
4. 数据库身份、命名锁丢失、未知COMMIT、共享IO或磁盘错误属于全局停止；保留失败报告并确认IO已排空，排查连接/代理/存储后沿原manifest恢复。不要自动重拿锁、扩大预算掩盖错误，或将共享故障改判为单source跳过。
5. 比较性能时保持输入、数据库实例、worker/IO/预算与延迟条件相同。同时看阶段墙钟、实际SQL/事务、bundle及持久化计数，不把累计等待相加，不将RSS采样或逻辑批量门面次数当作硬预算/实际SQL数。

批量业务写入/核对、身份分配、关联集合锁、bundle多块读取、source注册选择、重审归属索引及纯观测各为独立提交范围；出现回归时按对应提交及其后续修正依赖审查回退。回退代码前保留SQL票据与manifest，不改变schema、bundle格式、稳定ID或发布协议；生产旧镜像兼容性仍需独立现场验收。
