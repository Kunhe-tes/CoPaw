# 设计制品静态验证

日期：2026-11-15
范围：最终设计、Trace视图对照、过程决策、DDL草案、JSONL样例；仅分析与设计，未实施功能。

- 本地Markdown相对链接已检查可解析；视图原稿仍是用户提供的未跟踪输入，交付文档引用它时需一并纳入后续提交。
- 30条JSONL均可解析，event_id/生命周期槽唯一，UUID符合新ID格式，单条最大1535字节，小于24KiB；无正文或异常原文，安全字段静态检查通过。
- 两组样例涵盖正常Agent→LLM→Tool→LLM、技术错误后恢复、审批等待后同Run新Attempt、结束先到、缺父、未知Usage、精确NAS业务证据引用、增量事件/Link、后台子任务晚于Run结束。
- DDL仍为5张独立表；本轮增加6个字段、6个访问索引，无DROP/ALTER/DELETE/TRUNCATE，无TTL或清理逻辑，未执行SQL。
- 新增最宽显式索引为Source+Session+时间+Run，1580字节（另有变长/可空存储开销），低于设计基线3072字节；真实目标库兼容和查询计划仍待验证。
- 未修改src/、console/或业务运行配置；未提交或推送本轮修订。
- 同一Span的不可变身份/名称/父关系静态一致性通过；样例期望结构为首Run 1 Attempt/4 Span/0技术错误、次Run 2 Attempt/6 Span/1技术错误。本检查是fixture一致性检查，不是投影器运行测试。
- git diff --check通过。

静态检查不能代替MySQL/TDSQL建表/锁并发/EXPLAIN/容量、生产NAS权限/归档读取、真实Chromium108/当前浏览器交互以及业务挂点运行验收。生产日志采集不在项目范围。

## 2026-11-18 后端回归

- 使用项目虚拟环境运行观测核心、工具、技能、History 和 SubAgent 相关单测：688 passed；`git diff --check` 通过。pytest 对既有临时目录清理发出警告，不影响测试退出状态。
- 在用户提供的 MySQL 实例上新建随机隔离测试库并安装观测 DDL，运行 `tests/integrated/observability`、正文证据、超限鉴权与审批审计 MySQL 合同：34 passed。覆盖事件投影及授权 API、Runner、模型、工具、审批和已发布正文读取。
- 本轮观测库及会话测试控制库均已删除并查询确认不存在；会话测试的子库由 fixture 清理。未使用业务 schema。
- 这些结果仅覆盖现有测试合同，不代表已验证 TDSQL、生产 NAS 或完整业务场景。真实 Runner 审批拒绝/超时链路等后端缺口仍以各 issue 记录为准；页面开发与浏览器验收按用户要求暂停。
