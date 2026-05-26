# 提取客户姓名功能设计

## 概述

在 monitor 服务实现后台批量处理功能，从 `swe_tracing_traces` 表的 `user_message` 和 ES 的 `model_output` 中提取客户姓名，结果保存到新表供后续分析使用。

## 需求背景

- 需要按指定 `skill_name` 查询对话记录
- 从用户消息和模型输出中提取客户姓名
- 使用 `SWE_ZHAOHU_EXTRACT_URL` 服务进行姓名提取
- 结果持久化存储，支持后续查询和分析

## 技术方案

### API 端点

**路径：** `POST /monitor/tracing/extract-customer-names`

**请求参数：**
```json
{
  "skill_names": ["技能A", "技能B"],
  "user_ids": ["user1", "user2"],
  "bbk_id": "100",
  "start_date": "2026-01-01",
  "end_date": "2026-01-31"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| skill_names | string[] | 是 | 技能名称列表 |
| user_ids | string[] | 否 | 用户 ID 列表筛选 |
| bbk_id | string | 否 | 分行 ID 筛选 |
| start_date | string | 否 | 开始日期 (YYYY-MM-DD) |
| end_date | string | 否 | 结束日期 (YYYY-MM-DD) |

**响应：**
```json
{
  "total_traces": 150,
  "names_extracted": 320,
  "user_message_names": 180,
  "model_output_names": 140
}
```

### 数据库表设计

```sql
CREATE TABLE IF NOT EXISTS swe_extracted_customer_names (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id        VARCHAR(64) NOT NULL COMMENT '关联的 trace ID',
    skill_name      VARCHAR(255) NOT NULL COMMENT '技能名称',
    user_message_names JSON NOT NULL COMMENT '用户消息中提取的姓名列表',
    model_output_names JSON NOT NULL COMMENT '模型输出中提取的姓名列表',
    user_id         VARCHAR(64) DEFAULT '' COMMENT '用户 ID',
    bbk_id          VARCHAR(64) DEFAULT '' COMMENT '分行 ID',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    UNIQUE INDEX uk_trace_skill (trace_id, skill_name),
    INDEX idx_skill_name (skill_name),
    INDEX idx_user_id (user_id),
    INDEX idx_bbk_id (bbk_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='提取客户姓名记录表';
```

**设计说明：**
- 每个 trace 产生一条记录，不按姓名裂变
- `user_message_names` 和 `model_output_names` 以 JSON 数组存储姓名列表
- 使用唯一索引 `(trace_id, skill_name)` 保证不重复写入

### 数据处理流程

```
1. 接收请求参数

2. 查询 swe_tracing_spans 获取 trace_id 列表
   - WHERE event_type = 'skill_invocation'
   - AND skill_name IN (skill_names)
   - AND (user_ids 可选筛选)
   - AND (bbk_id 可选筛选)
   - AND (start_date/end_date 可选筛选)
   - DISTINCT trace_id，同时获取 user_id、bbk_id

3. 过滤已处理的 trace_id
   - 查询 swe_extracted_customer_names 已有记录
   - 跳过已存在（相同 skill_name + trace_id 组合）的 trace

4. 批量查询 swe_tracing_traces 获取 user_message
   - WHERE trace_id IN (待处理列表)

5. 批量查询 ES 获取 model_output
   - 调用 ESClient.get_message(trace_id)

6. 调用 SWE_ZHAOHU_EXTRACT_URL 提取姓名
   - POST {"text": user_message} -> {"names": ["张三", "李四"]}
   - POST {"text": model_output} -> {"names": ["王五"]}

7. 写入 swe_extracted_customer_names
   - 每个 trace 一条记录
   - user_message_names 存储用户消息提取结果
   - model_output_names 存储模型输出提取结果
   - 使用 INSERT ON DUPLICATE KEY UPDATE 或先查询再写入

8. 返回统计结果
```

### 关键设计决策

**去重策略：** 使用 `trace_id + skill_name` 唯一索引保证不重复写入。写入前查询已有记录，也防止并发重复写入。

**并发控制：** 对 `SWE_ZHAOHU_EXTRACT_URL` 外部 API 做并发限制，建议最大 5 并发，避免压垮下游服务。

**ES 降级处理：** ES 未连接时，只提取 user_message 中的姓名，model_output 部分跳过并记录警告日志。

**空结果处理：** 提取 API 返回空 names 列表或调用失败时，该字段存储空数组 `[]`，仍然写入记录以标记已处理。

**增量处理：** 每次请求自动跳过已处理过的 `trace_id + skill_name` 组合，无需外部记录水位。

### 环境变量

复用现有 `SWE_ZHAOHU_EXTRACT_URL` 环境变量，已在 `src/swe/config/config.py` 中定义。

Monitor 侧需要在配置中引入该变量：
- `MONITOR_EXTRACT_URL` 或复用 `USER_INFO_API_URL` 模式从环境变量加载

## 文件结构

```
monitor/src/monitor/
├── app/
│   ├── models/
│   │   └── tracing.py              # 新增请求/响应模型
│   ├── routers/
│   │   └── tracing.py              # 新增 API 端点
│   ├── services/
│   │   └── tracing/
│   │       └── extract_service.py  # 新增提取服务
│   └── database/
│       └── schema.py               # 新增表创建 SQL
└── config/
    └── constant.py                 # 新增 EXTRACT_URL 常量
```

## 错误处理

| 场景 | 处理方式 |
|------|----------|
| skill_names 为空 | 返回 400 错误 |
| 无匹配 traces | 返回空统计结果 |
| ES 不可用 | 跳过 model_output 提取，继续处理 user_message |
| 提取 API 超时 | 记录警告日志，该字段存储空数组 [] |
| 提取 API 返回非 200 | 记录警告日志，该字段存储空数组 [] |
| 数据库写入失败 | 返回 500 错误 |

## 测试要点

1. 正常流程：指定 skill_names，验证姓名正确提取并存储为 JSON 数组
2. 筛选条件：验证 user_ids、bbk_id、日期范围筛选生效
3. 去重逻辑：重复调用 API，验证每个 trace 只产生一条记录
4. ES 降级：ES 未配置时，验证 user_message 正常提取
5. 并发限制：验证外部 API 调用并发数可控
