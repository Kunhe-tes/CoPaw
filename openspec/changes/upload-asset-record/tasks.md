## 1. 数据库建表

- [x] 1.1 创建 SQL 建表脚本 `scripts/sql/asset_upload_record_tables.sql`，定义 `swe_asset_upload_record` 表（id BIGINT AUTO_INCREMENT PK, file_name VARCHAR(512) NOT NULL, file_size BIGINT NOT NULL, asset_path VARCHAR(512) NOT NULL, source_id VARCHAR(64) NULL, created_at TIMESTAMP, updated_at TIMESTAMP, 索引 source_id+created_at, UNIQUE KEY file_name）

## 2. 模块代码

- [x] 2.1 创建 `src/swe/app/asset_upload_record/models.py`，定义 Pydantic 模型：AssetUploadRecord、AssetUploadRecordCreate、PaginatedAssetUploadRecords、TemplateItem、AssetUploadFileNameList、TemplateSearchResponse、TemplateResultRequest、TemplateResultResponse
- [x] 2.2 创建 `src/swe/app/asset_upload_record/store.py`，实现 AssetUploadRecordStore：insert_record（upsert ON DUPLICATE KEY UPDATE）、list_records（分页查询，支持 source_id 过滤）、count_records（统计总数）、list_all_file_names、get_template_id_by_name、_to_record（行转模型）
- [x] 2.3 创建 `src/swe/app/asset_upload_record/service.py`，实现 AssetUploadRecordService：create_record、query_records、list_all_file_names、search_template_id、query_template_result
- [x] 2.4 创建 `src/swe/app/asset_upload_record/router.py`，定义 APIRouter(prefix="/template")，实现 init_asset_upload_record_module(db)、GET /records、GET /file-templates、GET /search、POST /result，注册到 routers/__init__.py

## 3. 上传接口集成

- [x] 3.1 修改 `src/swe/app/routers/internal.py` 中的 `_save_uploaded_asset_file` 函数，在文件写入磁盘成功后调用 AssetUploadRecordService.create_record 写库，写库失败时记录 warning 日志但不阻断上传响应

## 4. 应用初始化

- [x] 4.1 修改 `src/swe/app/_app.py`，在 lifespan 中导入并调用 `init_asset_upload_record_module(db_connection)`，与其他模块初始化放在一起

## 5. 验证

- [x] 5.1 执行建表 SQL，启动应用验证模块初始化正常
- [x] 5.2 调用 POST /assets/upload 上传文件，检查数据库中是否生成记录
- [x] 5.3 调用 GET /template/records 验证分页查询返回正确数据
