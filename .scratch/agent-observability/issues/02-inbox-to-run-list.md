# 02: 打通人工入库到授权Run列表的最小闭环

Status: resolved
Type: task
Blocked by: 01
Triage: ready-for-agent
Priority: P0

**What to build:** 用户仅需把契约JSON写入独立inbox，SWE即可校验并投影，授权运营人员能在独立Console入口看到对应Run列表与基本摘要；重复或乱序导入仍得到稳定结果。

**Blocked by:** 01：设计完整埋点契约并实现独立观测内核

**Status:** resolved

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [x] 交付独立MySQL连接配置、五表与索引的人工建表制品、最小INSERT说明和readiness检查；不回退业务/旧追踪连接，应用不自动CREATE/ALTER。
- [x] 在已有人工作业约定的测试库验证设计目标版本的DDL；实际 MySQL 8.0.46、utf8mb4、16KiB 页、strict mode、二进制业务身份列与索引创建已实测；TDSQL 兼容性未在本轮环境验证。
- [x] 独立应用生命周期任务以有界批次、READ COMMITTED和pending行领取机制投影；规范事件、派生状态及processed在同事务，固定run→attempt→span锁序，数据库故障可回滚重试。
- [x] 覆盖重复event_id、不同ID同槽、内容冲突、end先到、事件先于Span、晚提交小ingest_id、并发领取和崩溃重试；不使用MAX(id)永久水位，不因重复导入增加计数。
- [x] 无效载荷不能进入查询；立即清空可能违规payload并只留安全原因。合法事件规范化后仅在events保留一份，inbox留下处理记录；不增加按龄清理。
- [x] 独立API与Console列表显示Run、状态、业务锚点和质量；缺事实不伪造开始、Attempt序号或终态，全局健康事实不创建Run。
- [x] 所有数据入口沿用既有身份判定；manager限当前Source，admin显式跨Source，普通用户403，越界范围查询不可见；不通过ID或前端隐藏绕过鉴权。
- [x] 列表基础时间游标有版本、过滤/授权指纹和独立MAC；查询分页与超时有界，数据库不可用显示明确状态且不影响Agent业务；不开发日志采集器。
- [x] 以样例人工写入完成数据库→投影→API→Console验收；隔离 MySQL 8.0.46 库的集成测试验证 inbox→投影→授权 API，Chromium 108.0.5359.29 的 1280×720、390×844 与 `hideMenu=true` 页面显示实测 Run；390×844 无页面级横向溢出，表格在内部滚动。目标补丁版本 108.0.5359.95 与 TDSQL 变体未实测；生产采集不在项目验收范围。

验收环境不可用时必须明确记录未验证项，不以构建成功或新浏览器模拟替代真实Chromium108验收。

## Answer

已实现独立 `SWE_AGENTOBS_DB_*` 配置、五表只读 readiness（校验关键列与索引定义）、READ COMMITTED 有界 inbox projector、白名单与 DDL 字段约束、幂等事件及Run/Attempt/Span投影、授权查询 API、签名稳定游标、Console Run 列表和生命周期连接关闭。子代理完成两轮只读代码检视，发现问题均已修复。

代码验证：`venv/bin/python -m pytest tests/unit/observability -q`（23 passed）；`tests/integrated/observability/test_mysql_pipeline.py` 在远端 MySQL 8.0.46 测试库通过；相邻后端回归（35 passed）；Console TypeScript、ESLint、4 项 Vitest 与生产 build 通过。Build 有既有 Rollup chunk/circular-dependency 体积警告。

环境限制：实库使用用户提供连接，在隔离 `swe_agentobs_codex_20261116_test` 库执行；未修改业务库。DDL 与投影验证通过 MySQL 8.0.46，不代表目标 TDSQL 变体已兼容。浏览器使用真实 Chromium 108.0.5359.29 验收，现场要求的 108.0.5359.95 补丁版未取得。完整 SWE app 因当前虚拟环境缺少既有依赖 `trace_sdk` 未能启动；Console 验收通过连接隔离测试 API 与实库完成。

## Comments

2026-11-15：用户已确认15张票的拆分及阻塞关系，现发布为本地实施事项。尚未领取或开工；本次发布不构成功能开发授权。

2026-11-16：实现、隔离 MySQL 8.0.46 集成验证、授权 API 与 Chromium 108 页面验收完成，本票 resolved。Chromium 108.0.5359.95、TDSQL 变体和完整 SWE app（缺少 `trace_sdk`）未验证。
