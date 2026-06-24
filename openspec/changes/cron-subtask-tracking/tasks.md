## Tasks

### Phase 1: 数据库变更

- [ ] 执行 DDL 创建 `swe_cron_subtasks` 表
- [ ] 执行 ALTER 添加 `swe_cron_executions.async_status` 字段
- [ ] 验证表结构和索引

### Phase 2: 配置更新

- [ ] `constant.py` 添加异步任务配置变量
- [ ] `dev.json` 添加开发环境配置
- [ ] `prd.json` 添加生产环境配置
- [ ] `envs.json.example` 更新示例配置

### Phase 3: 模型层

- [ ] 创建 `models/subtask.py` 定义数据模型
- [ ] 定义请求/响应模型
- [ ] 更新 `schema.py` 添加建表 SQL

### Phase 4: 服务层

- [ ] 创建 `services/subtask/__init__.py`
- [ ] 实现 `query_service.py` 查询服务
- [ ] 实现 `sync_service.py` 状态同步服务
  - [ ] 外部 API 调用逻辑
  - [ ] 状态更新逻辑
  - [ ] 异步状态汇总逻辑

### Phase 5: 路由层

- [ ] 创建 `routers/subtask.py`
- [ ] 实现写入接口 `POST /monitor/subtasks`
- [ ] 实现状态同步接口 `POST /monitor/subtasks/sync-status`
- [ ] 实现异步状态汇总接口 `POST /monitor/cron/executions/sync-async-status`
- [ ] 注册路由到 `_app.py`

### Phase 6: 测试验证

- [ ] 手动测试写入接口
- [ ] 手动测试状态同步接口
- [ ] 手动测试异步状态汇总接口
- [ ] 验证数据库字段更新正确