## 1. Database Schema

- [ ] 1.1 创建 SQL 建表脚本 `scripts/sql/zhaohu_channel_binding_table.sql`，定义 `swe_zhaohu_channel_binding` 表结构（id, tenant_id, source_id, robot_id, open_id, created_at, updated_at）及唯一键 uk_tenant_source 和索引 idx_open_id

## 2. Store 实现

- [ ] 2.1 创建 `src/swe/app/channels/zhaohu/binding_store.py`，实现 `ZhaohuChannelBindingStore` 类（构造函数、initialize、_use_db 检查）
- [ ] 2.2 实现 `upsert_binding(tenant_id, source_id, robot_id, open_id)` 方法，使用 ON DUPLICATE KEY UPDATE
- [ ] 2.3 实现 `get_binding(tenant_id, source_id)` 方法，返回完整绑定记录字典
- [ ] 2.4 实现 `get_robot_id(tenant_id, source_id)` 和 `get_binding_by_open_id(open_id)` 便捷查询方法
- [ ] 2.5 实现模块级单例函数：`init_zhaohu_binding_module(db)`、`get_zhaohu_binding_store()` 及对应的便捷异步函数

## 3. Channel 集成

- [ ] 3.1 在 `ZhaohuChannel.process_callback_message()` 中，user info 查询完成后添加 upsert_binding 调用（覆盖 openId 变更场景），失败时仅 log warning 不影响主流程
- [ ] 3.2 在 `_build_push_payload()` 中，当 self.robot_open_id 为空时从 DB 查询 robot_id 作为 fallback
- [ ] 3.3 更新 `src/swe/app/channels/zhaohu/__init__.py` 导出 Store 便捷函数

## 4. 应用启动集成

- [ ] 4.1 在 `src/swe/app/_app.py` 启动流程中调用 `init_zhaohu_binding_module(db)` 初始化 Store

## 5. 测试

- [ ] 5.1 创建 `tests/unit/channels/test_zhaohu_binding_store.py`，测试 Store 各方法的正确性和 DB 不可用时的降级行为
- [ ] 5.2 在 `tests/unit/channels/test_zhaohu_channel.py` 中补充回调落库集成测试
