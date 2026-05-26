## Context

`src/swe/app/routers/internal.py` 已包含内部 text asset 读写能力，并使用 `_ASSET_ROOT_DIRNAME = "asset"` 作为全局 asset 目录名。现有读接口已经通过 `_get_asset_file_path()` 从 `WORKING_DIR / _ASSET_ROOT_DIRNAME / file_name` 读取文件，但缺少对应的通用文件上传入口。

上传接口需要服务内部调用方使用，因此应保持在 `router = APIRouter(prefix="/internal", ...)` 下，并继续复用 `X-Internal-Token` 校验逻辑。该能力只负责把上传文件保存到 asset 根目录，不处理公开访问、预览路径或租户静态目录复制。

## Goals / Non-Goals

**Goals:**

- 新增内部接口 `POST /internal/assets/upload`。
- 接收 multipart 表单中的 `file` 字段，使用上传文件名作为 asset 文件名。
- 复用现有 `_validate_asset_file_name()`，禁止路径穿越和非法文件名。
- 将文件字节原样保存到 `WORKING_DIR / _ASSET_ROOT_DIRNAME / file_name`。
- 返回结构化响应，至少包含 `success`、`file_name`、`asset_path` 和 `size`。
- 增加单元测试覆盖成功上传、Token 校验、非法文件名和覆盖写入行为。

**Non-Goals:**

- 不新增公开上传接口。
- 不新增文件类型白名单、大小限制或病毒扫描。
- 不改变现有 text asset read/write/preview-path 接口行为。
- 不把上传文件复制到 `WORKING_DIR/<scope_id>/workspaces/default/static`。

## Decisions

1. 使用 `UploadFile` 接收文件。

   FastAPI 已支持 multipart 上传，`UploadFile` 能按文件流读取内容，适合后续扩展为流式拷贝。相比 base64 JSON 上传，multipart 更贴近文件上传语义，也避免额外编码膨胀。

2. 上传文件名来自 `UploadFile.filename`。

   这样调用方可以直接控制 asset 文件名，并与现有 `_get_asset_file_path(file_name)` 读取模型保持一致。实现必须先调用 `_validate_asset_file_name()`，确保最终路径只落在 asset 根目录的直接子文件。

3. 同名文件采用覆盖写入。

   现有 text asset 写入和 preview target 更新已经允许对明确目标进行覆盖。上传接口同样把文件名视为调用方指定的目标 asset，重复上传同名文件时覆盖旧内容，便于更新同一个逻辑资源。测试需要验证覆盖后的内容为最新上传内容。

4. 响应返回相对路径而非绝对路径。

   `asset_path` 使用 `asset/<file_name>` 形式，避免把宿主机真实 `WORKING_DIR` 绝对路径暴露给调用方，同时仍能让调用方定位保存位置。

## Risks / Trade-offs

- 文件大小不受限制 -> 当前变更不引入限制，后续如需要可增加配置化大小上限；实现阶段应避免一次性做额外业务校验。
- 同名覆盖可能丢失旧文件 -> 该行为符合“指定文件名即指定目标”的内部接口语义，调用方负责生成唯一文件名或显式覆盖。
- multipart 依赖环境缺失 -> FastAPI multipart 上传需要运行环境具备对应依赖；测试会在当前项目环境中验证，若缺失则在实现时补齐依赖或调整现有依赖声明。
- 上传文件名来自客户端 -> 通过 `_validate_asset_file_name()` 限定为单层文件名，阻止路径穿越和绝对路径写入。
