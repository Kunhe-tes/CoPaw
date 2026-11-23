-- Apply once after conversation_mysql_metadata.sql in new or existing schemas.
ALTER TABLE swe_conversation_chats
    ADD KEY ix_conv_chat_registry
        (service_unit_key, tenant_key, source_key, agent_key, registry_order),
    ADD KEY ix_conv_chat_session_first
        (session_id, deleted_at, registry_order);
