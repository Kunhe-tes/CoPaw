-- Apply after the two Session/Chat CREATE statements from conversation_metadata_tables.sql.
-- Dedicated mysql-metadata deployment schema. Existing bundle DDL is independent.
ALTER TABLE swe_conversation_sessions
    ADD COLUMN nas_filename VARBINARY(255) NULL,
    ADD UNIQUE KEY uq_conv_nas_filename
        (service_unit_key, tenant_key, source_key, agent_key, nas_filename);

ALTER TABLE swe_conversation_chats
    ADD COLUMN extended_metadata_text MEDIUMTEXT NULL,
    ADD COLUMN resources_cleaned_at DATETIME(6) NULL;

CREATE TABLE swe_conversation_metadata_sources (
    service_unit_key VARBINARY(256) NOT NULL,
    tenant_key VARBINARY(256) NOT NULL,
    source_key VARBINARY(256) NOT NULL,
    migration_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    manifest_digest BINARY(32) NOT NULL,
    published TINYINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (service_unit_key, tenant_key, source_key)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE swe_conversation_metadata_workspaces (
    service_unit_key VARBINARY(256) NOT NULL,
    tenant_key VARBINARY(256) NOT NULL,
    source_key VARBINARY(256) NOT NULL,
    agent_key VARBINARY(256) NOT NULL,
    workspace_root VARBINARY(1024) NOT NULL,
    imported_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    registry_digest BINARY(32) NOT NULL,
    PRIMARY KEY (service_unit_key, tenant_key, source_key, agent_key),
    UNIQUE KEY uq_conv_metadata_root (service_unit_key, workspace_root)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
