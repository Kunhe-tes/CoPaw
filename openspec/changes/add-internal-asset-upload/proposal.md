## Why

内部调用方目前可以通过 text asset 接口写入文本内容，但缺少直接上传二进制或原始文件的 asset 接口。新增上传能力后，调用方可以把文件统一落盘到现有 asset 根目录，供后续读取、预览或静态资源流程复用。

## What Changes

- 在 `src/swe/app/routers/internal.py` 中新增内部 asset 文件上传接口。
- 接口接收 multipart 文件上传，并将文件保存到 `WORKING_DIR / _ASSET_ROOT_DIRNAME`。
- 上传文件名必须通过安全校验，禁止路径穿越、绝对路径、空文件名和保留目录名。
- 上传成功后返回保存后的文件名、成功标记和可用于定位该 asset 的路径信息。
- 复用现有内部服务 Token 校验行为，不引入公开上传接口。

## Capabilities

### New Capabilities

- `asset-file-upload`: 内部服务可上传文件并保存到全局 asset 根目录。

### Modified Capabilities

- None

## Impact

- Affected code: `src/swe/app/routers/internal.py`
- Affected tests: `tests/unit/routers/test_internal_text_assets.py` or a new focused router test file under `tests/unit/routers/`
- API surface: adds a new authenticated internal endpoint under `/internal/assets`
- Storage: writes uploaded files under `WORKING_DIR / _ASSET_ROOT_DIRNAME`
