## Why

当前 `/assets/upload` 接口上传文件后仅将文件保存到本地磁盘，没有记录上传文件的元信息（文件名、大小等）。需要在上传时将文件名称等信息持久化到数据库表中，并提供查询接口，以便后续追踪和管理已上传的资产文件。

## What Changes

- 新增 `swe_asset_upload_record` 数据库表，记录上传文件的名称、大小、存储路径、来源标识等信息
- 修改 `/assets/upload` 接口，在上传文件成功后将文件信息写入新表
- 新增查询接口，支持按条件查询上传记录（分页、按 source_id 过滤等）
- 新增 SQL 建表脚本到 `scripts/sql/` 目录

## Capabilities

### New Capabilities
- `asset-upload-record`: 上传文件记录的持久化存储与查询能力，包括建表、写入记录、分页查询接口

### Modified Capabilities
- `asset-file-upload`: 上传成功后需额外写入数据库记录（行为变更）

## Impact

- **数据库**: 新增 `swe_asset_upload_record` 表（MySQL InnoDB, utf8mb4）
- **API**: 修改 `POST /assets/upload` 响应不变但内部增加写库逻辑；新增 `GET /assets/records` 查询接口
- **代码结构**: 新增 `src/swe/app/asset_upload_record/` 模块（models.py, store.py, service.py, router.py），修改 `internal.py` 中的 `_save_uploaded_asset_file` 函数
- **依赖**: 无新外部依赖，复用现有 `DatabaseConnection` 和 Pydantic 模式
