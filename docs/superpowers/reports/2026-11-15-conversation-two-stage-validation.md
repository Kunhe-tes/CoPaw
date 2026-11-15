# 会话迁移两阶段实现验证

日期：2026-11-15。工作树：`.worktrees/conversation-mysql-nas`。用户已确认 `prepare` 与 `migrate --apply` 两阶段、失败租户自动重审、正常租户校验后自动发布、部分成功退出 2。

## 实现与回归范围

- 未收敛旧 Turn 与源变化使用明确租户输入异常；不笼统捕获 ValueError、SQL 或权威完整性错误。
- 隔离 freeze 按租户复核，失败租户详情变化不再要求全报告相等；原正常租户变化标失败，服务身份、账号覆盖及未知 workspace 仍保护。严格旧模式保持原契约。
- 正常输入新增 SHA-256 内容摘要，只枚举固定会话入口、精确身份文件及分享正文；摘要读取前后校验文件身份。旧清单无摘要时保留原鲜度契约。
- prepare 复用发现、冻结核验和只读 preflight，不导入业务行、不发布；migrate 自动重审此前失败组，同一次执行不自动接受新失败组的变化。
- 已有业务行/票据的失败组保留证据，摘要与所有权通过才可尝试原样续跑；无摘要或内容变化保守拒绝。零数据、零票据才允许修订证据。
- 准备/重审按租户有界解析与摘要；执行采用至多 workers-1 个租户只读预取与单 owner 导入/校验流水线，公用 IO 池，workers=1 无跨租户预取。不是跨租户并发数据库事务。配置发现、覆盖扫描和全局一致性校验仍有串行边界。
- 独立复核补充了预取后导入前摘要复查、最终盘点借用共享 IO、取消期间 spool 清理、有票据原失败组的续跑门禁。

## 验证记录

- 完整单元与 CLI 回归一次：1579 passed in 57.74s，日志 `/tmp/conversation-workflow-final-full.log`。质量整理与新增边界用例后最终完整回归：1585 passed in 55.57s，日志 `/tmp/conversation-workflow-delivered.log`。
- 真实 MySQL 两阶段场景：prepare 隔离 B，migrate 发布 A/C；A 在线修改配置、增加 Agent、增加 SQL chat 后修复 B，再次 migrate 自动重审并发布 B，A/C 不重读且新数据保留。一次 1 passed in 54.01s，补跑 1 passed in 50.82s，最终补跑日志 `/private/tmp/tenant-workflow-mysql-final-4.log`。
- 测试只使用随机专用 schema 和本地目录；最终扩展矩阵和准确清理结果另行追加。首次测试配置重导出 mock 不完整导致一次分享集合只读查询走部署配置，随后显式指定空分享 fixture 并同时替换两个配置入口；未执行应用库 DDL、业务写入或清理。

### 最终 MySQL 矩阵

`test_tenant_workflow_mysql.py` 三场景真实运行：3 passed in 158.29s，日志 `/private/tmp/tenant-workflow-mysql-matrix.log`。覆盖配置失败、真实 running Turn 导入拒绝、准备后会话字节变化且保留 mtime。每个场景首轮均允许 A/C 发布，修复 B 后再次 migrate 自动补迁；A 在线配置、新 Agent 和 SQL 新数据保持不变。字节变化场景首轮 B 未产生 Session 行，且未出现带 B scope 的票据；这是该运行的实际断言范围。

本轮准确登记的一个父测试库及三个子测试库逐名查询后均不存在，`remaining=[]`、`cleanup_verified=true`；证据 `/private/tmp/tenant-workflow-mysql-matrix-cleanup.json`。没有根据模糊前缀枚举或清理其他库。

## 验收边界

所有本轮 src/tests 改动通过 pre-commit（含 mypy、Black、flake8、pylint），`git diff --check` 通过。测试退出时存在 pytest 旧临时 garbage 目录清理警告，测试退出码为 0；未为消除警告删除历史目录。

未进行真实 NAS、万级容量/性能或固定旧镜像回滚验收。CLI 不停止旧 writer、不自动恢复文件权限、不部署新版、不开放入口。现场必须具备真实停写/备份证据、独立 NAS 与未发布输入只读保障；无双写或增量追赶。

全部租户发布后仍须 DBA 执行专用 schema 收口；等待收口可返回 partial_success，即使 failed 为 0。共享数据库/锁/EIO/空间耗尽/未知提交/程序错误仍停止调用，保留断点。

本机真实包启动历史上缺少 trace_sdk；测试环境使用既有测试替身。实际发布镜像必须独立通过无测试替身的 CLI help 与启动验收，不能将测试替身加入生产 PYTHONPATH。

## 提交后独立代码检视

以 `b511f1d6e` 为基线启动三路子代理，分别核查租户失败隔离、并发资源生命周期和 CLI/审计契约。检视发现并修复：

- 非法 Session revision、消息时间戳等明确旧输入错误仍可能以普通异常退出整批；改为 SQL 前明确校验和 `TenantInputError`，保留共享 SQL、权威及程序错误的致命语义。新增坏租户失败后后续正常租户继续执行的回归。
- prepare 的相邻 discovery 副件此前保存首次发现结果，可能与冻结复核后的失败状态矛盾；改为保存冻结报告字段。
- 空服务能产生零租户作业，随后注册访问首租户触发 IndexError；prepare 及注册入口均明确拒绝空租户任务。
- 预取完成后保留最后一个解码 workspace 缓存；交给 owner 前释放该缓存，消费时仍可从 spool 重读。分享列表及摘要仍驻内存，解析预算不代表进程 RSS 硬上限，操作手册已说明。

最终稳定代码完整子系统与 CLI 回归：**1604 passed in 55.72s**，日志 `/private/tmp/conversation-review-final.log`。本轮修复文件全部 pre-commit 检查通过，日志 `/private/tmp/conversation-review-hooks-final.log`。本轮检视和修复仅使用本地测试，未重新连接或修改数据库，也未执行生产迁移。
