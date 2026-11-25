# 会话元数据迁移功能修复方案

评审稿，代码基线为 `ac01ecaa3`。范围涵盖完整审计、重审续跑、恢复快照校验，以及招乎和草稿 Chat 两条线上行为。验收数据使用会话元数据与 NAS 正文，沿用 ADR 0049 的来源独立发布和 ADR 0050 的可选完整审计。此前历史读取异常遗留 reader pin 的路径已修复，现有故障注入用例作为回归保留。[来源发布 ADR](../../adr/0049-conversation-migration-publishes-sources-independently.md) · [快速校验 ADR](../../adr/0050-conversation-migration-uses-fast-structural-verification.md) · [reader pin 回归](../../../tests/unit/app/conversation_storage/test_history.py)

## 1. 完整审计必须报告实际覆盖

**根因。** 来源选择统一跳过 `published`，结果却直接从命令选项填入 `verification_level=full`。所有来源已发布且 schema 已收口时，零覆盖依然可以报成功。已有线上写入的来源，其当前恢复指针、历史水位和 Chat 也可能合法变化，因此直接对当前业务行运行原离线比较会产生误报。[来源选择与结果](../../../src/swe/cli/conversation_storage_tenants.py)

**设计。** `verify --full-audit` 继续对 `imported`、`verified` 来源执行冻结源与导入结果的完整比较。报告列出请求、实际执行、通过、失败和跳过的来源及原因。空覆盖返回明确的未完成状态和非零退出码，混合覆盖返回部分完成。已发布来源若有此前的完整审计凭据，展示其 revision 和结果作为历史记录。审计结果与 DBA schema 收口状态分别反映。仅写入本次实际跑过的验证结果，已发布来源的状态和准入凭据遵守其现有不可变约束。

增加可选的 `migrate --apply --full-audit`，让希望一次命令完成的操作者在每个来源发布前执行快速校验和完整审计，两者成功后再执行现有的最终源复查和发布。已上线来源如需重新做冻结基线比较，覆盖范围取决于事先保留的完整迁移时点目标快照和原冻结源，核验在隔离副本执行。常态在线健康检查使用当前数据的版本和引用一致性。

**验收。** 覆盖全未发布、部分已发布、全部已发布、全部已发布且已收口四种组合。核对每个来源的实际读取次数、结果与退出码。完整审计发现正文不一致时，对应来源保持未发布。已发布来源合法追加会话时，历史审计凭据与本次执行结果各自可辨。

## 2. 部分发布后的重审与中断恢复

**根因。** `prepare` 的 `manifest-v1` 工作区可以没有 `counts`，冻结副本重审分支却依赖该字段构造占位结果。重审在 SQL 提交前写入 pending，而同协议的 CLI 入口跳过 pending 恢复。该协议的旧、新 SQL source binding 文本还可能相同，单凭绑定文本无法确定本地文件属于哪次修订。[prepare](../../../src/swe/cli/conversation_storage_workflow_cmd.py) · [重审与恢复](../../../src/swe/app/conversation_storage/migration/tenant_retry.py)

**设计。** 冻结副本和原地模式都先用已登记的完整来源身份剔除已发布来源，再对未发布候选重发现。对提交的重审材料中涉及已发布来源的映射、覆盖规则和服务绑定执行元数据比对，通过后将既有工作区映射及冻结证据原样并回结果。继续校验重复归属。已发布来源证据的保留独立于计数，`counts` 缺省按未知处理。重审仅更改处于 `discovered` 或 `failed` 且经 SQL 验证无已导入业务行及相关票据的来源。保留原有 SQL owner、锁和 CAS。

在持锁的可写入口，先恢复 pending，再校验正常作业绑定和注册来源。只读预览可提示存在待恢复修订。新 pending 记录旧、新数据库修订号、变更来源的旧/新状态及证据、旧/新 manifest 快照摘要。恢复按下表处理，并校验当前本地 manifest 属于该次修订的旧或新快照。历史 pending 缺少旧修订号时，使用现存审计记录和来源证据确证旧态。证据不足则保留 pending 并报结果未知。

| SQL 观察结果 | 恢复动作 |
| --- | --- |
| 旧修订号及全部变更来源的旧状态、旧证据匹配 | 原子恢复旧 manifest，保留旧态审计记录，允许重新重审 |
| 新修订号及全部变更来源的新状态、新证据匹配 | 原子安装新 manifest，保留新态审计记录，允许续跑 |
| 混合状态、外部修订或证据损坏 | 保留 pending 和快照，报告冲突，等待证据对账 |

**验收。** 用真实 `prepare` 输出，无 `counts` 的 A 已发布、B 失败，分别在冻结副本和原地模式修订 B。验证 A 的状态、证据及业务写入完整保留。注入 pending 已落盘但 SQL 未提交、SQL 提交成功但响应丢失、本地快照替换后未归档三类故障，重复执行恢复并核对结果一致。篡改快照摘要、修订号或单条来源证据时，保留待恢复材料。

## 3. 恢复快照格式与旧 bundle 续跑

**根因。** 当前快速验证强制读取 `message_body_hashes`，旧版本已经持久化的 bundle 缺少此块时，导入重放和快速验证都可能拒绝。恢复记录校验覆盖目录与正文摘要，但缺少线上恢复投影的格式和结构校验。本地已重现缺摘要块被拒，以及缺 `format` 标记通过 fast、线上读取返回空历史。[已提交 bundle 比较](../../../src/swe/app/conversation_storage/migration/install_records.py) · [快速验证](../../../src/swe/app/conversation_storage/migration/verify_fast.py) · [线上恢复投影](../../../src/swe/app/conversation_storage/session_projection.py)

**设计。** 抽取线上 hydrate 已有的投影结构校验，供离线验证复用。验证格式、版本、核心字段与类型、列表目标路径和引用形状。继续检查完整 scope、Session、locator、occurrence、最终水位和批次顺序。结构校验可直接使用投影内容，正文引用仍由既有的批次验证检查。

重放已有 publication 时，先按稳定 operation key、SQL locator、import plan 和原有块核验，沿用现有 ID、票据和 NAS 文件。带摘要块的 publication 沿用严格摘要核验。对确认为既有已提交或已确认持久化的旧版 publication，兼容条件限定为缺少这个新增块，其余块和契约逐项匹配。若既有凭据没有独立的格式版本，要求有相符的既有票据和冻结输入参与对照，不能仅凭缺块判定为旧版。对缺摘要的 Session，从同一作业冻结输入重建规范化正文证据，按 occurrence 逐条比较持久化块。通过同一套旧格式判定覆盖已提交、已持久化未提交和独立 verify，冻结证据缺失或任何一项不一致时明确报失败。新生成的 publication 继续写入摘要块。该设计只涉及正确性，采用现有校验资源配置。

**验收。** 同一个 manifest 分别使用旧提交生成已持久化未提交、部分提交、全部已导入未发布的 bundle，切到新版续跑，核对 operation key 和 SQL ID。覆盖正确的旧格式、任意旧块篡改、缺少冻结源、恢复格式缺失、未知版本、错位引用、重复 occurrence 和缺摘要的新版输入。核对置信条件不足时无法进入发布。

## 4. 招乎活动 Session 与草稿 Chat

### 招乎活动指针

**根因。** 招乎把活动会话 ID 写入独立的 `zhaohu:active:{sap_id}` Session。v3 清单在 Chat 权威模式从 Chat 注册表选 Session，连单独配置的无 Chat Session 路径也会跳过。上线后 SQL 读到空状态，用户会走默认会话解析。[招乎读写](../../../src/swe/app/channels/zhaohu/channel.py) · [Session 清单](../../../src/swe/app/conversation_storage/migration/inventory.py)

**设计。** 支持明确声明的招乎活动 Session，从可信工作区映射取得来源、Agent、用户和实际 Session adapter 使用的 channel。优先复用已审核的 `session_paths`，发现端可从可信用户映射生成候选，清单仅接受与该用户匹配的保留 ID 和规范路径。将该文件纳入现有冻结输入覆盖与最终来源复查。借用现有 Session 恢复发布迁移 `active_session_id`，保留目录为空的合法状态。指针的目标 Chat 必须属于同一 scope、用户和招乎通道。空指针或已删除目标沿用清除状态及默认会话行为。目标来自其他范围、路径冲突或身份无法证明时报告来源阻断。线上继续用既有 SQL Session adapter 读写。

**验收。** 用真实旧 Session writer 保存由 `/new` 产生的非默认指针，完成 `prepare → migrate → 招乎读取`，核对继续命中原目标。覆盖同名用户跨来源、目标已删除、空指针、显式路径及冲突路径。

### 草稿 Chat 改绑

**根因。** create-if-absent 把 `draft_chat_id` 当作唯一性和重试凭据。Chat 改绑后原指针仍在，但它指向另一个 Session。后续创建按既有完整性规则拒绝。已删除草稿的指针另有明确的幂等语义。[草稿指针写入与改绑](../../../src/swe/app/conversation_storage/chat_mutations.py) · [草稿读取](../../../src/swe/app/conversation_storage/chat_repository.py)

**设计。** 选择在事务内拒绝改绑仍被原 Session 指定为草稿的 Chat。普通 Chat 继续使用现有改绑能力。用已持锁的源 Session 和 Chat ID 检查，在更新 Chat 前返回清晰的冲突原因。抢占草稿与改绑并发时，沿用 Session 串行化和 metadata revision。已存在的漂移先由只读一致性查询定位。单独修复时须依据已提交的改绑记录确认原指针的归属，再由受控事务处理。批量清空指针会同时移除历史幂等凭据。

这项选择收紧了指定草稿的改绑行为，换取在现有 schema 下保留 create-if-absent 语义。如果产品要求指定草稿也能成功改绑，需先定义原创建请求重试及目标 Session 已有草稿时的行为，再评估新增持久身份记录。

**验收。** 覆盖普通 Chat 改绑、指定草稿改绑、与草稿创建并发、删除后重复创建及同一操作重试。检查拒绝路径的 Chat、两端 Session、publication 和 NAS 引用状态。构造既有漂移，验证只读检查报告准确。

## 实施顺序和验证边界

先修审计报告和发布前入口，再交付重审恢复与旧 bundle 兼容。最后分别交付招乎独立 Session 和草稿改绑保护。各增量在正常 CLI 或线上入口加回归。真实 MySQL 重点验收重审提交响应丢失、bundle 已持久化未提交和并发改绑，NAS 使用隔离根。当前评审证据来自源码、已有本地复现和 95 项通过的现有单测，现场 MySQL 和 NAS 演练结果待实施后记录。
