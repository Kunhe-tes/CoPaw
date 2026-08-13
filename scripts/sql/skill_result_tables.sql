CREATE TABLE IF NOT EXISTS swe_skill_result (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  source_id VARCHAR(64) NULL COMMENT '来源标识',
  trace_id VARCHAR(128) NULL COMMENT '关联对话分析 traceId',
  skill_id VARCHAR(128) NULL COMMENT '技能ID',
  user_id VARCHAR(128) NULL COMMENT '用户ID',
  bbk VARCHAR(128) NULL COMMENT '分行编码',
  cust_list TEXT NULL COMMENT '客户列表（JSON 字符串数组）',
  metadata TEXT NULL COMMENT '预留元数据（JSON 字符串）',
  result_id VARCHAR(128) NULL COMMENT '结果ID',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  KEY idx_swe_skill_result_trace (trace_id),
  KEY idx_swe_skill_result_skill (skill_id, created_at),
  KEY idx_swe_skill_result_user (user_id, bbk, created_at),
  KEY idx_swe_skill_result_result (result_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='技能执行结果存档';
