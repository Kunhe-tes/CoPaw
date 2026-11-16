-- REVIEW-ONLY DDL draft; NOT executed. Independently configured database.
-- Target MySQL 8.0.21+, InnoDB DYNAMIC, 16KiB+ pages, strict mode.
-- Verify MySQL/TDSQL target before DBA applies. No automatic runtime DDL.
-- UTC DATETIME(6); exact business identity bytes; metadata only; no TTL/cleanup.

CREATE TABLE swe_agentobs_inbox (
    ingest_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    payload_text MEDIUMTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL,
    received_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    processing_state TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0 pending,1 processed,2 rejected,3 conflict',
    processed_at DATETIME(6) NULL,
    reason_code VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
    event_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
    PRIMARY KEY (ingest_id),
    KEY ix_agentobs_inbox_pending (processing_state, ingest_id),
    CONSTRAINT ck_agentobs_inbox_size CHECK (payload_text IS NULL OR OCTET_LENGTH(payload_text) <= 24576),
    CONSTRAINT ck_agentobs_inbox_state CHECK (processing_state IN (0,1,2,3))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE swe_agentobs_runs (
    run_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    service_unit_key VARBINARY(256) NOT NULL,
    source_key VARBINARY(256) NOT NULL,
    tenant_key VARBINARY(256) NOT NULL,
    agent_key VARBINARY(256) NOT NULL,
    chat_key VARBINARY(128) NOT NULL,
    root_question_key VARBINARY(256) NOT NULL,
    user_key VARBINARY(256) NULL,
    channel_key VARBINARY(64) NULL,
    session_key VARBINARY(1024) NULL,
    predecessor_run_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
    capture_enabled TINYINT UNSIGNED NOT NULL,
    started_at DATETIME(6) NOT NULL,
    ended_at DATETIME(6) NULL,
    status VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
    quality VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'unknown',
    terminal_fact_source VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
    duration_us BIGINT UNSIGNED NULL,
    active_duration_us BIGINT UNSIGNED NULL,
    llm_calls BIGINT UNSIGNED NULL,
    tool_calls BIGINT UNSIGNED NULL,
    agent_loops BIGINT UNSIGNED NULL,
    input_tokens BIGINT UNSIGNED NULL,
    output_tokens BIGINT UNSIGNED NULL,
    metadata_text MEDIUMTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    projected_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (run_id),
    KEY ix_agentobs_runs_source_time (service_unit_key, source_key, started_at, run_id),
    KEY ix_agentobs_runs_scope_time (service_unit_key, source_key, tenant_key, agent_key, started_at, run_id),
    KEY ix_agentobs_runs_question (service_unit_key, source_key, tenant_key, agent_key, chat_key, root_question_key),
    KEY ix_agentobs_runs_status (service_unit_key, source_key, status, started_at, run_id),
    KEY ix_agentobs_runs_predecessor (predecessor_run_id),
    CONSTRAINT ck_agentobs_run_capture CHECK (capture_enabled IN (0,1)),
    CONSTRAINT ck_agentobs_run_metadata CHECK (OCTET_LENGTH(metadata_text) <= 24576)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE swe_agentobs_events (
    event_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    schema_version SMALLINT UNSIGNED NOT NULL,
    event_name VARCHAR(48) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    entity_kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    entity_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    phase_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    local_seq INT UNSIGNED NOT NULL,
    run_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
    attempt_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
    span_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
    service_unit_key VARBINARY(256) NULL,
    source_key VARBINARY(256) NULL,
    tenant_key VARBINARY(256) NULL,
    agent_key VARBINARY(256) NULL,
    occurred_at DATETIME(6) NOT NULL,
    first_ingest_id BIGINT UNSIGNED NOT NULL,
    producer_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    metadata_text MEDIUMTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    PRIMARY KEY (event_id),
    UNIQUE KEY uq_agentobs_event_slot (entity_kind, entity_id, phase_key, local_seq),
    KEY ix_agentobs_events_run (run_id, occurred_at, event_id),
    KEY ix_agentobs_events_entity (entity_kind, entity_id, occurred_at, event_id),
    KEY ix_agentobs_events_scope_time (service_unit_key, source_key, occurred_at, event_id),
    CONSTRAINT ck_agentobs_event_metadata CHECK (OCTET_LENGTH(metadata_text) <= 24576)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE swe_agentobs_attempts (
    attempt_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    run_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    attempt_index INT UNSIGNED NOT NULL,
    predecessor_attempt_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
    approval_request_key VARBINARY(256) NULL,
    started_at DATETIME(6) NOT NULL,
    ended_at DATETIME(6) NULL,
    status VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
    quality VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'unknown',
    duration_us BIGINT UNSIGNED NULL,
    metadata_text MEDIUMTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    PRIMARY KEY (attempt_id),
    UNIQUE KEY uq_agentobs_attempt_order (run_id, attempt_index),
    CONSTRAINT ck_agentobs_attempt_metadata CHECK (OCTET_LENGTH(metadata_text) <= 24576)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE swe_agentobs_spans (
    span_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    run_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    attempt_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
    parent_span_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
    business_subagent_key VARBINARY(256) NULL,
    span_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    operation VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    model_key VARBINARY(256) NULL,
    provider_key VARBINARY(256) NULL,
    request_model_key VARBINARY(256) NULL,
    response_model_key VARBINARY(256) NULL,
    model_key_source VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NULL,
    streaming TINYINT UNSIGNED NULL,
    finish_reason VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
    tool_key VARBINARY(256) NULL,
    started_at DATETIME(6) NOT NULL,
    ended_at DATETIME(6) NULL,
    status VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
    error_type VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,
    quality VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'unknown',
    duration_us BIGINT UNSIGNED NULL,
    time_to_first_chunk_us BIGINT UNSIGNED NULL,
    time_to_first_visible_text_us BIGINT UNSIGNED NULL,
    input_tokens BIGINT UNSIGNED NULL,
    output_tokens BIGINT UNSIGNED NULL,
    metadata_text MEDIUMTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    PRIMARY KEY (span_id),
    KEY ix_agentobs_spans_run_time (run_id, started_at, span_id),
    KEY ix_agentobs_spans_parent (run_id, parent_span_id, started_at, span_id),
    KEY ix_agentobs_spans_type (run_id, span_type, started_at, span_id),
    KEY ix_agentobs_spans_model (model_key, started_at, run_id),
    KEY ix_agentobs_spans_tool (tool_key, started_at, run_id),
    CONSTRAINT ck_agentobs_span_streaming CHECK (streaming IS NULL OR streaming IN (0,1)),
    CONSTRAINT ck_agentobs_span_metadata CHECK (OCTET_LENGTH(metadata_text) <= 24576)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- User ingestion with one complete JSON line as bound parameter:
-- INSERT INTO swe_agentobs_inbox (payload_text) VALUES (%s);
-- Projector locks Run before Attempt/Span, verifies immutable scope, and enforces authorization via Run.
-- No FK because events may arrive out of order; projector supplies referential validation.
