# 技能导出功能设计

## 功能概述

支持「我的技能」和「应用市场」下的技能导出为 zip 文件，便于用户备份、迁移或分享技能。

## 设计日期

2026-07-07

## 需求确认

| 项目 | 决策 |
|------|------|
| 导出范围 | 单技能导出 |
| 导出内容 | 整个技能目录（包含所有文件和子目录） |
| 文件名规则 | 使用技能名 |
| 导出入口 | 应用市场和我的技能详情页都添加导出按钮 |
| 权限控制 | 分开控制：市场技能仅管理员可导出；我的技能所有用户可导出自己技能 |
| 技术实现 | 后端生成 zip，前端直接下载 |

## API 设计

### 后端 API

新增统一导出接口：

```
GET /market/skills/export
```

**请求参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `source_type` | string | 来源类型：`market` 或 `my` |
| `skill_name` | string | 技能名（my 技能必填） |
| `item_id` | string | 市场技能 ID（market 技能必填） |
| `X-Source-Id` | header | 租户标识 |

**响应：**
- Content-Type: `application/zip`
- Content-Disposition: `attachment; filename="<skill_name>.zip"`
- Body: zip 文件二进制流

**权限控制：**
- `source_type=market`：需要 `X-Manager=true`
- `source_type=my`：普通用户可导出自己技能

### 前端 API

在 `console/src/api/modules/market.ts` 添加导出方法：

```typescript
exportSkill: async (
  sourceId: string,
  sourceType: 'market' | 'my',
  skillName: string,
  itemId?: string
): Promise<void> => {
  const params = new URLSearchParams();
  params.set('source_type', sourceType);
  if (sourceType === 'my') {
    params.set('skill_name', skillName);
  } else {
    params.set('item_id', itemId || '');
  }

  const headers = mergeHeaders({
    'X-Source-Id': sourceId,
    ...(sourceType === 'market' ? { 'X-Manager': 'true' } : {}),
  });

  const url = getApiUrl(`/market/skills/export?${params.toString()}`);
  const response = await fetch(url, { headers });

  if (!response.ok) {
    throw new Error('导出失败');
  }

  // 触发浏览器下载
  const blob = await response.blob();
  const filename = `${skillName}.zip`;
  const downloadUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(downloadUrl);
}
```

## 后端实现设计

### 文件位置

在 `market/src/market/app/routers/skills_market.py` 添加导出路由。

### 核心实现逻辑

```python
@router.get("/market/skills/export")
async def export_skill(
    request: Request,
    source_type: str = Query(..., description="来源类型: market 或 my"),
    skill_name: Optional[str] = Query(None, description="用户技能名"),
    item_id: Optional[str] = Query(None, description="市场技能 ID"),
    x_source_id: Optional[str] = Header(None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    """导出技能为 zip 文件."""
    source_id = require_source_id(x_source_id)
    svc = request.app.state.marketplace

    # 权限校验
    if source_type == "market":
        _require_manager(x_manager)
        if not item_id:
            raise HTTPException(400, "item_id required for market type")
        # 获取技能目录
        skill_dir = get_skill_dir(svc.marketplace_root, source_id, item_id)
        # 获取技能名称作为文件名
        items = load_index(svc.marketplace_root, source_id)
        item = next((i for i in items if i.item_id == item_id), None)
        if not item:
            raise HTTPException(404, "Skill not found")
        export_name = item.name
    elif source_type == "my":
        if not skill_name:
            raise HTTPException(400, "skill_name required for my type")
        user_id = x_user_id or "default"
        # 获取用户技能目录
        skill_dir = get_user_skills_dir(svc.swe_root, user_id) / skill_name
        export_name = skill_name
    else:
        raise HTTPException(400, "Invalid source_type")

    # 检查目录是否存在
    if not skill_dir.exists():
        raise HTTPException(404, "Skill directory not found")

    # 打包目录为 zip
    return _build_zip_response(skill_dir, export_name)
```

### 打包逻辑

```python
def _build_zip_response(skill_dir: Path, export_name: str) -> StreamingResponse:
    """打包技能目录为 zip 并返回流式响应."""
    import io
    import zipfile

    # 创建内存 buffer
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 递归添加目录下所有文件
        for file_path in skill_dir.rglob('*'):
            if file_path.is_file():
                # 排除隐藏文件
                if file_path.name.startswith('.') or file_path.name.startswith('__'):
                    continue
                # 计算相对路径
                arcname = file_path.relative_to(skill_dir)
                zf.write(file_path, arcname)

    # 空目录处理
    if buffer.tell() == 0:
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("README.txt", "技能目录无文件")

    buffer.seek(0)

    # sanitize 文件名
    safe_name = _sanitize_filename(export_name)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{safe_name}.zip\"",
        },
    )


def _sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符."""
    import re
    # 替换 Windows 不允许的字符
    name = re.sub(r'[<>:"|?*\\/]', '_', name)
    # 截断到 200 字符
    if len(name) > 200:
        name = name[:200]
    return name.strip() or "skill"
```

## 前端实现设计

### 应用市场 - SkillDetailDrawer.tsx

在顶栏右侧按钮区域添加导出按钮：

**位置：** 在「版本历史」按钮之后，「分发」按钮之前

**按钮样式：**
- 图标：`DownloadOutlined` (antd)
- 文字：「导出」
- 样式：次要按钮风格（与「版本历史」一致）
- 条件渲染：仅管理员可见（`isManager`）

**点击逻辑：**
```typescript
const handleExport = async () => {
  try {
    await marketApi.exportSkill(sourceId, 'market', skill.name, skill.item_id);
    message.success('导出成功');
  } catch (err) {
    message.error('导出失败');
  }
};
```

### 我的技能 - SkillDetailPanel.tsx

在操作按钮区域添加导出按钮：

**位置：** 在「启用/禁用」按钮附近

**按钮样式：**
- 图标：`DownloadOutlined`
- 文字：「导出」
- 样式：次要按钮风格

**点击逻辑：**
```typescript
const handleExport = async () => {
  try {
    await marketApi.exportSkill(sourceId, 'my', skill.skill_name);
    message.success('导出成功');
  } catch (err) {
    message.error('导出失败');
  }
};
```

## 错误处理

### 后端错误场景

| 场景 | HTTP 状态码 | 响应内容 |
|------|-------------|----------|
| 技能不存在 | 404 | `{"detail": "Skill not found"}` |
| source_type 无效 | 400 | `{"detail": "Invalid source_type"}` |
| 缺少必要参数 | 400 | `{"detail": "item_id required for market type"}` |
| 权限不足（市场导出） | 403 | `{"detail": "Manager access required"}` |
| 技能目录为空 | 200 | 返回包含 README.txt 的 zip |

### 前端错误提示

统一使用 `message.error('导出失败')` 提示，具体原因由后端 detail 返回。

## 测试要点

1. **功能测试**
   - 市场技能导出：管理员点击导出，下载 zip，解压验证目录结构完整
   - 我的技能导出：普通用户点击导出，下载 zip，解压验证内容正确
   - 空目录导出：技能目录无文件时，zip 包含 README.txt

2. **权限测试**
   - 非管理员导出市场技能：返回 403
   - 普通用户导出自己的技能：成功
   - 普通用户导出他人技能：返回 404（目录不存在）

3. **边界测试**
   - 文件名包含特殊字符：sanitization 正确处理
   - 文件名过长：截断处理
   - 大文件导出：流式响应正常