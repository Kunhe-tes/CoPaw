请在当前 monitor 服务中新增一个“用户高频问题分析”模块，为后续 AI 智能工场工作流提供接口。

请先阅读项目现有目录结构、路由注册方式、数据库访问方式、请求/响应模型、统一返回格式和异常处理方式，严格复用现有项目规范，不要另起一套架构。

功能背景：
1. AI 智能工场会先调用取数接口，从 swe_tracing_traces 查询指定日期范围内的有效用户消息。
2. 工作流会调用大模型，对消息进行问题主题归纳并统计全机构、各 bbk_id 的 Top 10。
3. 工作流完成后，再调用结果保存接口，将结果批量写入 swe_high_frequency_question_result。
4. 本次只实现后端接口，不实现前端，也不在 monitor 服务中调用大模型。

建议在 monitor 服务中新增独立模块，例如：
- high_frequency_question
或遵循项目现有模块命名方式。

需要实现两个接口：

========================================
一、查询高频问题分析源消息
========================================

接口建议：

POST /monitor/high-frequency-question/messages

请求参数：

{
  "start_time": "2026-07-23 00:00:00",
  "end_time": "2026-07-30 00:00:00",
  "bbk_id": null
}

参数说明：
- start_time：必填，查询开始时间，包含。
- end_time：必填，查询结束时间，不包含。
- bbk_id：选填；为空时查询全部机构，有值时只查询该 bbk_id。
- 时间查询必须使用：
  start_time <= 消息时间 < end_time
- 校验 start_time < end_time。
- 建议限制查询时间跨度最大为 31 天，避免误调用产生超大查询。

数据来源：
swe_tracing_traces

请先检查 swe_tracing_traces 在当前项目中的 ORM Model、Mapper、DAO 或已有 SQL，确认以下字段的真实字段名，不要凭空创建字段：
- 消息唯一 ID
- 用户 ID
- 会话 ID
- bbk_id
- 用户消息内容
- 消息创建时间
- 消息角色或消息类型
- 定时任务标识、任务来源或能够排除定时任务消息的字段

查询要求：
1. 只查询用户发送的消息，不查询 assistant、system 等消息。
2. 排除定时任务产生的消息。
3. content 不能为 NULL，TRIM 后不能为空。
4. 过滤明显无意义的过短消息。
5. 优先使用项目中已经存在的定时任务识别逻辑；如果没有，请根据 swe_tracing_traces 的真实字段设计过滤条件，并在修改说明中明确说明。
6. 不要把所有长度较短的内容直接过滤掉，类似“查保险”“看持仓”等短文本仍可能是有效问题。
7. 可以过滤明确无意义的内容，例如“好的”“收到”“继续”“谢谢”等。
8. 按消息时间升序返回，保证输出稳定。
9. 当前约有 7 天 4000 条有效数据，MVP 可以一次返回，不需要分页；但请设置合理的最大返回数量，例如 10000 条，超过时返回明确错误，不要静默截断。

响应示例：

{
  "total": 4000,
  "data": [
    {
      "message_id": "msg_001",
      "user_id": "136807",
      "session_id": "session_001",
      "bbk_id": "110",
      "content": "帮我查询这个客户目前有哪些保险产品",
      "message_time": "2026-07-29 10:20:00"
    }
  ]
}

要求：
- 返回格式必须遵循 monitor 服务已有统一响应结构。
- 如果 user_id、session_id 或 bbk_id 在个别数据中允许为空，请按数据库实际情况处理，不要因为单条字段为空导致整个接口失败。
- content 不得在日志中完整打印，避免日志记录用户输入和潜在敏感信息。
- 日志只记录日期范围、bbk_id、查询数量和耗时。

========================================
二、批量保存高频问题分析结果
========================================

接口建议：

POST /monitor/high-frequency-question/results

请求示例：

{
  "batch_id": "HFQ_20260730_030000",
  "stat_start_time": "2026-07-23 00:00:00",
  "stat_end_time": "2026-07-30 00:00:00",
  "results": [
    {
      "scope_type": "ALL",
      "bbk_id": "ALL",
      "rank_no": 1,
      "topic_name": "查询客户保险持仓",
      "message_count": 520,
      "user_count": 210,
      "valid_message_count": 4000,
      "sample_questions": [
        "查询客户目前有哪些保险产品",
        "帮我看看客户买过什么保险"
      ]
    },
    {
      "scope_type": "ORG",
      "bbk_id": "110",
      "rank_no": 1,
      "topic_name": "生成客户营销话术",
      "message_count": 86,
      "user_count": 41,
      "valid_message_count": 525,
      "sample_questions": [
        "帮我给这个客户写一段营销话术"
      ]
    }
  ]
}

校验要求：
1. batch_id、stat_start_time、stat_end_time、results 必填。
2. stat_start_time 必须小于 stat_end_time。
3. results 不能为空。
4. scope_type 只允许 ALL、ORG。
5. scope_type=ALL 时，bbk_id 必须为 ALL。
6. scope_type=ORG 时，bbk_id 必须有实际值，且不能为 ALL。
7. rank_no 必须大于 0；MVP 建议限制在 1～10。
8. topic_name 不能为空，去除首尾空格后保存。
9. message_count、user_count、valid_message_count 不能小于 0。
10. message_count 不能大于 valid_message_count。
11. user_count 原则上不能大于 message_count。
12. sample_questions 最多保留 3～5 条，每条设置合理长度限制，例如 1000 字符。
13. 同一个 batch_id + scope_type + bbk_id + rank_no 不能出现重复数据。
14. 一次请求中的全部结果必须使用同一事务批量保存，任意一条失败则整体回滚。
15. 不要循环逐条提交数据库，使用项目现有批量插入方式。
16. 接口需要支持幂等重试。

幂等策略建议：
- 以 batch_id 作为一次完整预跑批次标识。
- 在同一个事务内，先删除该 batch_id 已有结果，再批量插入本次完整结果。
- 这样工作流因网络问题重试时不会重复插入。
- 不允许影响其他 batch_id 的历史数据。

响应示例：

{
  "batch_id": "HFQ_20260730_030000",
  "saved_count": 120
}

========================================
三、测试环境已有结果表结构
========================================

表名：

swe_high_frequency_question_result

表结构如下，请基于真实数据库类型和项目 ORM 规范建立对应 Model/Entity/Mapper，不要重新建表：

CREATE TABLE swe_high_frequency_question_result (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',

    batch_id VARCHAR(64) NOT NULL COMMENT '分析批次号，例如 HFQ_20260730_030000',

    stat_start_time DATETIME NOT NULL COMMENT '统计开始时间，包含',
    stat_end_time DATETIME NOT NULL COMMENT '统计结束时间，不包含',

    scope_type VARCHAR(16) NOT NULL COMMENT '统计范围：ALL-全部机构，ORG-单个机构',
    bbk_id VARCHAR(64) NOT NULL COMMENT '分行机构ID，全部机构统一保存为ALL',

    rank_no INT NOT NULL COMMENT '当前统计范围内的高频问题排名',

    topic_name VARCHAR(255) NOT NULL COMMENT '归纳后的高频问题主题',

    message_count INT NOT NULL DEFAULT 0 COMMENT '归入该主题的消息数量',
    user_count INT NOT NULL DEFAULT 0 COMMENT '归入该主题的去重用户数量',
    valid_message_count INT NOT NULL DEFAULT 0 COMMENT '当前统计范围内参与分析的有效消息总数',

    sample_questions JSON DEFAULT NULL COMMENT '代表性原始问题列表，JSON数组',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '结果生成并写入时间',

    PRIMARY KEY (id),

    UNIQUE KEY uk_batch_scope_rank (
        batch_id,
        scope_type,
        bbk_id,
        rank_no
    ),

    KEY idx_scope_latest (
        scope_type,
        bbk_id,
        created_at
    ),

    KEY idx_batch_id (
        batch_id
    ),

    KEY idx_stat_time (
        stat_start_time,
        stat_end_time
    )
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = '用户高频问题预跑结果表';

sample_questions 是 JSON 数组。请根据项目当前数据库框架选择正确处理方式：
- 如果 ORM 已支持 JSON 类型，直接映射为 List<String> 或项目常用 JSON 类型。
- 如果当前项目通常使用字符串保存 JSON，则实体中按 String 处理，并在接口 DTO 与数据库 Entity 之间进行序列化和反序列化。
- 不要为了该字段额外引入重量级依赖。
-- rmassistdata.swe_tracing_traces definition

CREATE TABLE `swe_tracing_traces` (
  `trace_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '追踪唯一标识，UUID格式',
  `b3_trace_id` varchar(64) DEFAULT NULL,
  `source_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '数据源标识，用于多租户数据隔离',
  `user_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '用户标识，发起请求的用户ID',
  `user_name` varchar(20) DEFAULT NULL COMMENT '用户姓名',
  `bbk_id` varchar(10) DEFAULT NULL COMMENT '分行编号',
  `session_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '会话标识，同一会话的多次请求共享此ID',
  `session_name` varchar(100) DEFAULT NULL COMMENT '会话名称',
  `channel` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '通道来源，如 console/webhook/api 等',
  `start_time` datetime(3) NOT NULL COMMENT '追踪开始时间，用户请求发起时刻',
  `end_time` datetime(3) DEFAULT NULL COMMENT '追踪结束时间，请求完成时刻',
  `duration_ms` int DEFAULT NULL COMMENT '总耗时（毫秒），从开始到结束的时长',
  `model_name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '主要使用的模型名称，如 gpt-4/claude-3',
  `total_input_tokens` int DEFAULT '0' COMMENT '输入Token总数，所有LLM调用的输入累计',
  `total_output_tokens` int DEFAULT '0' COMMENT '输出Token总数，所有LLM调用的输出累计',
  `total_tokens` int DEFAULT '0' COMMENT 'Token总数，等于输入+输出',
  `tools_used` json DEFAULT NULL COMMENT '使用的工具列表，JSON数组格式',
  `skills_used` json DEFAULT NULL COMMENT '使用的技能列表，JSON数组格式',
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT 'running' COMMENT '追踪状态：running/completed/error/cancelled',
  `error` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci COMMENT '错误信息，失败时记录的错误描述',
  `user_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci COMMENT '用户输入消息，截断后的摘要内容',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `start_date` varchar(20) DEFAULT NULL COMMENT '数据日期',
  PRIMARY KEY (`trace_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_model_name` (`model_name`),
  KEY `idx_session_id` (`session_id`),
  KEY `idx_source_start_time` (`source_id`,`start_time`),
  KEY `idx_source_user` (`source_id`,`user_id`),
  KEY `idx_source_session` (`source_id`,`session_id`),
  KEY `idx_user_name` (`user_name`),
  KEY `idx_bbk_id` (`bbk_id`),
  KEY `idx_user_source_time_name` (`user_id`,`source_id`,`start_time` DESC,`user_name`),
  KEY `idx_source_start_date` (`start_date`),
  KEY `idx_source_start_user` (`source_id`,`start_time`,`user_id`,`session_id`),
  KEY `idx_source_date_user` (`source_id`,`start_date`,`user_id`,`session_id`),
  KEY `idx_source_id` (`source_id`),
  KEY `idx_start_time` (`start_time`),
  KEY `idx_source_b3_trace` (`source_id`,`b3_trace_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
========================================
四、代码结构要求
========================================

请根据 monitor 服务现有架构增加完整代码，包括但不限于：

1. 路由或 Controller
2. 请求 DTO
3. 响应 DTO
4. Service 接口及实现
5. Repository、Mapper 或 DAO
6. swe_high_frequency_question_result 对应 Entity/Model
7. 从 swe_tracing_traces 查询消息所需的 SQL 或 Mapper 方法
8. 批量删除同 batch_id 旧数据的方法
9. 批量插入结果的方法
10. 参数校验
11. 事务控制
12. 必要日志
13. 单元测试或至少提供可执行的接口测试样例

命名建议：
- HighFrequencyQuestionController
- HighFrequencyQuestionService
- HighFrequencyQuestionServiceImpl
- HighFrequencyQuestionResult
- HighFrequencyQuestionMessageQueryRequest
- HighFrequencyQuestionMessageResponse
- HighFrequencyQuestionResultSaveRequest

但必须优先遵循当前项目已有命名风格。

========================================
五、实现边界
========================================

本次不要实现：
- 前端页面
- 定时任务
- 大模型调用
- Prompt
- 高频主题归类
- Top 10 计算
- 查询前端展示结果的接口
- 长期主题库

monitor 服务本次只负责：
1. 从 swe_tracing_traces 提供干净的源消息。
2. 接收 AI 工作流生成的结果并写入结果表。

========================================
六、代码质量要求
========================================

1. 不要修改无关代码。
3. 优先复用已有 Trace Model、Mapper 和查询逻辑。
4. SQL 参数必须使用参数绑定，禁止字符串拼接，避免 SQL 注入。
5. 时间字段使用项目统一的时间类型和序列化格式。
6. 写入接口必须有 @Transactional 或项目等价事务机制。
7. 批量保存失败时必须回滚。
8. 对重复 batch_id 支持安全重试。
9. 日志不要输出完整消息正文和 sample_questions。
10. 请在完成后列出：
   - 新增和修改了哪些文件
   - 两个接口的路径
   - swe_tracing_traces 实际使用了哪些字段
   - 定时任务消息的具体过滤条件
   - 幂等和事务如何实现
   - curl 或 Postman 测试示例
   - 当前仍需人工确认的字段或业务规则

请先分析代码，再直接完成实现，不要只给方案或伪代码。