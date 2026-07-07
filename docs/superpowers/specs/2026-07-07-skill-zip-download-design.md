# 技能 ZIP 下载功能设计

## 概述

为“我的技能-我创建的”和“应用市场”补充技能 ZIP 下载能力，保证用户可以下载当前版本技能包，同时在应用市场中按历史版本下载指定版本的技能快照。

本次设计只覆盖 Skill，不覆盖 MCP。

## 目标

- “我的技能-我创建的”支持下载当前技能目录为 ZIP 包
- “应用市场”支持下载当前市场版本技能目录为 ZIP 包
- “应用市场-版本历史”支持按版本下载历史快照 ZIP 包
- 当前版本下载时给出轻提示，告知历史版本下载入口

## 非目标

- 不修改“我接收的”技能下载入口
- 不增加详情页中的版本下拉选择器
- 不新增额外的导出元数据文件或说明文件
- 不改变现有版本快照结构

## 交互设计

### 我的技能

入口位置：

- 页面：`console/src/pages/MySkills/SkillDetailPanel.tsx`
- 范围：仅“我创建的”技能显示下载按钮

交互：

1. 用户在详情面板点击“下载 ZIP”
2. 前端请求后端下载接口
3. 浏览器开始下载 ZIP 文件
4. 成功后提示“已开始下载技能包”

### 应用市场当前版本

入口位置：

- 页面：`console/src/pages/Market/SkillDetailDrawer.tsx`
- 范围：技能详情抽屉操作区

交互：

1. 用户点击“下载 ZIP”
2. 前端直接下载当前市场版本 ZIP
3. 下载发起后显示轻提示：
   `已开始下载当前版本。如需下载历史版本，请打开“版本历史”后按版本单独下载。`

说明：

- 不弹确认框
- 不通过下拉框选择版本

### 应用市场历史版本

入口位置：

- 页面：`console/src/pages/Market/Skills/VersionHistoryModal.tsx`
- 范围：每个版本条目提供独立下载操作

交互：

1. 用户打开“版本历史”
2. 在某一版本条目点击“下载”
3. 前端下载对应版本快照 ZIP
4. 成功后提示“已开始下载版本 {version_id}”

## 后端设计

### 设计原则

- 路由层负责鉴权、参数校验和响应组装
- 打包 ZIP 的文件系统逻辑下沉到可复用 helper
- 当前版本与历史版本共用 ZIP 打包逻辑，只是目录来源不同

### 目录来源

#### 我的技能当前版本

来源目录：

- 用户工作区中的自建技能目录
- 路由位于 `market/src/market/app/routers/skills_browse.py`

目标：

- 将指定技能目录完整打包
- ZIP 内保持原始技能目录结构

#### 应用市场当前版本

来源目录：

- `<marketplace_root>/<source_id>/skills/<item_id>/`
- 路由位于 `market/src/market/app/routers/skills_browse.py`

目标：

- 下载当前市场主目录内容
- 与用户在详情页看到的当前版本保持一致

#### 应用市场历史版本

来源目录：

- `<marketplace_root>/<source_id>/skill_versions/<item_id>/<version_id>/`
- 路由位于 `market/src/market/app/routers/skill_versions.py`

目标：

- 下载对应版本快照目录
- 与版本比对、版本切换所指向的快照语义一致

### 建议新增接口

#### 我的技能下载

```text
GET /market/skills/mine/{skill_name}/download
```

语义：

- 下载当前用户创建的技能 ZIP

#### 应用市场当前版本下载

```text
GET /market/skills/{item_id}/download
```

语义：

- 下载市场当前版本技能 ZIP

#### 应用市场历史版本下载

```text
GET /market/skills/{item_id}/versions/{version_id}/download
```

语义：

- 下载指定历史版本快照 ZIP

### 响应约束

- `Content-Type`: `application/zip`
- `Content-Disposition`: 附带可读文件名
- 文件名建议：
  - 我的技能当前版本：`{skill_name}.zip`
  - 市场当前版本：`{skill_name}-{current_version}.zip`
  - 历史版本：`{skill_name}-{version_id}.zip`

### ZIP 打包规则

- 保留技能目录内的原始文件与目录结构
- 不增加额外包裹目录层级
- 不写入临时说明文件
- 仅打包目标技能目录内容

### 错误处理

- 技能不存在：返回 `404`
- 版本不存在：返回 `404`
- 非法路径或目录越界：返回 `400` 或 `403`
- 打包失败：返回 `500`

## 前端设计

### API 模块

建议在现有 `marketApi` / `mySkillsApi` 基础上增加下载方法，返回 `Blob` 或直接触发浏览器下载。

建议方法：

- `mySkillsApi.downloadCreatedSkill(skillName)`
- `marketApi.downloadSkill(sourceId, itemId)`
- `marketApi.downloadSkillVersion(sourceId, itemId, versionId)`

### 下载实现方式

- 使用 `fetch`/`request` 获取二进制流
- 从响应头读取文件名；读取失败时使用前端兜底文件名
- 通过 `Blob` + `URL.createObjectURL` + 隐藏 `a` 标签触发下载

### 入口变更清单

- `console/src/pages/MySkills/SkillDetailPanel.tsx`
  - 为“我创建的”技能新增“下载 ZIP”按钮
- `console/src/pages/Market/SkillDetailDrawer.tsx`
  - 新增“下载 ZIP”按钮
  - 当前版本下载后显示历史版本入口提示
- `console/src/pages/Market/Skills/VersionHistoryModal.tsx`
  - 为每个版本条目新增“下载”操作

## 文件变更范围

后端：

- `market/src/market/app/routers/skills_browse.py`
- `market/src/market/app/routers/skill_versions.py`
- `market/src/market/marketplace/` 下新增或扩展 ZIP 打包 helper

前端：

- `console/src/api/modules/mySkills.ts`
- `console/src/api/modules/market.ts`
- `console/src/pages/MySkills/SkillDetailPanel.tsx`
- `console/src/pages/Market/SkillDetailDrawer.tsx`
- `console/src/pages/Market/Skills/VersionHistoryModal.tsx`

## 测试设计

### 后端测试

- 我的技能下载接口返回 ZIP 响应且内容可解压
- 市场当前版本下载接口返回当前目录内容
- 历史版本下载接口返回指定快照目录内容
- 技能不存在、版本不存在时返回正确状态码

### 前端测试

- “我创建的”技能显示下载按钮，“我接收的”不显示
- 应用市场详情点击下载时发起当前版本下载
- 当前版本下载后显示历史版本提示文案
- 版本历史中点击某个版本时发起对应版本下载

## 风险与注意事项

- ZIP 打包涉及文件 I/O，需避免阻塞主线程，建议复用现有 `asyncio.to_thread()` 风格
- 历史版本快照目录可能缺失，接口需明确返回 404，不能静默回退到当前版本
- 文件名应兼容中文与特殊字符，必要时做安全化处理

## 方案结论

本次采用“当前版本直接下载 + 历史版本在版本历史中逐条下载”的方案：

- 保持详情页轻量
- 复用现有版本历史心智
- 前后端改动边界清晰
- 后续可平滑扩展到 MCP 下载能力
