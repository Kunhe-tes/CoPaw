# Skill ZIP Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为“我的技能-我创建的”和“应用市场”实现当前版本 ZIP 下载，并为“应用市场-版本历史”实现按版本 ZIP 下载。

**Architecture:** 后端在 `market` 服务内新增统一 ZIP 打包 helper，并分别暴露“我的技能当前版本”“市场当前版本”“市场历史版本”三个下载接口。前端在 `console` 侧补充下载 API 和三个入口按钮，沿用现有详情面板与版本历史弹窗，不新增版本下拉选择器。

**Tech Stack:** FastAPI、Python `zipfile`、`asyncio.to_thread()`、TypeScript、React、Ant Design

---

## 文件结构

- 修改 `market/src/market/app/routers/skills_browse.py`
  - 增加“我的技能当前版本下载”和“市场当前版本下载”接口
- 修改 `market/src/market/app/routers/skill_versions.py`
  - 增加“市场历史版本下载”接口
- 新增 `market/src/market/marketplace/zip_download.py`
  - 统一封装 ZIP 文件名清洗、目录打包、临时文件生成
- 修改 `console/src/api/modules/mySkills.ts`
  - 增加“下载我创建的技能”API
- 修改 `console/src/api/modules/market.ts`
  - 增加“下载市场当前版本”“下载市场历史版本”API
- 修改 `console/src/pages/MySkills/SkillDetailPanel.tsx`
  - 为“我创建的”技能增加“下载 ZIP”按钮
- 修改 `console/src/pages/Market/SkillDetailDrawer.tsx`
  - 增加“下载 ZIP”按钮和历史版本提示
- 修改 `console/src/pages/Market/Skills/VersionHistoryModal.tsx`
  - 为每个版本条目增加“下载”按钮
- 新增 `tests/unit/market/test_skill_zip_download.py`
  - 覆盖三个下载接口及错误场景

### Task 1: 后端 ZIP 打包 Helper

**Files:**
- Create: `market/src/market/marketplace/zip_download.py`
- Test: `tests/unit/market/test_skill_zip_download.py`

- [ ] **Step 1: 写 ZIP helper 的失败测试**

```python
from pathlib import Path

from market.marketplace.zip_download import build_skill_zip


def test_build_skill_zip_keeps_original_tree(tmp_path: Path):
    skill_dir = tmp_path / "skill"
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    (refs_dir / "guide.md").write_text("hello\n", encoding="utf-8")

    zip_path = build_skill_zip(skill_dir, "demo.zip", tmp_path)

    assert zip_path.name == "demo.zip"
    assert zip_path.exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `venv/bin/python -m pytest tests/unit/market/test_skill_zip_download.py::test_build_skill_zip_keeps_original_tree -v`

Expected: FAIL，提示 `ModuleNotFoundError` 或 `cannot import name 'build_skill_zip'`

- [ ] **Step 3: 写最小实现**

```python
"""技能 ZIP 下载辅助工具。"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path


_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')


def sanitize_zip_filename(filename: str) -> str:
    """清洗 ZIP 文件名，避免非法字符破坏下载行为。"""
    safe_name = _INVALID_FILENAME_CHARS.sub("-", filename).strip()
    return safe_name or "skill.zip"


def build_skill_zip(
    skill_dir: Path,
    output_name: str,
    temp_dir: Path,
) -> Path:
    """将技能目录打包为 ZIP，保留目录内原始结构。"""
    zip_path = temp_dir / sanitize_zip_filename(output_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in skill_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(skill_dir))
    return zip_path
```

- [ ] **Step 4: 运行测试确认通过**

Run: `venv/bin/python -m pytest tests/unit/market/test_skill_zip_download.py::test_build_skill_zip_keeps_original_tree -v`

Expected: PASS

- [ ] **Step 5: 补一个结构断言测试并跑绿**

```python
import zipfile


def test_build_skill_zip_contains_relative_paths(tmp_path: Path):
    skill_dir = tmp_path / "skill"
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    (refs_dir / "guide.md").write_text("hello\n", encoding="utf-8")

    zip_path = build_skill_zip(skill_dir, "demo.zip", tmp_path)

    with zipfile.ZipFile(zip_path, "r") as zf:
        assert sorted(zf.namelist()) == ["SKILL.md", "references/guide.md"]
```

Run: `venv/bin/python -m pytest tests/unit/market/test_skill_zip_download.py::test_build_skill_zip_contains_relative_paths -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/unit/market/test_skill_zip_download.py market/src/market/marketplace/zip_download.py
git commit -m "feat(market): add skill zip helper"
```

### Task 2: 我的技能当前版本下载接口

**Files:**
- Modify: `market/src/market/app/routers/skills_browse.py`
- Modify: `tests/unit/market/test_skill_zip_download.py`

- [ ] **Step 1: 写“我的技能下载”失败测试**

```python
def test_download_my_skill_returns_zip(client, user_headers, created_skill_dir):
    response = client.get(
        "/market/skills/mine/demo-skill/download",
        headers=user_headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment;" in response.headers["content-disposition"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `venv/bin/python -m pytest tests/unit/market/test_skill_zip_download.py::test_download_my_skill_returns_zip -v`

Expected: FAIL，状态码为 `404`

- [ ] **Step 3: 写最小接口实现**

```python
@router.get("/market/skills/mine/{skill_name}/download")
async def download_my_skill(
    skill_name: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    agent_id: str = "default",
):
    """下载我创建的技能 ZIP。"""
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-Id header is required")

    svc = request.app.state.marketplace
    skill_dir = svc.get_created_skill_dir(source_id, x_user_id, skill_name, agent_id)
    if skill_dir is None or not skill_dir.exists():
        raise HTTPException(status_code=404, detail="Skill not found")

    zip_path = await asyncio.to_thread(
        build_skill_zip,
        skill_dir,
        f"{skill_name}.zip",
        Path(tempfile.gettempdir()),
    )
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `venv/bin/python -m pytest tests/unit/market/test_skill_zip_download.py::test_download_my_skill_returns_zip -v`

Expected: PASS

- [ ] **Step 5: 补 404 用例并跑绿**

```python
def test_download_my_skill_returns_404_when_missing(client, user_headers):
    response = client.get(
        "/market/skills/mine/missing/download",
        headers=user_headers,
    )

    assert response.status_code == 404
```

Run: `venv/bin/python -m pytest tests/unit/market/test_skill_zip_download.py -k "download_my_skill" -v`

Expected: 相关用例全部 PASS

- [ ] **Step 6: Commit**

```bash
git add tests/unit/market/test_skill_zip_download.py market/src/market/app/routers/skills_browse.py
git commit -m "feat(market): add my skill zip download"
```

### Task 3: 市场当前版本与历史版本下载接口

**Files:**
- Modify: `market/src/market/app/routers/skills_browse.py`
- Modify: `market/src/market/app/routers/skill_versions.py`
- Modify: `tests/unit/market/test_skill_zip_download.py`

- [ ] **Step 1: 写“市场当前版本下载”失败测试**

```python
def test_download_market_skill_returns_zip(client, source_headers, market_skill_item):
    response = client.get(
        f"/market/skills/{market_skill_item.item_id}/download",
        headers=source_headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `venv/bin/python -m pytest tests/unit/market/test_skill_zip_download.py::test_download_market_skill_returns_zip -v`

Expected: FAIL，状态码为 `404`

- [ ] **Step 3: 写“市场当前版本下载”最小实现**

```python
@router.get("/market/skills/{item_id}/download")
async def download_market_skill(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_bbk_id: Optional[str] = Header(default=None, alias="X-Bbk-Id"),
):
    """下载市场当前版本技能 ZIP。"""
    source_id = require_source_id(x_source_id)
    user_bbk_id = x_bbk_id or "100"
    svc = request.app.state.marketplace

    detail = await svc.get_skill_detail(source_id, item_id, user_bbk_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Skill not found")

    skill_dir = get_skill_dir(svc.marketplace_root, source_id, item_id)
    zip_path = await asyncio.to_thread(
        build_skill_zip,
        skill_dir,
        f"{detail.name}-{detail.version}.zip",
        Path(tempfile.gettempdir()),
    )
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)
```

- [ ] **Step 4: 写“市场历史版本下载”失败测试**

```python
def test_download_market_skill_version_returns_zip(
    client,
    source_headers,
    market_skill_item,
    market_skill_version,
):
    response = client.get(
        f"/market/skills/{market_skill_item.item_id}/versions/{market_skill_version}/download",
        headers=source_headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
```

- [ ] **Step 5: 运行历史版本测试确认失败**

Run: `venv/bin/python -m pytest tests/unit/market/test_skill_zip_download.py::test_download_market_skill_version_returns_zip -v`

Expected: FAIL，状态码为 `404`

- [ ] **Step 6: 写“市场历史版本下载”最小实现**

```python
@router.get("/market/skills/{item_id}/versions/{version_id}/download")
async def download_version_zip(
    request: Request,
    item_id: str,
    version_id: str,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
):
    """下载技能历史版本 ZIP。"""
    source_id = require_source_id(x_source_id)
    svc = _get_version_service(request)
    marketplace = request.app.state.marketplace

    _validate_item_exists(svc, source_id, item_id)

    detail = svc.get_version_detail(source_id, item_id, version_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Version {version_id} not found")

    version_dir = svc._get_version_root(source_id, item_id) / version_id
    if not version_dir.exists():
        raise HTTPException(status_code=404, detail=f"Version {version_id} not found")

    current_item = next(
        i for i in load_index(marketplace.marketplace_root, source_id) if i.item_id == item_id
    )
    zip_path = await asyncio.to_thread(
        build_skill_zip,
        version_dir,
        f"{current_item.name}-{version_id}.zip",
        Path(tempfile.gettempdir()),
    )
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)
```

- [ ] **Step 7: 运行相关测试确认通过**

Run: `venv/bin/python -m pytest tests/unit/market/test_skill_zip_download.py -k "download_market_skill" -v`

Expected: 当前版本和历史版本下载用例 PASS

- [ ] **Step 8: 补历史版本 404 用例并跑绿**

```python
def test_download_market_skill_version_returns_404_when_missing(
    client,
    source_headers,
    market_skill_item,
):
    response = client.get(
        f"/market/skills/{market_skill_item.item_id}/versions/missing/download",
        headers=source_headers,
    )

    assert response.status_code == 404
```

Run: `venv/bin/python -m pytest tests/unit/market/test_skill_zip_download.py -v`

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add tests/unit/market/test_skill_zip_download.py market/src/market/app/routers/skills_browse.py market/src/market/app/routers/skill_versions.py
git commit -m "feat(market): add market skill zip downloads"
```

### Task 4: 前端下载 API

**Files:**
- Modify: `console/src/api/modules/mySkills.ts`
- Modify: `console/src/api/modules/market.ts`

- [ ] **Step 1: 写前端下载 helper 的最小接口代码**

```typescript
async function downloadBinary(
  url: string,
  options: RequestInit,
): Promise<{ blob: Blob; filename: string | null }> {
  const response = await fetch(getApiUrl(url), options);
  if (!response.ok) {
    throw new Error(await response.text());
  }

  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition");
  const matched = disposition?.match(/filename="?([^"]+)"?/i);
  return { blob, filename: matched?.[1] ?? null };
}
```

- [ ] **Step 2: 在 `mySkillsApi` 增加下载方法**

```typescript
downloadCreatedSkill: async (
  skillName: string,
): Promise<{ blob: Blob; filename: string | null }> => {
  const encodedName = encodeURIComponent(skillName);
  return downloadBinary(
    `/market/skills/mine/${encodedName}/download`,
    {
      method: "GET",
      headers: new Headers(mergeHeaders().headers as Record<string, string>),
    },
  );
},
```

- [ ] **Step 3: 在 `marketApi` 增加两个下载方法**

```typescript
downloadSkill: async (
  sourceId: string,
  itemId: string,
): Promise<{ blob: Blob; filename: string | null }> => {
  return downloadBinary(
    `/market/skills/${itemId}/download`,
    {
      method: "GET",
      headers: new Headers(
        mergeHeaders({ "X-Source-Id": sourceId }).headers as Record<string, string>,
      ),
    },
  );
},

downloadSkillVersion: async (
  sourceId: string,
  itemId: string,
  versionId: string,
): Promise<{ blob: Blob; filename: string | null }> => {
  return downloadBinary(
    `/market/skills/${itemId}/versions/${encodeURIComponent(versionId)}/download`,
    {
      method: "GET",
      headers: new Headers(
        mergeHeaders({ "X-Source-Id": sourceId }).headers as Record<string, string>,
      ),
    },
  );
},
```

- [ ] **Step 4: 自查类型一致性**

Check:
- `mySkillsApi` 和 `marketApi` 返回值结构都为 `{ blob, filename }`
- 后续 UI 不需要猜测不同 API 的返回格式

- [ ] **Step 5: Commit**

```bash
git add console/src/api/modules/mySkills.ts console/src/api/modules/market.ts
git commit -m "feat(console): add skill zip download apis"
```

### Task 5: 我的技能详情入口

**Files:**
- Modify: `console/src/pages/MySkills/SkillDetailPanel.tsx`

- [ ] **Step 1: 先加 props，保持组件边界清晰**

```typescript
interface SkillDetailPanelProps {
  // ...
  downloadingSkill: boolean;
  onDownload: (skill: MySkill) => void;
}
```

- [ ] **Step 2: 在按钮区增加“下载 ZIP”按钮**

```tsx
{!skill.is_received && (
  <Button
    size="small"
    onClick={() => onDownload(skill)}
    loading={downloadingSkill}
    style={{ height: 24, borderRadius: 4 }}
  >
    下载 ZIP
  </Button>
)}
```

- [ ] **Step 3: 在父组件实现下载触发**

```typescript
const triggerBrowserDownload = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
};

const handleDownloadSkill = async (skill: MySkill) => {
  setDownloadingSkill(true);
  try {
    const { blob, filename } = await mySkillsApi.downloadCreatedSkill(skill.skill_name);
    triggerBrowserDownload(blob, filename || `${skill.skill_name}.zip`);
    message.success("已开始下载技能包");
  } catch (err) {
    message.error(err instanceof Error ? err.message : "下载失败");
  } finally {
    setDownloadingSkill(false);
  }
};
```

- [ ] **Step 4: 手工检查可见性逻辑**

Check:
- “我创建的”显示按钮
- “我接收的”不显示按钮

- [ ] **Step 5: Commit**

```bash
git add console/src/pages/MySkills/SkillDetailPanel.tsx console/src/pages/MySkills/index.tsx
git commit -m "feat(console): add created skill zip download"
```

### Task 6: 市场详情与版本历史入口

**Files:**
- Modify: `console/src/pages/Market/SkillDetailDrawer.tsx`
- Modify: `console/src/pages/Market/Skills/VersionHistoryModal.tsx`

- [ ] **Step 1: 在市场详情抽屉增加当前版本下载按钮**

```tsx
<Button
  onClick={handleDownloadCurrentVersion}
  style={SECONDARY_BUTTON_STYLE}
>
  下载 ZIP
</Button>
```

- [ ] **Step 2: 实现当前版本下载与提示**

```typescript
const handleDownloadCurrentVersion = async () => {
  if (!sourceId) return;
  setDownloadingCurrent(true);
  try {
    const { blob, filename } = await marketApi.downloadSkill(sourceId, skill.item_id);
    triggerBrowserDownload(blob, filename || `${skill.name}-${skill.version}.zip`);
    message.success("已开始下载当前版本。如需下载历史版本，请打开“版本历史”后按版本单独下载。");
  } catch (err) {
    message.error(err instanceof Error ? err.message : "下载失败");
  } finally {
    setDownloadingCurrent(false);
  }
};
```

- [ ] **Step 3: 在版本历史条目增加“下载”按钮**

```tsx
<Button size="small" onClick={() => handleDownloadVersion(version.version_id)}>
  下载
</Button>
```

- [ ] **Step 4: 实现历史版本下载**

```typescript
const handleDownloadVersion = async (versionId: string) => {
  try {
    const { blob, filename } = await marketApi.downloadSkillVersion(sourceId, itemId, versionId);
    triggerBrowserDownload(blob, filename || `${skillName}-${versionId}.zip`);
    message.success(`已开始下载版本 ${displayVersion(versionId)}`);
  } catch (err) {
    message.error(err instanceof Error ? err.message : "下载失败");
  }
};
```

- [ ] **Step 5: 手工检查交互一致性**

Check:
- 详情页按钮直接下当前版本
- 不新增版本下拉框
- 版本历史逐行下载指定版本

- [ ] **Step 6: Commit**

```bash
git add console/src/pages/Market/SkillDetailDrawer.tsx console/src/pages/Market/Skills/VersionHistoryModal.tsx
git commit -m "feat(console): add market skill zip download actions"
```

### Task 7: 全量验证

**Files:**
- Modify: `docs/superpowers/specs/2026-07-07-skill-zip-download-design.md`（仅当实现偏离 spec 时）

- [ ] **Step 1: 运行后端测试**

Run: `venv/bin/python -m pytest tests/unit/market/test_skill_zip_download.py -v`

Expected: PASS

- [ ] **Step 2: 运行相关前端测试或静态检查**

Run: `cd console && npm test -- --runInBand`

Expected: 与本次改动相关用例 PASS；若仓库没有对应测试，至少运行能覆盖类型和构建的检查命令

- [ ] **Step 3: 做一次手工回归清单**

Check:
- 我的技能创建项下载正常
- 应用市场详情下载正常
- 应用市场历史版本下载正常
- 当前版本下载提示文案准确
- 404 场景不会下载空文件

- [ ] **Step 4: 如实现与 spec 不一致，补文档**

```markdown
- 更新 `docs/superpowers/specs/2026-07-07-skill-zip-download-design.md`
- 保证接口路径、按钮位置、提示文案与实际代码一致
```

- [ ] **Step 5: Commit**

```bash
git add market/src/market/app/routers/skills_browse.py market/src/market/app/routers/skill_versions.py market/src/market/marketplace/zip_download.py console/src/api/modules/mySkills.ts console/src/api/modules/market.ts console/src/pages/MySkills/SkillDetailPanel.tsx console/src/pages/MySkills/index.tsx console/src/pages/Market/SkillDetailDrawer.tsx console/src/pages/Market/Skills/VersionHistoryModal.tsx tests/unit/market/test_skill_zip_download.py docs/superpowers/specs/2026-07-07-skill-zip-download-design.md
git commit -m "feat(skill): support zip downloads for current and historical versions"
```

## Self-Review

- Spec coverage:
  - 我的技能当前版本下载：Task 2、Task 5
  - 市场当前版本下载：Task 3、Task 6
  - 历史版本下载：Task 3、Task 6
  - 当前版本提示文案：Task 6
- Placeholder scan:
  - 已去除 `TODO`、`适当处理`、`类似 Task N` 这类占位语句
- Type consistency:
  - 前端下载 API 统一返回 `{ blob, filename }`
  - 三个后端下载接口统一返回 `application/zip`
