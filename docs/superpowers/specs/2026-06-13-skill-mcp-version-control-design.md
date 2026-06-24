# Skill / MCP 版本控制重构设计

> 状态：草案 v1
> 作者：smilehan
> 日期：2026-06-13
> 关联文件：本文档落地后会拆分为 `docs/plans/version-control-impl-plan.md`

---

## 1. 背景

CoPaw 当前对 Skill 与 MCP 的"版本"概念分散在四处实现，且存在以下问题：

1. **「我的技能」内的版本不会自动递增**：用户上传 zip 到自己工作区时，若 SKILL.md 没写 version，部分路径默认 `1.0.0`、部分路径直接覆盖、一些路径根本不读 SKILL.md。语义不一致。
2. **「我的 MCP」每次编辑都强制 patch+1**：无视用户是否真改了内容。
3. **市场名称不是真正唯一**：现状是 `(name, creator_id)` 唯一。不同用户同名同步会被拒绝并被建议改名为 `name_1`，与"市场是单一权威"的产品语义冲突。
4. **MCP 没有版本快照系统**：只有单一 `MarketItem.version` 字段，与 Skill 的 `mcp_versions/` 完整快照能力不对等。
5. **跨服务字段不一致**：`market` 侧 `MCPClientConfig` 有 `version` / `received_version` 字段；`swe` 侧 `MCPClientConfig` 没有。同一份 `agent.json` 被两个模型读写。
6. **重复实现**：4 套 SKILL.md frontmatter 解析器、5 套 `_bump_patch` 实现，散落各处。

本设计的目标是把这些问题统一收敛到一套清晰的版本规则，并落实为可分阶段交付的工程任务。

---

## 2. 范围与非目标

### 2.1 范围

* 「我的技能」 / 「我的 MCP」内部的版本号决策与持久化（**仅 market 侧的端点**：`/market/skills/upload`、`/market/my-mcp/*`）。
* 「我的技能」 / 「我的 MCP」 → 应用市场的同步流程及其版本记录。
* 应用市场 → 用户工作区的分发流程（仅校对，不变更现有逻辑）。
* 重复代码收敛（frontmatter 解析、版本递增工具）—— **仅 market 侧** 的多套实现合并为一份。

### 2.2 非目标

* **存量数据迁移**：本次不迁移历史 `(name, creator_id)` 重复条目，仅对新发布生效（用户已确认）。
* **「同步到市场」按钮放开给普通用户**：保留现行 `X-Manager: true` 后端约束（用户已确认）。
* **数据库表结构变更**：所有版本元数据继续走 JSON 文件存储，仅 `swe_marketplace_operation_logs` / `swe_user_item_operation_logs` 维持现状。
* **不修改 swe 服务的代码**（用户已确认 Q6）。具体含义：
  - 不改 `src/swe/agents/skills_manager.py` 的 frontmatter 解析逻辑（保持自身正确）；
  - 不改 `src/swe/config/config.py` 的 `MCPClientConfig`（不增 `version`/`received_version` 字段）；
  - 不改 `src/swe/app/routers/skills.py` 的 `POST /skills` / `POST /skills/upload` 行为。
  - **注意**：这意味着 console 的 Agent/Skills 页面（走 swe `POST /skills`）创建/上传 skill 时**不走 R1/R2 版本规则**；R1/R2 只对市场前端的"我的技能"页（走 market `POST /market/skills/upload`）生效。两条路径短期版本行为不一致是已知遗留状态。
  - **风险**：swe 侧 `MCPClientConfig` 模型没有 `version`/`received_version` 字段且 `extra` 为默认 `ignore`，理论上 swe 改写 `agent.json` 时可能抹掉 market 写入的这两个字段。本次明确不修，作为已知风险记录在 §12。如未来观察到字段丢失，再做最小修复（一行 `extra="allow"`）。

---

## 3. 关键概念与术语

| 术语 | 含义 |
|---|---|
| **我的技能 / 我的 MCP** | 用户自有工作区下的 skill / MCP，存储于 `<swe_root>/<scope_id>/workspaces/<agent_id>/` 下 |
| **市场（marketplace）** | 多用户共享的 skill / MCP 仓库，存储于 `<marketplace_root>/<source_id>/` 下，索引为 `index.json` |
| **`version_text`（用户侧）** | 用户工作区某 skill / MCP 当前的版本号；存于 `skill.json.metadata.version_text` 或 `agent.json.mcp.clients[*].version` |
| **`MarketItem.version`（市场侧）** | 市场上某条目的"当前版本"，与最新版本快照（`is_current`）的 `version_id` 同步 |
| **`MarketItem.creator_id/creator_name`（市场侧）** | **当前 `is_current` 快照的来源用户**。每次发布或切版本时跟随更新（与现状代码行为一致）。历史归属由 `SkillVersion` 列表承载 |
| **`SkillVersion` / `MCPVersion`** | 市场版本快照：`<marketplace_root>/<source_id>/{skill,mcp}_versions/<item_id>/v<x.y.z>/` 下的文件 + `versions.json` 里的元数据 |
| **`source_user_id/name`** | 一次同步动作的"内容来源用户"（即被引用工作区的拥有者）。空串表示无来源（admin 走 zip 上传路径） |
| **`source_user_version`** | 同步动作发生时，`source_user` 在自己工作区的 `version_text`；admin zip 上传无来源时记 `v0.0.0` |
| **`received_version`** | 用户工作区收到分发时记录的市场版本号；用于 `has_update` 比对（已存在） |

---

## 4. 现状摘要（事实）

### 4.1 我的技能 / 我的 MCP

| 项 | 现状代码位置 | 行为 |
|---|---|---|
| 用户工作区 skill `version_text` 来源 | `skills_manager.py:466 _extract_version` | 读 SKILL.md frontmatter `version` / `metadata.version` / `metadata.builtin_skill_version`，无则空串 |
| 用户上传 zip 到工作区时的版本决策 | `skills_browse.py:405 _build_skill_metadata` | ① SKILL.md 有 → 用之 ② 无且已存在 → patch+1 ③ 无且新建 → `1.0.0` |
| 用户在 swe 侧 `POST /skills` 创建 skill | `src/swe/app/routers/skills.py:885 create_skill` | **不走任何版本决策**，version 完全取决于 SKILL.md |
| 用户编辑 MCP 时的版本决策 | `my_mcp.py:576 update_my_mcp` | **每次必 patch+1**，不读请求体里的 version 字段 |
| 用户创建 MCP | `my_mcp.py:478 create_my_mcp` | 默认 `1.0.0` |

### 4.2 应用市场

| 项 | 现状代码位置 | 行为 |
|---|---|---|
| 市场条目唯一性 | `service.py:_upsert_skill_item` / `publish_mcp` | `(name, creator_id)` 唯一 |
| 同名不同人同步 | 抛 `SkillNameConflictError` / `MCPNameConflictError` | 返回 `suggested_name = "<name>_1"` |
| Skill 版本快照 | `version_service.py` + `version_models.py` | 完整：`v<x.y.z>/` + `versions.json`，记录 `created_by(_name)`, `created_at`, `description`, `signature`, `is_current`, `is_initial` |
| MCP 版本快照 | **无** | 仅有 `MarketItem.version` 单字段 |
| Skill 同版本号同内容再发布 | `version_service.py:138-153` | 跳过快照，但**会翻 `is_current`**，多用户场景下会把指针拉回旧版本（潜在 bug） |

### 4.3 同步动作的端点矩阵

| 动作 | 端点 | 权限 | 实际行为 |
|---|---|---|---|
| 用户上传 zip 到自己工作区 | `POST /market/skills/upload` | 普通用户 | ① 中描述 |
| admin 上传 zip 到市场 | `POST /market/skills/publish-upload` | manager | 直接落 `index.json` + 创建初始快照 |
| admin 引用某用户工作区发布到市场 | `POST /market/skills` (PublishSkillRequest) | manager | 从 `<creator_id>` 工作区拷文件，发布到市场 |
| admin 把市场技能分发到一批用户 | `POST /market/skills/{item_id}/distribute` | manager | 拷市场文件到各用户工作区，写 `received_version` |
| admin 同步「我的 MCP」到市场（单个） | `POST /market/my-mcp/{client_key}/publish` | manager | 走 `_publish_client_to_market` |
| admin 同步「我的 MCP」到市场（批量） | `POST /market/my-mcp/publish` | manager | 同上 |

> 关键事实：**普通用户的 UI「同步到市场」按钮，后端实际由 manager 调用，从「实际操作者」的工作区抓文件**。本次不变更这一权限模型。

### 4.4 重复实现盘点

**SKILL.md frontmatter 解析器**：

1. `src/swe/agents/skills_manager.py:424-475` — 用 `python-frontmatter` 包（**权威**）
2. `market/src/market/marketplace/version_service.py:732-767` — 手写 line parser
3. `market/src/market/marketplace/service.py:352-367` — 手写 line parser
4. `market/src/market/app/routers/skills_market.py:125-165` — 手写 line parser
5. `market/src/market/app/routers/skills_browse.py:356-383` — 手写 line parser
6. `market/src/market/app/routers/skill_versions.py:60-97` — 手写 line parser

**`_bump_patch` 实现**：

1. `market/src/market/marketplace/service.py:215-224`
2. `market/src/market/marketplace/version_service.py:707-730`（最完整，处理 2 段式版本号）
3. `market/src/market/app/routers/skills_browse.py:386-402`（同上）
4. `market/src/market/app/routers/my_mcp.py:137-146`
5. `market/src/market/app/routers/skills_market.py` 复用 `service` 的版本

---

## 5. 新逻辑（产品规则）

### 5.1 我的技能 / 我的 MCP（用户自有版本）

> **范围**：仅作用于用户自己工作区内的版本号 `version_text`。与市场 `MarketItem.version` 隔离。

#### 规则 R1 — 首次创建

| 来源 | 行为 |
|---|---|
| SKILL.md frontmatter 含 `version` / `mcp 请求体含 version` | 用之（去除前导 `v`/`V`，去除引号） |
| 无 | 默认 `1.0.0` |

#### 规则 R2 — 非首次（编辑或重新上传）

| 来源 | 行为 |
|---|---|
| SKILL.md 含 `version` / 请求体含 `version` | 用之 |
| 无 + 内容**有变化**（signature 不同） | 在已有 `version_text` 基础上 patch+1 |
| 无 + 内容**无变化** | 保持原版本号不动 |

> **变更点**：当前 MCP 的 `update_my_mcp` 不读请求体 version 且每次必 bump。要按 R2 修正：先看请求体显式 version，没有再看内容是否变化。

#### 规则 R3 — 隔离

用户工作区版本号与市场版本号互相独立。从市场分发到用户工作区时，仅写入 `metadata.received_version`；不覆盖、不影响用户后续在工作区里递增 `version_text`。

### 5.2 应用市场（市场版本）

#### 规则 R4 — 名称硬唯一

* 市场上每个 `name`（在同一个 `source_id` 内）只有**一条** `MarketItem`。
* 不同用户同名同步 → **续接到现有 `MarketItem`**，创建新版本快照（不再返回 `suggested_name`）。
* `MarketItem.creator_id` / `creator_name` 表示**当前 `is_current` 快照的来源用户**，每次发布或切版本时跟随更新（与现状代码行为一致）。历史归属（每个版本是谁同步的）由 `SkillVersion.source_user_*` 字段承载。

#### 规则 R5 — 同步快照记录

每次产生新快照时，记录：

| 字段 | 含义 |
|---|---|
| `version_id` | 该快照的版本号 |
| `created_at` | 快照时间（=同步时间） |
| `created_by` / `created_by_name` | **触发同步动作的操作者**（`X-User-Id`，本系统下都是 admin） |
| `source_user_id` / `source_user_name` | **本次内容来源的用户**（被引用工作区的拥有者）；admin zip 上传场景为空串 |
| `source_user_version` | 同步时刻 `source_user` 工作区的 `version_text`；规则见 R6 |
| `description` | 自动生成或用户填写的变更描述 |
| `signature` | 文件 SHA256 签名（已有） |
| `is_current` / `is_initial` | 已有标记 |

> **`created_by` 与 `source_user_*` 的区分**：
> * `created_by` 永远是按按钮的 admin（来自 `X-User-Id`）；
> * `source_user_*` 是内容来源用户。当 admin 通过 `_publish_client_to_market`（MCP）发布自己工作区的 MCP 时，二者相同；当 admin 通过 `PublishSkillRequest` 显式指定 `creator_id` 拉某用户工作区时，二者不同；当 admin 走 zip 上传（无任何用户工作区来源）时，`source_user_*` 全部为空串。
> * 不再使用 `synced_via` 枚举字段——通过 `source_user_id` 是否为空 / 是否等于 `created_by`，足以区分这三种情形，无需冗余枚举。

#### 规则 R6 — `source_user_*` 的取值边界

| 场景 | 后端端点 | `source_user_id` | `source_user_version` |
|---|---|---|---|
| admin 走 `publish-upload` 直接 zip 上传 skill 到市场 | `POST /market/skills/publish-upload` | `""` | `"v0.0.0"` |
| admin 走 `publish_skill` 引用某用户工作区发布 skill | `POST /market/skills` | `req.creator_id` | 被引用用户当前 `version_text` |
| admin 走 `mcp_market.upload_mcp` 直接 zip 上传 MCP 到市场 | `POST /market/mcp/upload` | `""` | `"v0.0.0"` |
| admin 同步自己工作区的 MCP 到市场 | `POST /market/my-mcp/.../publish` | `X-User-Id` | 操作者本人 `agent.json.mcp.clients[*].version` |
| 用户工作区里 source=`marketplace:*` 的内容直接同步回市场 | （前端拦截 + 后端兜底 R7） | — | — |

> **解读**：
> * 普通用户**不会**直接调用任何"同步到市场"端点（被 `_require_manager` 拦截，UI 也不展示按钮）。所有 `source_user_*` 的填写都发生在 admin 触发的同步动作里。
> * `MCP` 路径**只能同步自己工作区的 MCP**（`load_agent_config_for_request` 仅加载请求者的 `agent.json`），所以 `source_user_id` 必然等于 `X-User-Id`。
> * `Skill` 路径里 admin 可显式指定他人的 `creator_id` 来拉对方工作区——但这是当前代码遗留能力，是否仍要保留是产品决策（见 §10 Q5）。
> * 用户原话规则 5 中 "用户直接从应用市场上传的 skill 记 v0.0.0" 在新规则下唯一对应"admin zip 上传"路径。

#### 规则 R7 — 同版本同内容兜底

`version_service.py:138-153` 现行逻辑在多用户续接场景下会把 `is_current` 翻回旧版本，破坏链表语义。新行为：

* 同 `version_id` 同 signature → **no-op**：不创建快照，不修改 `is_current`，不更新 `MarketItem.version` / `creator_id`，返回 200 + `{ "skipped": true, "reason": "no_change" }`。
* 同 `version_id` 不同 signature → 报 409 + 提示用户在 SKILL.md 显式指定新版本或允许 auto-bump。

#### 规则 R8 — 切换版本同步更新 MarketItem 归属

`switch_version` 操作（`POST /market/skills/{item_id}/versions/{version_id}/switch`）现状只更新 `MarketItem.version`（`skill_versions.py:100-129 _update_skill_index`）。新行为：

* 切换到目标快照后，把 `MarketItem.creator_id` / `creator_name` 也同步为该快照的 `source_user_id` / `source_user_name`（若 `source_user_id` 为空，回退为 `created_by` / `created_by_name`）。
* 这样保证"市场列表显示的归属"始终对应当前 `is_current` 快照的真实来源。

---

## 6. 数据模型变更

### 6.1 `MarketItem`（语义不变，逻辑代码改）

* 字段无变更。
* `creator_id` / `creator_name` 语义保持现状：**等于当前 `is_current` 快照的来源**。每次发布或切版本时跟随更新，与现状代码 `_upsert_skill_item:380-382` / `_apply_publish_update:1948-1955` 行为一致。
* **逻辑变更**：
  - "按 `(name, creator_id)` 查找已有条目"全部改为"按 `name` 查找"。
  - 移除 `SkillNameConflictError` / `MCPNameConflictError` 的"同名不同人"分支（同名不同人不再是冲突，是续接）。

### 6.2 `SkillVersion`（新增字段）

```python
class SkillVersion(BaseModel):
    version_id: str
    created_at: str
    created_by: str = ""           # 已有 → 操作者（按按钮的人，admin 的 X-User-Id）
    created_by_name: str = ""      # 已有
    description: str = ""          # 已有
    signature: str = ""            # 已有
    is_current: bool = False       # 已有
    is_initial: bool = False       # 已有
    # 新增：
    source_user_id: str = ""       # 内容来源用户 ID；空串=admin zip 上传，无来源
    source_user_name: str = ""     # 内容来源用户名
    source_user_version: str = ""  # 来源用户的 version_text；admin zip 路径记 "v0.0.0"
```

> 旧 `versions.json` 的兼容性：Pydantic 字段默认值即可向后兼容；旧记录读出来这三个字段为空串，等价于"历史数据无来源信息"，符合事实。
> **不再使用 `synced_via` 枚举字段**（设计 v1 草案中曾提出，已删除）：通过判断 `source_user_id` 是否为空 / 是否等于 `created_by` 已可区分所有场景，无需冗余枚举。

### 6.3 `MCPVersion`（新增模型，决议 Q3：signature 仅 `mcp.json`）

```python
class MCPVersion(BaseModel):
    version_id: str
    created_at: str
    created_by: str = ""
    created_by_name: str = ""
    description: str = ""
    signature: str = ""            # SHA256(canonical_json(mcp.json))，仅 mcp.json 内容
    is_current: bool = False
    is_initial: bool = False
    source_user_id: str = ""
    source_user_name: str = ""
    source_user_version: str = ""

class MCPVersionsManifest(BaseModel):
    client_key: str = ""
    name: str = ""
    versions: list[MCPVersion] = Field(default_factory=list)
```

存储路径：`<marketplace_root>/<source_id>/mcp_versions/<item_id>/{versions.json, v<x.y.z>/mcp.json}`

> **signature 计算**：仅对 `mcp.json` 反序列化为字典后做 canonical JSON dump（key 排序、固定缩进）再 SHA256。不纳入任何"关联资源文件"——MCP 当前没有这个概念。
> **MCP 路径下 `source_user_id` 总是等于 `created_by`**，因为 `_publish_client_to_market` 只能加载操作者本人的 `agent.json`（除非未来引入 admin 跨用户加载能力，目前无）。

### 6.4 `MCPClientConfig`（swe / market 字段对齐）

`src/swe/config/config.py:1165 MCPClientConfig` 添加 `version: str = "1.0.0"` 与 `received_version: str = ""`，与 `market/src/market/runtime/config_store.py:45 MCPClientConfig` 字段一致。避免 swe 侧读出 `agent.json` 时这两个字段被 Pydantic 丢弃。

---

## 7. 共享工具下沉

## 7. 共享工具下沉（仅 market 侧）

### 7.1 frontmatter 解析与版本工具（决议 Q1 + Q6 联合调整）

> **作用范围限定**：本次仅在 market 侧整合多套重复实现。**swe 侧 `src/swe/agents/skills_manager.py:424-475` 的 frontmatter 逻辑保持原状不动**（决议 Q6）。
> 后果：swe 侧 `_extract_version` 会回退到 `metadata.version` / `metadata.builtin_skill_version`，而 market 侧统一只看顶层 `version:` 行——两边对"非顶层 version"字段的处理仍不一致。日常 SKILL.md 只用顶层 `version:` 时不影响；如果未来发现兼容问题，再做单独修复。

**market 侧** — 新建 `market/src/market/utils/skill_md.py`：

```python
def parse_frontmatter(md_content: str) -> dict[str, Any]:
    """统一的 SKILL.md frontmatter 解析。基于 python-frontmatter 包。"""

def extract_version(md_content: str) -> str:
    """提取 version 字段，去除 v 前缀和引号；不存在则返回空串。"""

def extract_metadata(md_content: str) -> dict:
    """提取 name / description / version / chinese_name 等。"""
```

替换以下文件中的本地实现：

* `market/src/market/marketplace/version_service.py:732-767`
* `market/src/market/marketplace/service.py:352-367`
* `market/src/market/app/routers/skills_market.py:125-165`
* `market/src/market/app/routers/skills_browse.py:356-383`
* `market/src/market/app/routers/skill_versions.py:60-97`

### 7.2 `bump_patch` / `normalize_version` 工具（仅 market 侧）

新建 `market/src/market/utils/version.py`：

```python
def bump_patch(version: str) -> str:
    """1.2.3 → 1.2.4；1.5 → 1.5.1；非法格式 → <version>.1。"""

def normalize_version(version: str) -> str:
    """去除前导 v/V 与引号空白。"""
```

替换：

* `market/src/market/marketplace/service.py:215-224`
* `market/src/market/marketplace/version_service.py:707-730`
* `market/src/market/app/routers/skills_browse.py:386-402`
* `market/src/market/app/routers/my_mcp.py:137-146`

---

## 8. 端点行为变更总览

| 端点 | 现状 | 新行为 |
|---|---|---|
| `POST /market/skills/upload` (我的技能上传 zip) | 已正确执行 R1/R2 | 不变（仅替换为共享工具） |
| `POST /skills` (swe 侧创建 skill) | 不读版本 | **不变**（决议 Q6：本次不改 swe） |
| `PUT /market/skills/mine/{name}/files/...` (编辑文件) | 通过 `save_skill_file` patch+1 | 改为：先读 SKILL.md 显式 version，无则 patch+1（且仅在 signature 变化时） |
| `POST /market/my-mcp` (创建 MCP) | 默认 `1.0.0` | 不变 |
| `PUT /market/my-mcp/{key}` (编辑 MCP) | **每次必 patch+1** | 按 R2：请求体含 version → 用之；否则若 signature 变化 → patch+1；无变化 → 不动 |
| `POST /market/skills` (admin 引用用户工作区发布) | 同名不同人 → 409 + suggested_name；`creator_id` 取 `req.creator_id` | 按 R4 续接到现有 `MarketItem`；快照 `source_user_id=req.creator_id`、`source_user_version=被引用用户 version_text`；`created_by=X-User-Id`（admin）；`MarketItem.creator_id` 同步覆盖为 `req.creator_id` |
| `POST /market/skills/publish-upload` (admin zip 上传市场) | 同名不同人 → 409 + suggested_name | 按 R4 续接；快照 `source_user_id=""`、`source_user_version="v0.0.0"`；`created_by=X-User-Id`；`MarketItem.creator_id` 同步覆盖为 `X-User-Id`（admin） |
| `POST /market/my-mcp/{key}/publish` (单个 MCP 同步) | 同名不同人 → 409 + suggested_name | 按 R4 续接 + 创建 `MCPVersion`；快照 `source_user_id=created_by=X-User-Id`、`source_user_version=操作者本地 version`；`MarketItem.creator_id` 同步覆盖 |
| `POST /market/my-mcp/publish` (批量 MCP 同步) | 同上 | 同上 |
| `POST /market/mcp/upload` (admin zip 上传 MCP 到市场) | 同上 | 同 admin zip 路径：`source_user_id=""`、`source_user_version="v0.0.0"`、`MarketItem.creator_id=X-User-Id` |
| `POST /market/skills/{item_id}/versions/{version_id}/switch` | 仅更新 `MarketItem.version` | 按 R8 同时更新 `MarketItem.creator_id/creator_name`，跟随目标快照的 `source_user_*`（空则回退为 `created_by`） |
| `POST /market/skills/{item_id}/distribute` | 写 `received_version`，不影响 `version_text` | 不变 |
| `POST /market/mcp/{item_id}/distribute` | 同上 | 不变 |

---

## 9. 工程任务拆解（提交顺序）

| 编号 | 任务 | 影响文件 | 风险 | 依赖 |
|---|---|---|---|---|
| **T1** | 新建 `market/src/market/utils/skill_md.py` 与 `version.py` | 新增文件 | 低 | — |
| **T2** | 替换 market 侧所有 frontmatter 解析器与 `_bump_patch` 调用为共享工具 | 5 个 market 文件 | 低 | T1 |
| ~~T3~~ | ~~swe 侧 `MCPClientConfig` 增补 `version` / `received_version` 字段~~ | ~~`src/swe/config/config.py`~~ | — | **已取消（决议 Q6）** |
| ~~T4~~ | ~~swe 侧 `POST /skills` 路径接入 R1/R2 版本决策~~ | ~~`src/swe/app/routers/skills.py`、`src/swe/agents/skills_manager.py`~~ | — | **已取消（决议 Q6）** |
| **T5** | 修正 `update_my_mcp`：尊重请求体 version + 内容未变不 bump；响应体新增 `version_changed: bool` / `previous_version: str` / `bump_reason: "explicit" \| "auto" \| "unchanged"` 字段（决议 Q4） | `market/src/market/app/routers/my_mcp.py:533-591`、`schemas.py` MyMCPDetail | 中（行为变更，前端可选消费提示字段） | T1 |
| **T6** | `SkillVersion` 模型增补 3 个新字段（`source_user_id/name/version`）；`create_version_snapshot` 签名扩展，调用方传入 `source_user_*` 与 `created_by` | `version_models.py`、`version_service.py` | 中 | — |
| **T7** | `version_service.py:138-153` 同版本同内容逻辑修复（不再翻 `is_current`）；`switch_version` 流程中追加 R8（同步更新 `MarketItem.creator_id/creator_name`） | `version_service.py`、`skill_versions.py:_update_skill_index` | 低，但需测试 | T6 |
| **T8** | `service.py:_upsert_skill_item` 改为按 `name` 续接，移除 `SkillNameConflictError` 同名分支 | `service.py` | **高**（产品行为变更） | T6 |
| **T9** | `skills_market.publish_skill` / `publish_skill_upload` / `_process_single_skill` 透传 source_user 与 created_by 到 snapshot | `skills_market.py`、`skills_browse.py`、`service.py` | 中 | T8 |
| **T10** | 新建 `version_models.py` 增加 `MCPVersion` / `MCPVersionsManifest`；新建 `mcp_version_service.py` 平行实现快照能力 | 新增 + 修改 | 高（新系统） | T1, T6 |
| **T11** | `service.publish_mcp` 接入 MCP 快照能力，按 `name` 续接，移除同名拒绝分支 | `service.py:1933-2105` | **高** | T10 |
| **T12** | `my_mcp.py:_publish_client_to_market` 与 `mcp_market.py:upload_mcp` 透传 source_user / created_by | `my_mcp.py`、`mcp_market.py` | 中 | T11 |
| **T13** | 新增市场端 MCP 版本浏览 API（与 `skill_versions.py` 对称） | 新增 router | 低 | T10 |
| **T14** | UI 隐藏 `source=marketplace:*` 的"同步到市场"按钮；后端兜底 R7 | 前端 + `service.py` | 低 | T7 |
| **T15** | 测试用例：R1/R2/R4/R5/R6/R7/R8 各场景的端到端 fixture | `market/tests/` | — | 全部 |

---

## 10. 决议项（已敲定）

| # | 问题 | 决议 |
|---|---|---|
| Q1 | 共享工具的物理位置 | **仅 market 侧一份**：`market/src/market/utils/skill_md.py`、`version.py`。swe 侧不动（详见 Q6）|
| Q2 | T8 完成后已存在的"同名不同人多条 `MarketItem`" UI 呈现 | **直接展示，不做特殊处理**；本次不考虑存量问题 |
| Q3 | MCP signature 计算范围 | **仅 `mcp.json`**（canonical JSON 后 SHA256） |
| Q4 | T5 行为变更（MCP 不再每次必 bump）的前端配合 | **后端在响应里返回"未递增"提示字段**，前端是否消费由前端自定 |
| Q5 | `POST /market/skills` (admin 显式指定他人 `creator_id` 的端点) | **保留**：admin 仍可通过该端点把某用户工作区的 skill 推到市场；快照 `source_user_id=req.creator_id`、`created_by=X-User-Id`（admin） |
| Q6 | 是否修改 swe 服务代码 | **不修改**：本次完全不动 swe 侧。R1/R2 仅通过 market 侧的 `/market/skills/upload` 等端点生效；console Agent/Skills 页（走 swe `POST /skills`）短期保持原行为。swe `MCPClientConfig` 缺字段问题作为已知风险记录，未来如观察到字段丢失再做最小修复 |

---

## 11. 验收标准

完成后必须满足：

1. ~~同一份 `agent.json` 在 swe 与 market 两端读写时，`version` / `received_version` 字段不会丢失（T3）~~ — **本条已取消**（决议 Q6：不改 swe）。作为已知风险见 §12。
2. ~~`POST /skills` 与 `POST /market/skills/upload` 两条创建路径产生的 `version_text` 一致（T4）~~ — **本条已取消**（决议 Q6）。两条路径短期保持版本行为不一致。
3. `PUT /market/my-mcp/{key}` 在 body 不变 + 数据库内容不变时，**不**触发 patch+1（T5）。
4. 不同用户依次同步同名 skill 到市场后，市场上**只有一条** `MarketItem`，`creator_id` 始终等于"当前 `is_current` 快照的 `source_user_id`"（无来源时回退为 `created_by`），且 `SkillVersion` 列表能按时间倒序看出每个同步动作的 `source_user_id/name/version`（T6/T8/T9）。
5. admin 走 `publish-upload` 上传的同名 skill 在快照里 `source_user_id=""`、`source_user_version="v0.0.0"`、`MarketItem.creator_id=X-User-Id`（admin 自己）（T9）。
6. MCP 的版本能力与 Skill 完全对称：`GET /market/mcp/{item_id}/versions` 返回快照列表（T10/T13）。
7. 市场上某 skill 的 `is_current` 不会因为"同版本号同内容再发布"被翻回旧版本（T7）。
8. `switch_version` 切版本后，`MarketItem.creator_id/creator_name/version` 三者一致指向目标快照（T7）。

---

## 12. 风险与回退

| 风险 | 缓解 |
|---|---|
| T8 改 `(name, creator_id)` 唯一为 `name` 唯一后，旧客户端可能仍尝试发起带 `_1` 命名的请求 | T8 完成后，前端的 `suggested_name` UI 走查一遍移除；后端忽略 `_1` 后缀的兜底逻辑保留两个版本周期 |
| T10 引入 MCP 快照后，老 `MarketItem.version` 单字段语义需要继续维护以兼容旧 UI | `_apply_publish_update` 仍同步写 `MarketItem.version = 最新 version_id` |
| T6 修改 `versions.json` schema 后，旧文件读出新字段为空 | Pydantic 默认值保证兼容；T15 加专门的 fixture 测试 |
| T5 行为变更后，频繁编辑 MCP 但内容未变的用户会看到版本号"卡住" | 这是预期行为，UI 文案配合调整 |
| **swe 侧 `MCPClientConfig` 缺 `version`/`received_version` 字段（决议 Q6 不修）** | swe 路径写 `agent.json` 时若用 `model_dump(exclude_unset=False)` 会抹掉未声明字段。**已知风险**：观察 production 是否有用户的 `version`/`received_version` 字段被静默清空，若发生再做最小修复（一行 `extra="allow"` 或加两个字段）。期间 market 侧每次读写 `agent.json` 时建议**主动补回**这两个字段以减少 swe 误抹的窗口 |
| **swe Agent/Skills 页（走 swe `POST /skills`）短期不走 R1/R2** | 已知遗留：用户在该页面创建/上传 skill 时版本仍由 SKILL.md 决定且不递增。等本次 market 侧落地稳定后，可再开一轮单独 ticket 把 swe 侧对齐 |

---

## 13. 后续动作

设计文档评审通过后，拆分为：

* `docs/plans/version-control-impl-plan.md` — 含 T1-T15 每项的具体改动清单与验证步骤
* `openspec/specs/version-control/spec.md` — 若 openspec 流程要求，补对应规约文件
