## Context

当前 `/assets/upload` 接口（`src/swe/app/routers/internal.py:593`）将上传文件保存到 `WORKING_DIR/asset/` 目录，但不记录任何元信息到数据库。项目使用 FastAPI + aiomysql 的三层架构（models → store → service → router），所有数据库模块遵循一致的模式（参考 `feedback/`, `instance/` 等模块）。数据库表使用 `swe_` 前缀，InnoDB 引擎，utf8mb4 字符集。

## Goals / Non-Goals

**Goals:**
- 上传文件时自动将文件名、大小、存储路径等元信息写入 `swe_asset_upload_record` 表
- 提供分页查询接口，支持按 `source_id` 过滤上传记录
- 复用项目现有的模块架构（models/store/service/router）和初始化模式

**Non-Goals:**
- 不做文件删除、更新记录等写操作接口（当前需求仅为记录和查询）
- 不修改现有上传接口的响应结构（保持向后兼容）
- 不引入新的外部依赖

## Decisions

### 1. 新建独立模块 vs 内联到 internal.py

**选择**: 新建独立模块 `src/swe/app/asset_upload_record/`（models.py, store.py, service.py, router.py）

**理由**: 项目所有数据库模块都遵循独立模块模式（feedback, instance, greeting 等），internal.py 已经 936 行且职责混杂。新模块遵循既有约定，便于维护。

### 2. 写库时机：同步写入 vs 异步写入

**选择**: 在 `_save_uploaded_asset_file` 函数中，文件写入磁盘成功后同步写库

**理由**: 上传是低频操作，同步写库简单可靠。如果写库失败，文件已落盘不影响上传功能，仅丢失记录。写库失败时记录警告日志但不阻断上传响应。

### 3. 查询接口挂载位置

**选择**: 挂载到 `public_router`（`/assets/records`），与上传接口同属 public 路由，不需要内部 Token 认证

**理由**: 上传接口本身在 public_router 上不需要认证，查询接口也应保持一致。后续如需鉴权可通过中间件统一处理。

### 4. 表字段设计

**选择**: `id`（BIGINT AUTO_INCREMENT）, `file_name`（VARCHAR 256）, `file_size`（BIGINT）, `asset_path`（VARCHAR 512）, `source_id`（VARCHAR 64 NULL）, `created_at`, `updated_at`

**理由**: 与项目现有表结构一致（参考 `swe_response_feedback`），`source_id` 可 NULL 以兼容当前上传接口不传 source_id 的情况。

## Risks / Trade-offs

- [写库失败不阻断上传] → 通过 try/except 包裹写库逻辑，失败时记录 warning 日志，不影响上传功能
- [source_id 可能为空] → 当前上传接口不接收 source_id，记录中 source_id 为 NULL；后续如有需求可通过 header 注入
