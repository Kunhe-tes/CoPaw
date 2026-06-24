ALTER TABLE swe_html_preview_click_events
ADD COLUMN IF NOT EXISTS user_name VARCHAR(255) NULL
COMMENT '点击用户名称/客户经理姓名'
AFTER user_id;

ALTER TABLE swe_html_preview_click_events
ADD COLUMN IF NOT EXISTS list_key VARCHAR(1024) NULL
COMMENT '名单稳定标识，默认使用文件链接'
AFTER file_name;

ALTER TABLE swe_html_preview_click_events
ADD COLUMN IF NOT EXISTS list_name VARCHAR(512) NULL
COMMENT '名单展示名称，默认使用文件名'
AFTER list_key;

ALTER TABLE swe_html_preview_click_events
ADD COLUMN IF NOT EXISTS button_type VARCHAR(32) NULL
COMMENT '按钮类型：insight/phone/plan/other'
AFTER button_text;

ALTER TABLE swe_html_preview_click_events
ADD COLUMN IF NOT EXISTS customer_id VARCHAR(128) NULL
COMMENT '客户唯一标识'
AFTER button_type;

ALTER TABLE swe_html_preview_click_events
ADD COLUMN IF NOT EXISTS customer_name VARCHAR(255) NULL
COMMENT '客户展示名称'
AFTER customer_id;

UPDATE swe_html_preview_click_events
SET
  list_key = COALESCE(NULLIF(list_key, ''), file_url),
  list_name = COALESCE(NULLIF(list_name, ''), file_name, file_url)
WHERE list_key IS NULL OR list_key = '' OR list_name IS NULL OR list_name = '';

ALTER TABLE swe_html_preview_click_events
ADD INDEX IF NOT EXISTS idx_button_type_clicked (button_type, clicked_at);

ALTER TABLE swe_html_preview_click_events
ADD INDEX IF NOT EXISTS idx_customer_clicked (customer_id, clicked_at);

ALTER TABLE swe_html_preview_click_events
ADD INDEX IF NOT EXISTS idx_list_clicked (list_key(255), clicked_at);

CREATE TABLE IF NOT EXISTS swe_html_preview_list_snapshots (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,

  source_id VARCHAR(64) NULL COMMENT '来源标识',
  bbk_id VARCHAR(128) NULL COMMENT '分行/机构标识',

  cron_task_id VARCHAR(128) NULL COMMENT '定时任务ID',
  cron_task_name VARCHAR(255) NULL COMMENT '定时任务名称',

  list_key VARCHAR(1024) NOT NULL COMMENT '名单稳定标识，默认使用文件链接',
  list_name VARCHAR(512) NOT NULL COMMENT '名单展示名称，默认使用文件名',
  file_url TEXT NOT NULL COMMENT 'HTML 文件链接',
  file_name VARCHAR(512) NULL COMMENT 'HTML 文件名',

  customer_id VARCHAR(128) NULL COMMENT '客户唯一标识',
  customer_name VARCHAR(255) NOT NULL COMMENT '客户展示名称',
  extra_info JSON NULL COMMENT '客户扩展信息',

  snapshot_at DATETIME NOT NULL COMMENT '快照采集时间',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',

  INDEX idx_snapshot_source_list (source_id, list_key(255)),
  INDEX idx_snapshot_bbk_list (bbk_id, list_key(255)),
  INDEX idx_snapshot_customer (customer_id),
  INDEX idx_snapshot_at (snapshot_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='HTML 预览名单客户快照';
