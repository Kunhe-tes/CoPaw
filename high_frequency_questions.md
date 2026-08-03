请帮我在现有 Python Monitor 服务中补充“用户高频问题分析”的异步任务管理、缓存复用和结果查询逻辑。

请先阅读项目中现有的高频问题相关接口、Service、DAO/Repository、工作流调用代码，以及 swe_async_tasks 的已有使用方式。保持当前 Python 框架、分层结构、数据库访问方式、异步执行方式和编码风格，尽量做最小改动，不要按 Java 项目的方式实现。

一、现有业务背景

高频问题工作流的输入参数主要包括：

- source_id：前端传入的字符串，例如 RMASSIST、default
- start_time
- end_time
- bbk_id：选填

source_id 是真实的数据来源标识，必须原样保存和使用，不能改造成筛选条件编码。

用户只能查询和查看自己当前 source_id 下的数据。

因此，无论查询缓存、查询历史结果，还是判断重复运行任务，都必须将 source_id 作为匹配条件。

不同 source_id 之间不能复用结果。例如：

- source_id=RMASSIST
- source_id=default

即使日期和机构相同，也必须视为两组独立结果。

机构规则：

- bbk_id 为空时：
  - scope_type = ALL
  - bbk_id = ALL
- bbk_id 非空时：
  - scope_type = ORG
  - bbk_id = 前端传入的真实机构 ID

工作流是同步接口：

1. 调用 /message 接口读取数据
2. 完成高频问题分析
3. 调用 /result 接口写入 swe_high_frequency_question_result
4. 只有结果写库完成后，工作流接口才返回成功

swe_async_tasks.task_id 与 swe_high_frequency_question_result.batch_id 使用同一个值。

异步任务状态只使用：

- RUNNING
- SUCCEEDED
- FAILED

不需要 PENDING。

二、日期处理

数据库表中的 stat_start_time 和 stat_end_time 保持 DATETIME 类型，不修改表结构。

业务上判断相同条件时，只比较日期，不比较具体时分秒。

相同条件定义为：

- source_id 相同
- start_time 的日期相同
- end_time 的日期相同
- scope_type 相同
- bbk_id 相同

前端选择的日期范围最长不能超过 7 天。

请优先在 Python 代码中将 datetime 转换为 date，或者计算对应自然日的时间边界进行范围查询，不建议在数据库字段上直接使用 DATE(column)，避免索引失效。

例如前端选择：

- start_date = 2026-07-28
- end_date = 2026-08-03

缓存匹配时只需要识别为同一组日期条件。

实际读取消息时，请沿用项目当前的时间范围口径，不要擅自改变 /message 接口现有的包含关系。如果当前使用闭区间或左闭右开，请保持一致，并在代码注释中说明。

三、提交任务接口

新增或完善高频问题分析任务提交接口。

收到请求后依次执行：

1. 校验 source_id 不能为空。
2. 校验开始时间和结束时间合法。
3. 校验日期范围最长不超过 7 天。
4. 规范化机构：
   - bbk_id 为空：scope_type=ALL，bbk_id=ALL
   - bbk_id 非空：scope_type=ORG，bbk_id=原始值
5. 查询最近 24 小时内是否存在相同条件的成功结果。

成功结果匹配条件：

- source_id 相同
- 开始日期相同
- 结束日期相同
- scope_type 相同
- bbk_id 相同
- 结果表 created_at 在最近 24 小时内

如果存在，直接返回最新一批结果及 batch_id，不创建异步任务，也不重新调用工作流。

6. 如果没有可复用结果，检查是否存在相同条件的 RUNNING 任务。

RUNNING 任务匹配条件同样是：

- source_id 相同
- 开始日期相同
- 结束日期相同
- scope_type 相同
- bbk_id 相同

如果存在，直接返回已有 task_id，不能重复提交。

7. 如果既没有可复用结果，也没有运行中任务：
   - 生成 task_id
   - 将 task_id 同时作为工作流 batch_id
   - 插入 swe_async_tasks，状态为 RUNNING
   - 将同步工作流调用放入项目已有的后台任务机制或线程池中执行
   - 提交接口立即返回 task_id 和 RUNNING，不能让前端请求等待整个工作流执行完成
工作流调用接口：curl --location --request POST 'http://aplus-gateway.paasuat.cmbchina.cn/openapi/runtime/app/07c1cda53/tag/dev/workflow/run/WF543tVbDE' \
  --header 'API-Key: 22a74901e4d64da98847cbe8cdb7c528' \
  --header 'Content-Type: application/json' \
  --data-raw '{"inputParams":{"source_id":"","start_time":"","end_time":"","bbk_id":""，"batch_id":""},"openId":"8379AE437A0A3EAB9D610725B0725F21","responseMode":"noStreaming"}'工作流返回结果：{"message":"success"}目前还不知道怎么判断异常了是否会返回报错信息


四、筛选条件如何与 async 任务关联

swe_async_tasks 表没有独立的 start_time、end_time、scope_type、bbk_id 字段。

source_id 字段必须保存前端传入的真实 source_id，例如 RMASSIST，不能用它拼接日期和机构。

请先检查项目中 swe_async_tasks.result_json 或其他已有字段的使用约定。

建议在任务创建时，把本次请求条件保存到 result_json 中，例如：

{
  "request": {
    "source_id": "RMASSIST",
    "start_date": "2026-07-28",
    "end_date": "2026-08-03",
    "scope_type": "ORG",
    "bbk_id": "110"
  }
}

任务成功后更新 result_json 时，应保留 request，并补充 result，例如：

{
  "request": {
    "source_id": "RMASSIST",
    "start_date": "2026-07-28",
    "end_date": "2026-08-03",
    "scope_type": "ORG",
    "bbk_id": "110"
  },
  "result": {
    "batch_id": "xxx",
    "result_count": 10
  }
}

如果项目当前数据库版本不适合高效查询 JSON 字段，请结合现有代码给出最小改动方案，但不能篡改 source_id 的业务含义。

不要通过解析 title 或 summary 判断相同条件。

五、创建 swe_async_tasks

创建任务时写入：

- task_id：生成的任务 ID
- service：monitor
- task_type：monitor.high.freq.question
- status：RUNNING
- title：用户高频问题分析
- summary：可读的日期范围和机构说明
- source_id：前端原样传入的 source_id，例如 RMASSIST
- actor_user_id：当前操作人 ID；定时任务使用 SYSTEM
- actor_user_name：当前操作人名称；定时任务使用 系统定时任务
- target_count：1
- done_count：0
- failed_count：0
- error_message：NULL
- result_json：保存规范化后的请求筛选条件
- finished_at：NULL

actor_user_id 仅用于审计，不能作为缓存复用或重复任务判断条件。

同一 source_id 下的所有用户共享相同筛选条件的分析结果。

六、后台调用工作流

后台任务中同步调用工作流，并传入：

- source_id
- task_id
- batch_id，值与 task_id 相同
- start_time
- end_time
- bbk_id

调用成功的前提是：

- 工作流已完成分析
- /result 接口调用成功
- swe_high_frequency_question_result 已完成写库

成功后更新 swe_async_tasks：

- status = SUCCEEDED
- done_count = 1
- failed_count = 0
- error_message = NULL
- finished_at = 当前时间
- result_json 保留 request，并补充 batch_id、result_count 等结果信息

调用异常时，不要立即无条件标记失败。

先根据 batch_id=task_id 查询 swe_high_frequency_question_result 是否已经存在结果：

- 如果结果已存在，说明可能只是工作流返回阶段发生网络异常，将任务更新为 SUCCEEDED
- 如果结果不存在，将任务更新为 FAILED

FAILED 状态字段：

- status = FAILED
- done_count = 0
- failed_count = 1
- finished_at = 当前时间
- error_message = 截断后的安全错误摘要

不要把完整用户消息、Prompt、模型输出或敏感数据写入 error_message。

七、事务要求

不要使用一个长事务包住以下全过程：

- 插入 RUNNING
- 调用工作流
- 更新最终状态

工作流可能执行数分钟，不能长期占用数据库事务。

应拆分为短事务：

1. 创建 RUNNING 任务
2. 在事务外调用工作流
3. 单独更新 SUCCEEDED 或 FAILED

八、并发去重

需要防止两个用户几乎同时提交相同条件时创建两个任务。

请结合当前数据库访问方式实现并发保护。

相同条件包括：

- source_id
- start_date
- end_date
- scope_type
- bbk_id

优先复用项目已有的锁、事务、唯一性控制或任务创建方法。

如果现有表结构无法通过唯一索引保证，请在代码中实现二次检查，并明确说明仍然可能存在的极小并发窗口，不要修改数据库表结构。

九、默认凌晨预跑

每天凌晨定时生成：

- source_id：由定时任务配置明确传入，不能默认跨 source_id 生成
- 最近 7 天
- scope_type = ALL
- bbk_id = ALL
- actor_user_id = SYSTEM
- actor_user_name = 系统定时任务

不同 source_id 需要分别配置定时任务或分别调用提交方法。

凌晨预跑也复用同一套任务提交、缓存检查和状态更新逻辑，不维护第二套实现。

十、结果查询接口

前端查询时必须传入 source_id，并且只能返回该 source_id 下的数据。

按以下优先级返回：

1. 最近 24 小时内，相同 source_id、日期和机构条件的最新成功结果
2. 相同条件正在运行的 RUNNING 任务
3. 最新任务失败，但存在更早成功结果时：
   - 返回更早成功结果
   - state = AVAILABLE_STALE
   - message = 最近一次更新失败，当前展示历史结果
4. 没有结果也没有任务时：
   - state = EMPTY

成功结果返回：

- task_id
- batch_id
- status/state
- source_id
- stat_start_time
- stat_end_time
- scope_type
- bbk_id
- result_updated_at
- topics

result_updated_at 取同一 batch_id 下：

MAX(swe_high_frequency_question_result.created_at)

前端用于显示：

本结果更新于 yyyy-MM-dd HH:mm

十一、请重点检查

1. 当前 Python 项目使用的是 FastAPI、Flask 还是其他框架，并沿用现有写法。
2. 当前数据库访问使用 SQLAlchemy、原生 SQL、MyBatis 风格封装或其他方式，并沿用现有实现。
3. 当前项目是否已经有通用的 swe_async_tasks Model、Repository、Service。
4. 当前是否已有后台线程池、asyncio task、Celery 或其他异步任务机制，优先复用。
5. /result 接口是否能保证写库成功后才返回。
6. 工作流返回值中如何判断真正成功，不能仅以 HTTP 200 判断。
7. source_id 必须始终保留为前端传入的真实值，不能编码日期或机构。

修改完成后请输出：

- 修改的文件列表
- 每个文件的修改内容
- 新增或修改的接口
- Python 异步执行方式
- 24 小时缓存命中逻辑
- source_id 隔离逻辑
- RUNNING 任务去重逻辑
- SUCCEEDED/FAILED 状态流转
- result_updated_at 的返回方式
- 仍需确认的业务或技术问题