# 技能导出功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现技能导出功能，支持应用市场和我的技能导出为 zip 文件

**Architecture:** 后端新增统一导出 API，前端添加导出按钮触发下载

**Tech Stack:** FastAPI (StreamingResponse), TypeScript (fetch blob download), Ant Design

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `market/src/market/app/routers/skills_market.py` | Modify | 添加导出路由和辅助函数 |
| `console/src/api/modules/market.ts` | Modify | 添加 exportSkill API 方法 |
| `console/src/pages/Market/SkillDetailDrawer.tsx` | Modify | 添加导出按钮 |
| `console/src/pages/MySkills/SkillDetailPanel.tsx` | Modify | 添加导出按钮 |
| `console/src/pages/MySkills/index.tsx` | Modify | 添加导出回调函数 |

---

### Task 1: 后端 - 添加辅助函数

**Files:**
- Modify: `market/src/market/app/routers/skills_market.py`

- [ ] **Step 1: 在文件末尾添加 `_sanitize_filename` 函数**

在文件末尾（最后一个路由函数之后）添加：

```python
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

- [ ] **Step 2: 在 `_sanitize_filename` 之前添加 `_build_zip_response` 函数**

```python
def _build_zip_response(skill_dir: Path, export_name: str) -> StreamingResponse:
    """打包技能目录为 zip 并返回流式响应."""
    from fastapi.responses import StreamingResponse

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
```

- [ ] **Step 3: Commit**

```bash
git add market/src/market/app/routers/skills_market.py
git commit -m "feat(market): add zip export helper functions"
```

---

### Task 2: 后端 - 添加导出路由

**Files:**
- Modify: `market/src/market/app/routers/skills_market.py`

- [ ] **Step 1: 添加必要的导入**

在文件顶部导入区（line 29 附近），添加 `get_user_skills_dir` 导入：

```python
from ...marketplace.fs import get_skill_dir, get_user_skills_dir, _atomic_write_json
```

- [ ] **Step 2: 在文件末尾添加导出路由**

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
            raise HTTPException(status_code=400, detail="item_id required for market type")
        # 获取技能目录
        skill_dir = get_skill_dir(svc.marketplace_root, source_id, item_id)
        # 获取技能名称作为文件名
        items = load_index(svc.marketplace_root, source_id)
        item = next((i for i in items if i.item_id == item_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="Skill not found")
        export_name = item.name
    elif source_type == "my":
        if not skill_name:
            raise HTTPException(status_code=400, detail="skill_name required for my type")
        user_id = x_user_id or "default"
        # 获取用户技能目录
        skill_dir = get_user_skills_dir(svc.swe_root, user_id) / skill_name
        export_name = skill_name
    else:
        raise HTTPException(status_code=400, detail="Invalid source_type")

    # 检查目录是否存在
    if not skill_dir.exists():
        raise HTTPException(status_code=404, detail="Skill directory not found")

    # 打包目录为 zip
    return _build_zip_response(skill_dir, export_name)
```

- [ ] **Step 3: Commit**

```bash
git add market/src/market/app/routers/skills_market.py
git commit -m "feat(market): add skill export API endpoint"
```

---

### Task 3: 前端 API - 添加导出方法

**Files:**
- Modify: `console/src/api/modules/market.ts`

- [ ] **Step 1: 在 `marketApi` 对象末尾添加 `exportSkill` 方法**

在 `getDistributionPreview` 方法之后，添加：

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

    const headers = Object.fromEntries(
      (mergeHeaders({
        'X-Source-Id': sourceId,
        ...(sourceType === 'market' ? { 'X-Manager': 'true' } : {}),
      }).headers as Headers).entries(),
    );

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
  },
```

- [ ] **Step 2: Commit**

```bash
git add console/src/api/modules/market.ts
git commit -m "feat(console): add exportSkill API method"
```

---

### Task 4: 前端 - 应用市场添加导出按钮

**Files:**
- Modify: `console/src/pages/Market/SkillDetailDrawer.tsx`

- [ ] **Step 1: 添加 `DownloadOutlined` 图标导入**

在文件顶部导入区（line 6-12），添加 `DownloadOutlined`：

```typescript
import {
  EditOutlined,
  HistoryOutlined,
  MoreOutlined,
  UserOutlined,
  DownloadOutlined,
} from "@ant-design/icons";
```

- [ ] **Step 2: 添加 `handleExport` 函数**

在组件内部，`moreMenuItems` 定义之前（line 427 附近），添加：

```typescript
  const handleExport = useCallback(async () => {
    if (!skill || !sourceId) return;
    try {
      await marketApi.exportSkill(sourceId, 'market', skill.name, skill.item_id);
      message.success('导出成功');
    } catch (err) {
      message.error('导出失败');
    }
  }, [skill, sourceId]);
```

- [ ] **Step 3: 在操作按钮区添加导出按钮**

在「版本历史」按钮之后（line 667），「分发」按钮之前，添加导出按钮：

```typescript
            {isManager && (
              <Button
                onClick={handleExport}
                style={SECONDARY_BUTTON_STYLE}
              >
                <DownloadOutlined style={{ fontSize: 12 }} />
                导出
              </Button>
            )}
```

具体位置：在 `版本历史` Button 之后，`{isManager && onDistribute &&` 之前。

- [ ] **Step 4: Commit**

```bash
git add console/src/pages/Market/SkillDetailDrawer.tsx
git commit -m "feat(console): add export button to skill detail drawer"
```

---

### Task 5: 前端 - 我的技能添加导出按钮

**Files:**
- Modify: `console/src/pages/MySkills/SkillDetailPanel.tsx`
- Modify: `console/src/pages/MySkills/index.tsx`

- [ ] **Step 1: 在 SkillDetailPanel.tsx 添加图标导入**

在文件顶部（line 3），添加 `DownloadOutlined`：

```typescript
import { StarOutlined, RocketOutlined, UserOutlined, ClockCircleOutlined, CalendarOutlined, TagOutlined, DownOutlined, UpOutlined, DownloadOutlined } from "@ant-design/icons";
```

- [ ] **Step 2: 在 SkillDetailPanelProps 接口添加 `onExport` prop**

在 `onSyncToMarket` 之后（line 68），添加：

```typescript
  onExport: (skill: MySkill) => void;
```

- [ ] **Step 3: 在组件参数中添加 `onExport`**

在 `onSyncToMarket` 参数之后（line 89），添加：

```typescript
  onExport,
```

- [ ] **Step 4: 在操作按钮区添加导出按钮**

在「删除」按钮之前（line 258），添加导出按钮：

```typescript
          <Button
            size="small"
            icon={<DownloadOutlined style={{ fontSize: 12 }} />}
            style={{ height: 28, fontSize: 12, borderRadius: 8 }}
            onClick={() => onExport(skill)}
          >
            导出
          </Button>
```

- [ ] **Step 5: 在 index.tsx 添加 `handleExport` 函数**

在 `handleSyncToMarket` 函数之后（line 542），添加：

```typescript
  const handleExport = useCallback(async (skill: MySkill) => {
    if (!skill) return;
    try {
      await marketApi.exportSkill(sourceId, 'my', skill.skill_name);
      message.success('导出成功');
    } catch (err) {
      message.error('导出失败');
    }
  }, [sourceId]);
```

- [ ] **Step 6: 在 SkillDetailPanel 调用中添加 `onExport` prop**

在 SkillDetailPanel 组件调用处（line 917-936），添加 `onExport={handleExport}`：

```typescript
        <SkillDetailPanel
          skill={selectedSkill}
          ...
          onExport={handleExport}
        />
```

- [ ] **Step 7: Commit**

```bash
git add console/src/pages/MySkills/SkillDetailPanel.tsx console/src/pages/MySkills/index.tsx
git commit -m "feat(console): add export button to my skills detail panel"
```

---

### Task 6: 验证与测试

- [ ] **Step 1: 启动后端服务验证 API**

```bash
# 进入 market 目录启动服务
cd market && python -m market
```

测试 API 可用性：curl 或浏览器访问 `/market/skills/export?source_type=market&item_id=<id>` 带 proper headers

- [ ] **Step 2: 启动前端验证 UI**

```bash
cd console && npm run dev
```

访问应用市场技能详情页，验证导出按钮显示和点击下载功能

- [ ] **Step 3: 功能验证清单**

- 管理员在应用市场技能详情页点击导出，下载 zip 文件
- 普通用户在我的技能详情页点击导出，下载 zip 文件
- 解压 zip 验证目录结构完整（包含 SKILL.md、templates 等）

- [ ] **Step 4: Final commit with all changes**

```bash
git add -A
git commit -m "feat: complete skill export functionality"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- API 设计完整覆盖 ✓
- 前端导出按钮位置符合设计 ✓
- 权限控制实现 ✓
- 错误处理覆盖 ✓

**2. Placeholder scan:**
- 无 TBD、TODO ✓
- 所有代码步骤包含完整代码 ✓
- 无模糊描述 ✓

**3. Type consistency:**
- `exportSkill` 方法签名前后端一致 ✓
- `onExport` prop 类型正确 ✓