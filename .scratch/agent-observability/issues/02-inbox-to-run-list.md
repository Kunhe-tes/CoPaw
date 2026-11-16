# 02: 打通人工入库到授权Run列表的最小闭环

Status: claimed
Type: task
Blocked by: 01
Triage: ready-for-agent
Priority: P0

**What to build:** 用户仅需把契约JSON写入独立inbox，SWE即可校验并投影，授权运营人员能在独立Console入口看到对应Run列表与基本摘要；重复或乱序导入仍得到稳定结果。

**Blocked by:** 01：设计完整埋点契约并实现独立观测内核

**Status:** ready-for-agent

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [x] 交付独立MySQL连接配置、五表与索引的人工建表制品、最小INSERT说明和readiness检查；不回退业务/旧追踪连接，应用不自动CREATE/ALTER。
- [ ] 在已有人工作业约定的测试库验证设计目标版本的DDL；实际MySQL/TDSQL兼容性、字符集、二进制业务身份比较和索引长度有记录，不能只用静态解析宣称通过。
- [x] 独立应用生命周期任务以有界批次、READ COMMITTED和pending行领取机制投影；规范事件、派生状态及processed在同事务，固定run→attempt→span锁序，数据库故障可回滚重试。
- [x] 覆盖重复event_id、不同ID同槽、内容冲突、end先到、事件先于Span、晚提交小ingest_id、并发领取和崩溃重试；不使用MAX(id)永久水位，不因重复导入增加计数。
- [x] 无效载荷不能进入查询；立即清空可能违规payload并只留安全原因。合法事件规范化后仅在events保留一份，inbox留下处理记录；不增加按龄清理。
- [x] 独立API与Console列表显示Run、状态、业务锚点和质量；缺事实不伪造开始、Attempt序号或终态，全局健康事实不创建Run。
- [x] 所有数据入口沿用既有身份判定；manager限当前Source，admin显式跨Source，普通用户403，越界范围查询不可见；不通过ID或前端隐藏绕过鉴权。
- [x] 列表基础时间游标有版本、过滤/授权指纹和独立MAC；查询分页与超时有界，数据库不可用显示明确状态且不影响Agent业务；不开发日志采集器。
- [ ] 以样例人工写入完成数据库→投影→API→Console验收；当前未配置目标MySQL，必须在可用MySQL 8.0.21+环境完成实库DDL、并发投影与端到端验收。前端当前 Chromium 实测通过，但真实 Chromium 108/360 内核验收未执行；生产采集不在项目验收范围。

验收环境不可用时必须明确记录未验证项，不以构建成功或新浏览器模拟替代真实Chromium108验收。

## Answer

已实现独立 `SWE_AGENTOBS_DB_*` 配置、五表只读 readiness（校验关键列与索引定义）、READ COMMITTED 有界 inbox projector、白名单与 DDL 字段约束、幂等事件及Run/Attempt/Span投影、授权查询 API、签名稳定游标、Console Run 列表和生命周期连接关闭。子代理完成两轮只读代码检视，发现问题均已修复。

代码验证：`venv/bin/python -m pytest tests/unit/observability -q`（23 passed）；相邻后端回归（35 passed）；Console TypeScript、ESLint、4 项 Vitest 与生产 build 通过。Build 有既有 Rollup chunk/circular-dependency 体积警告。

环境限制：`SWE_AGENTOBS_DB_HOST` 未配置，Docker daemon 未运行，容器中没有 MySQL/MariaDB server，因此目标版本 DDL、锁/事务行为及人工 INSERT→投影→API 的实库验收未执行。浏览器在当前 Playwright Chromium 下通过 1280×720、390×844 和 `hideMenu=true` 视图；API 因本地没有 FastAPI 后端显示预期 unavailable 状态。Chromium 108/360 真机或匹配内核不可用，未作基线声明。

## Comments

2026-11-15：用户已确认15张票的拆分及阻塞关系，现发布为本地实施事项。尚未领取或开工；本次发布不构成功能开发授权。

2026-11-16：本轮用户目标明确授权 implement-spec。代码已提交交付；由于实库与基线浏览器验收环境缺失，本票保持claimed，待补齐环境验证后才能resolved。
