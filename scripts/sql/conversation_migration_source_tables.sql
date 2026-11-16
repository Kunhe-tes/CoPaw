-- DBA applies before new source-isolated migrations; no application DDL.
CREATE TABLE IF NOT EXISTS swe_conversation_migration_sources (
  migration_id VARBINARY(36) NOT NULL,
  service_unit_key VARBINARY(256) NOT NULL,
  tenant_key VARBINARY(256) NOT NULL,
  source_key VARBINARY(256) NOT NULL,
  state VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  evidence_text LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  verification_text LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  failure_text LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL,
  attempts INT UNSIGNED NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  published_at DATETIME(6) NULL,
  PRIMARY KEY (migration_id, service_unit_key, tenant_key, source_key)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
