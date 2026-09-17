# 技能分发预览功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在分发弹窗中展示用户技能持有情况，支持首次分发和覆盖更新两种场景

**Architecture:** 概览卡片 + 用户状态标记双层展示，两种模式（按用户/按机构）统一设计

**Tech Stack:** React + Ant Design + FastAPI (Market)

---

## 文件结构

### 后端新增

| 文件 | 职责 |
|------|------|
| `market/src/market/app/routers/skills_market.py` | 新增预览 API 端点 |
| `market/src/market/marketplace/service.py` | 新增预览查询方法 |
| `market/src/market/marketplace/schemas.py` | 新增预览响应模型 |

### 前端新增

| 文件 | 职责 |
|------|------|
| `console/src/api/modules/market.ts` | 新增预览 API 调用函数 |
| `console/src/components/DistributionPreview/index.tsx` | 概览卡片组件 |
| `console/src/components/DistributionPreview/index.module.less` | 概览卡片样式 |

### 前端修改

| 文件 | 职责 |
|------|------|
| `console/src/components/TenantSelector/index.tsx` | 添加用户状态标记显示 |
| `console/src/components/TenantSelector/index.module.less` | 添加状态样式 |
| `console/src/pages/Market/DistributeTargetModal.tsx` | 集成预览组件 |

---

## Task 1: 后端预览 API 数据模型

**Files:**
- Modify: `market/src/market/marketplace/schemas.py`

- [ ] **Step 1: 添加预览响应模型**

在 `schemas.py` 文件末尾添加：

```python
class UserSkillStatus(BaseModel):
    """用户技能状态."""

    tenant_id: str
    tenant_name: str | None = None
    bbk_id: str | None = None
    status: str  # first_time / update / conflict
    current_version: str | None = None  # update 时显示当前版本


class DistributionPreviewResponse(BaseModel):
    """分发预览响应."""

    skill_version: str
    users: list[UserSkillStatus] = Field(default_factory=list)
    distributed_user_ids: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: 验证模型定义**

运行后端服务启动检查（无语法错误）：

```bash
cd market && python -c "from src.market.marketplace.schemas import DistributionPreviewResponse, UserSkillStatus; print('OK')"
```

Expected: 输出 `OK`

---

## Task 2: 后端预览查询方法

**Files:**
- Modify: `market/src/market/marketplace/service.py`

- [ ] **Step 1: 添加预览查询 SQL 常量**

在 `service.py` 的 SQL 常量区域（约 line 200）添加：

```python
# 查询用户技能持有状态
_QUERY_USER_SKILL_STATUS_SQL = """
SELECT tenant_id, tenant_name, bbk_id, source, version_text
FROM swe_skills
WHERE skill_name = %s AND source_id = %s AND tenant_id IN ({placeholders})
"""
```

- [ ] **Step 2: 添加预览查询方法**

在 `MarketplaceService` 类中添加方法（约 line 1650，在 `_resolve_target_users` 方法附近）：

```python
async def get_distribution_preview(
    self,
    source_id: str,
    item_id: str,
    target_tenant_ids: list[str],
) -> dict:
    """获取技能分发预览，返回每个用户的技能持有状态.

    Args:
        source_id: 来源 ID
        item_id: 市场条目 ID
        target_tenant_ids: 目标用户 ID 列表

    Returns:
        包含 skill_version、users、distributed_user_ids 的字典
    """
    # 加载市场条目
    items = load_index(self.marketplace_root, source_id)
    item = next(
        (
            i
            for i in items
            if i.item_id == item_id and i.item_type == "skill"
        ),
        None,
    )
    if item is None:
        raise ValueError(f"Item {item_id} not found in source {source_id}")

    skill_version = item.version
    skill_name = normalize_skill_name(item.name)

    # 查询用户技能状态
    users_status: list[dict] = []
    distributed_user_ids: list[str] = []

    if self.db.is_connected and target_tenant_ids:
        placeholders = ",".join(["%s"] * len(target_tenant_ids))
        sql = _QUERY_USER_SKILL_STATUS_SQL.format(placeholders=placeholders)
        rows = await self.db.fetch_all(
            sql,
            (skill_name, source_id, *target_tenant_ids),
        )

        # 构建状态映射
        user_skill_map = {row["tenant_id"]: row for row in rows}

        # 查询已分发用户（从操作日志）
        dist_rows = await self.db.fetch_all(
            _QUERY_DISTRIBUTIONS_SQL,
            (source_id, item_id, "skill"),
        )
        distributed_user_ids = [
            row["target_user_id"] for row in dist_rows if row["target_user_id"] in target_tenant_ids
        ]

        # 查询用户基本信息
        placeholders = ",".join(["%s"] * len(target_tenant_ids))
        user_sql = _QUERY_USERS_BY_TENANT_IDS_SQL.format(placeholders=placeholders)
        user_rows = await self.db.fetch_all(
            user_sql,
            (source_id, *target_tenant_ids),
        )
        user_info_map = {row["tenant_id"]: row for row in user_rows}

        # 构建每个用户的状态
        for tenant_id in target_tenant_ids:
            user_info = user_info_map.get(
                tenant_id,
                {"tenant_id": tenant_id, "tenant_name": None, "bbk_id": None},
            )
            skill_info = user_skill_map.get(tenant_id)

            if skill_info:
                source = skill_info.get("source", "")
                current_version = skill_info.get("version_text", "")

                # 判断状态
                if source.startswith("marketplace:"):
                    # 已分发技能，可覆盖更新
                    status = "update"
                elif source == "customized":
                    # 自建技能，冲突
                    status = "conflict"
                else:
                    # 其他来源，视为首次
                    status = "first_time"

                users_status.append({
                    "tenant_id": tenant_id,
                    "tenant_name": user_info.get("tenant_name"),
                    "bbk_id": user_info.get("bbk_id"),
                    "status": status,
                    "current_version": current_version if status == "update" else None,
                })
            else:
                # 用户未持有该技能
                users_status.append({
                    "tenant_id": tenant_id,
                    "tenant_name": user_info.get("tenant_name"),
                    "bbk_id": user_info.get("bbk_id"),
                    "status": "first_time",
                    "current_version": None,
                })
    else:
        # 数据库未连接或无目标用户，返回基本信息
        for tenant_id in target_tenant_ids:
            users_status.append({
                "tenant_id": tenant_id,
                "tenant_name": None,
                "bbk_id": None,
                "status": "first_time",
                "current_version": None,
            })

    return {
        "skill_version": skill_version,
        "users": users_status,
        "distributed_user_ids": distributed_user_ids,
    }
```

- [ ] **Step 3: 导入 normalize_skill_name**

在文件顶部导入区域（约 line 27-45）确认已导入：

```python
from .fs import (
    ...
    normalize_skill_name,
    ...
)
```

- [ ] **Step 4: 验证方法定义**

运行导入检查：

```bash
cd market && python -c "from src.market.marketplace.service import MarketplaceService; print('OK')"
```

Expected: 输出 `OK`

---

## Task 3: 后端预览 API 端点

**Files:**
- Modify: `market/src/market/app/routers/skills_market.py`

- [ ] **Step 1: 导入预览响应模型**

在文件顶部导入区域（约 line 30-36）添加导入：

```python
from ...marketplace.schemas import (
    ...
    DistributionPreviewResponse,
    UserSkillStatus,
)
```

- [ ] **Step 2: 添加预览 API 端点**

在文件末尾（约 line 2034）添加新的路由：

```python
@router.get(
    "/market/skills/{item_id}/distribution-preview",
    response_model=DistributionPreviewResponse,
)
async def get_distribution_preview(
    item_id: str,
    request: Request,
    source_id: str = Query(..., description="来源 ID"),
    tenant_ids: str = Query(default="", description="目标用户 ID，逗号分隔"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
):
    """获取技能分发预览（管理员）.

    返回每个用户的技能持有状态：
    - first_time: 首次分发
    - update: 覆盖更新（显示当前版本）
    - conflict: 自建冲突（不可覆盖）
    """
    _require_manager(x_manager)
    svc = request.app.state.marketplace

    # 解析 tenant_ids
    target_tenant_ids = []
    if tenant_ids.strip():
        target_tenant_ids = [t.strip() for t in tenant_ids.split(",") if t.strip()]

    if not target_tenant_ids:
        # 无目标用户时返回空预览
        items = load_index(svc.marketplace_root, source_id)
        item = next(
            (
                i
                for i in items
                if i.item_id == item_id and i.item_type == "skill"
            ),
            None,
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Skill not found")
        return DistributionPreviewResponse(
            skill_version=item.version,
            users=[],
            distributed_user_ids=[],
        )

    try:
        result = await svc.get_distribution_preview(
            source_id,
            item_id,
            target_tenant_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return DistributionPreviewResponse(
        skill_version=result["skill_version"],
        users=[UserSkillStatus(**u) for u in result["users"]],
        distributed_user_ids=result["distributed_user_ids"],
    )
```

- [ ] **Step 3: 验证 API 定义**

运行导入检查：

```bash
cd market && python -c "from src.market.app.routers.skills_market import router; print('OK')"
```

Expected: 输出 `OK`

---

## Task 4: 前端预览 API 调用

**Files:**
- Modify: `console/src/api/modules/market.ts`

- [ ] **Step 1: 添加类型定义**

在文件顶部类型定义区域（约 line 30-85）添加：

```typescript
// 用户技能状态
export interface UserSkillStatus {
  tenant_id: string;
  tenant_name: string | null;
  bbk_id: string | null;
  status: 'first_time' | 'update' | 'conflict';
  current_version?: string;
}

// 分发预览响应
export interface DistributionPreviewResponse {
  skill_version: string;
  users: UserSkillStatus[];
  distributed_user_ids: string[];
}
```

- [ ] **Step 2: 添加 API 调用方法**

在 `marketApi` 对象末尾（约 line 503）添加：

```typescript
  // 获取分发预览
  getDistributionPreview: async (
    sourceId: string,
    itemId: string,
    tenantIds: string[]
  ): Promise<DistributionPreviewResponse> => {
    const tenantIdsParam = tenantIds.join(",");
    const opts = mergeHeaders({
      "X-Source-Id": sourceId,
      "X-Manager": "true",
    });
    return request<DistributionPreviewResponse>(
      `/market/skills/${itemId}/distribution-preview?source_id=${sourceId}&tenant_ids=${tenantIdsParam}`,
      opts
    );
  },
```

- [ ] **Step 3: 验证 TypeScript 类型检查**

运行前端类型检查：

```bash
cd console && npm run type-check 2>&1 | grep -E "error|warning" || echo "OK"
```

Expected: 无错误输出

---

## Task 5: 前端概览卡片组件

**Files:**
- Create: `console/src/components/DistributionPreview/index.tsx`
- Create: `console/src/components/DistributionPreview/index.module.less`

- [ ] **Step 1: 创建组件文件**

创建 `console/src/components/DistributionPreview/index.tsx`：

```typescript
/**
 * 分发预览概览卡片组件
 *
 * 展示分发统计：首次分发、覆盖更新、跳过（冲突）
 */
import { useMemo } from "react";
import { Checkbox, Spin } from "antd";
import { useTranslation } from "react-i18next";
import type { UserSkillStatus } from "@/api/modules/market";
import styles from "./index.module.less";

interface DistributionPreviewProps {
  skillVersion: string;
  users: UserSkillStatus[];
  distributedUserIds: string[];
  selectedTenantIds: string[];
  loading?: boolean;
  onSelectDistributed: (distributedIds: string[]) => void;
}

export function DistributionPreview({
  skillVersion,
  users,
  distributedUserIds,
  selectedTenantIds,
  loading,
  onSelectDistributed,
}: DistributionPreviewProps) {
  const { t } = useTranslation();

  // 计算当前选中用户的分发统计
  const stats = useMemo(() => {
    const selectedUsers = users.filter(
      (u) => selectedTenantIds.includes(u.tenant_id)
    );
    const firstTime = selectedUsers.filter(
      (u) => u.status === "first_time"
    ).length;
    const update = selectedUsers.filter(
      (u) => u.status === "update"
    ).length;
    const conflict = selectedUsers.filter(
      (u) => u.status === "conflict"
    ).length;
    return { firstTime, update, conflict };
  }, [users, selectedTenantIds]);

  // 是否勾选了"默认选中已分发用户"
  const isSelectDistributedChecked = useMemo(() => {
    if (distributedUserIds.length === 0) return false;
    // 所有已分发用户都在选中列表中
    return distributedUserIds.every((id) =>
      selectedTenantIds.includes(id)
    );
  }, [distributedUserIds, selectedTenantIds]);

  // 勾选/取消勾选"默认选中已分发用户"
  const handleSelectDistributedChange = (checked: boolean) => {
    if (checked) {
      onSelectDistributed(distributedUserIds);
    } else {
      // 取消勾选时，清空选择（由父组件处理）
      onSelectDistributed([]);
    }
  };

  return (
    <div className={styles.previewCard}>
      <div className={styles.previewHeader}>
        <span className={styles.previewTitle}>
          {t("distributionPreview.title", "分发预览")}
        </span>
        {distributedUserIds.length > 0 && (
          <Checkbox
            checked={isSelectDistributedChecked}
            onChange={(e) => handleSelectDistributedChange(e.target.checked)}
          >
            {t(
              "distributionPreview.selectDistributed",
              "默认选中已分发用户"
            )}
          </Checkbox>
        )}
      </div>

      {loading ? (
        <Spin size="small" className={styles.previewSpin} />
      ) : (
        <>
          <div className={styles.statsRow}>
            <div className={styles.statItem}>
              <div className={styles.statNumber} style={{ color: "#52c41a" }}>
                {stats.firstTime}
              </div>
              <div className={styles.statLabel} style={{ color: "#52c41a" }}>
                {t("distributionPreview.firstTime", "首次分发")}
              </div>
            </div>
            <div className={styles.statItem}>
              <div className={styles.statNumber} style={{ color: "#1890ff" }}>
                {stats.update}
              </div>
              <div className={styles.statLabel} style={{ color: "#1890ff" }}>
                {t("distributionPreview.update", "覆盖更新")}
              </div>
            </div>
            <div className={styles.statItem}>
              <div className={styles.statNumber} style={{ color: "#faad14" }}>
                {stats.conflict}
              </div>
              <div className={styles.statLabel} style={{ color: "#faad14" }}>
                {t("distributionPreview.conflict", "跳过(冲突)")}
              </div>
            </div>
          </div>

          <div className={styles.previewInfo}>
            {t("distributionPreview.currentVersion", "当前技能版本")}:{" "}
            {skillVersion} | {t("distributionPreview.distributedCount", "已分发用户数")}:{" "}
            {distributedUserIds.length}
          </div>
        </>
      )}
    </div>
  );
}

export default DistributionPreview;
```

- [ ] **Step 2: 创建样式文件**

创建 `console/src/components/DistributionPreview/index.module.less`：

```less
.previewCard {
  background: #f0f5ff;
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 12px;
}

.previewHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.previewTitle {
  font-weight: 600;
  font-size: 14px;
}

.previewSpin {
  margin-top: 12px;
}

.statsRow {
  display: flex;
  gap: 24px;
  margin-top: 12px;
}

.statItem {
  text-align: center;
}

.statNumber {
  font-size: 24px;
  font-weight: bold;
}

.statLabel {
  font-size: 12px;
}

.previewInfo {
  margin-top: 8px;
  color: #666;
  font-size: 12px;
}
```

- [ ] **Step 3: 验证组件导入**

运行前端类型检查：

```bash
cd console && npm run type-check 2>&1 | grep -E "error|warning" || echo "OK"
```

Expected: 无错误输出

---

## Task 6: TenantSelector 用户状态标记

**Files:**
- Modify: `console/src/components/TenantSelector/index.tsx`
- Modify: `console/src/components/TenantSelector/index.module.less`

- [ ] **Step 1: 添加 props 类型定义**

在 `TenantSelector/index.tsx` 顶部类型定义区域（约 line 13）添加导入：

```typescript
import type { UserSkillStatus } from "@/api/modules/market";
```

在 `types.ts` 文件（或 `index.tsx` 内部定义 props 类型处）添加：

```typescript
interface TenantSelectorProps {
  // ...existing props...
  userSkillStatusMap?: Map<string, UserSkillStatus>; // 新增：用户技能状态映射
}
```

- [ ] **Step 2: 添加状态标记渲染逻辑**

在用户卡片渲染区域（约 line 500-520）修改渲染逻辑：

```typescript
// 在 userGrid 渲染区域内，修改用户卡片渲染
{displayedTenantIds.map((tenantId) => {
  const selected = effectiveInListTenantIds.includes(tenantId);
  const status = userSkillStatusMap?.get(tenantId);
  return (
    <button
      key={tenantId}
      type="button"
      onClick={() => handleUserCardClick(tenantId, selected)}
      className={`${styles.userCard} ${
        selected ? styles.userCardSelected : ""
      } ${
        status?.status === "update" ? styles.userCardUpdate : ""
      } ${
        status?.status === "conflict" ? styles.userCardConflict : ""
      }`}
    >
      {selected ? (
        <span className={styles.checkIcon}>
          <CheckOutlined />
        </span>
      ) : status?.status === "conflict" ? (
        <span className={styles.warnIcon}>⚠</span>
      ) : (
        <span className={styles.emptyIcon}>○</span>
      )}
      <span className={styles.userName}>{renderTenantName(tenantId)}</span>
      {status && (
        <span className={styles.userStatus}>
          {status.status === "update" && status.current_version && (
            <span className={styles.versionChange}>
              {status.current_version}→{skillVersion}
            </span>
          )}
          {status.status === "first_time" && (
            <span className={styles.firstTimeLabel}>首次</span>
          )}
          {status.status === "conflict" && (
            <span className={styles.conflictLabel}>自建冲突</span>
          )}
        </span>
      )}
    </button>
  );
})}
```

- [ ] **Step 3: 添加按机构模式的用户状态显示**

在 Collapse 展开的机构用户列表（约 line 409-420）添加状态显示：

```typescript
{groupedTenants.map((group) => ({
  key: group.bbkId,
  label: (
    <span className={styles.collapseLabel}>
      <UserOutlined className={styles.collapseIcon} />
      {group.bbkName}
      <span className={styles.collapseCount}>
        {t("tenantSelector.userCount", { count: group.users.length })}
      </span>
      {/* 新增：机构统计 */}
      <span className={styles.collapseStats}>
        {t("tenantSelector.orgStats", {
          update: group.users.filter(u => userSkillStatusMap?.get(u.tenant_id)?.status === "update").length,
          firstTime: group.users.filter(u => userSkillStatusMap?.get(u.tenant_id)?.status === "first_time").length,
        })}
      </span>
    </span>
  ),
  children: (
    <div className={styles.userDetailGrid}>
      {group.users.map((user) => {
        const status = userSkillStatusMap?.get(user.tenant_id);
        return (
          <div
            key={user.tenant_id}
            className={`${styles.userDetailItem} ${
              status?.status === "update" ? styles.userDetailUpdate : ""
            } ${
              status?.status === "conflict" ? styles.userDetailConflict : ""
            }`}
            title={renderTenantName(user.tenant_id)}
          >
            <div className={styles.userDetailName}>
              {renderTenantName(user.tenant_id)}
            </div>
            {status && (
              <div className={styles.userDetailStatus}>
                {status.status === "update" && status.current_version && (
                  <span>{status.current_version}→v新</span>
                )}
                {status.status === "first_time" && (
                  <span style={{ color: "#52c41a" }}>首次</span>
                )}
                {status.status === "conflict" && (
                  <span style={{ color: "#f5222d" }}>自建冲突</span>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  ),
}))}
```

- [ ] **Step 4: 添加样式定义**

在 `index.module.less` 文件末尾添加：

```less
// 用户状态标记样式
.userCardUpdate {
  border: 2px solid #1890ff;
  background: #e6f7ff;
}

.userCardConflict {
  border: 1px solid #faad14;
  background: #fffbe6;
}

.warnIcon {
  color: #faad14;
  margin-right: 4px;
}

.emptyIcon {
  color: #999;
  margin-right: 4px;
}

.userName {
  color: #333;
}

.userStatus {
  display: block;
  font-size: 11px;
  margin-top: 4px;
}

.versionChange {
  color: #1890ff;
}

.firstTimeLabel {
  color: #52c41a;
}

.conflictLabel {
  color: #f5222d;
}

// 按机构模式用户详情状态
.userDetailUpdate {
  background: #e6f7ff;
  border: 1px solid #1890ff;
}

.userDetailConflict {
  background: #fffbe6;
  border: 1px solid #faad14;
}

.userDetailName {
  color: #333;
  font-size: 12px;
}

.userDetailStatus {
  color: inherit;
  font-size: 10px;
  margin-top: 2px;
}

.collapseStats {
  color: #1890ff;
  font-size: 12px;
  margin-left: 8px;
}
```

- [ ] **Step 5: 添加 props 接收**

在 TenantSelector 函数组件的 props 解构中添加：

```typescript
export function TenantSelector({
  selectedTenantIds,
  onChange,
  onSelectionInfoChange,
  hint,
  excludeTenantId,
  onLoadError,
  userSkillStatusMap, // 新增
}: TenantSelectorProps) {
```

- [ ] **Step 6: 验证 TypeScript 类型检查**

运行前端类型检查：

```bash
cd console && npm run type-check 2>&1 | grep -E "error|warning" || echo "OK"
```

Expected: 无错误输出

---

## Task 7: DistributeTargetModal 集成预览

**Files:**
- Modify: `console/src/pages/Market/DistributeTargetModal.tsx`

- [ ] **Step 1: 添加导入**

在文件顶部添加导入：

```typescript
import { DistributionPreview } from "../../components/DistributionPreview";
import type { UserSkillStatus, DistributionPreviewResponse } from "../../api/modules/market";
```

- [ ] **Step 2: 添加预览状态**

在 DistributeTargetModal 函数组件内添加状态：

```typescript
// 预览状态
const [previewLoading, setPreviewLoading] = useState(false);
const [previewData, setPreviewData] = useState<DistributionPreviewResponse | null>(null);

// 用户技能状态映射
const userSkillStatusMap = useMemo(() => {
  if (!previewData) return new Map<string, UserSkillStatus>();
  return new Map(previewData.users.map((u) => [u.tenant_id, u]));
}, [previewData]);
```

- [ ] **Step 3: 添加预览获取逻辑**

添加 useEffect 获取预览数据：

```typescript
// 打开时清空选择并获取预览
useEffect(() => {
  if (!open) return;
  setSelectedTenantIds([]);
  setPreviewData(null);

  // 获取所有用户 ID 用于预览
  const fetchPreview = async () => {
    if (!item) return;
    setPreviewLoading(true);
    try {
      // 先获取租户列表
      const tenants = await fetchTenantsBySource(sourceId);
      const tenantIds = tenants.map((t) => t.tenant_id);

      // 获取预览数据
      const preview = await marketApi.getDistributionPreview(
        sourceId,
        (item as MarketSkill).item_id,
        tenantIds
      );
      setPreviewData(preview);
    } catch (error) {
      console.error("获取预览失败:", error);
    } finally {
      setPreviewLoading(false);
    }
  };

  fetchPreview();
}, [open, item, sourceId]);
```

- [ ] **Step 4: 添加"默认选中已分发用户"回调**

添加回调函数：

```typescript
// 处理"默认选中已分发用户"
const handleSelectDistributed = (distributedIds: string[]) => {
  if (distributedIds.length > 0) {
    setSelectedTenantIds(distributedIds);
  } else {
    setSelectedTenantIds([]);
  }
};
```

- [ ] **Step 5: 渲染预览卡片**

在 Modal 内容区域顶部添加预览卡片（约 line 169）：

```typescript
return (
  <Modal
    open={open}
    title={`分发「${item?.name || ""}」`}
    onCancel={submitting ? undefined : onClose}
    onOk={handleSubmit}
    okText="分发"
    cancelText="取消"
    okButtonProps={{
      disabled: selectedTenantIds.length === 0,
      loading: submitting,
    }}
    width={600}
  >
    <div style={{ display: "grid", gap: 12 }}>
      {/* 新增：分发预览卡片 */}
      {type === "skill" && previewData && (
        <DistributionPreview
          skillVersion={previewData.skill_version}
          users={previewData.users}
          distributedUserIds={previewData.distributed_user_ids}
          selectedTenantIds={selectedTenantIds}
          loading={previewLoading}
          onSelectDistributed={handleSelectDistributed}
        />
      )}

      <div style={{ color: "#666", fontSize: 12 }}>{hintText}</div>
      <div style={{ fontWeight: 500 }}>
        当前条目：{item?.name || "-"}（共选择 {selectedTenantIds.length} 个用户）
      </div>
      <TenantSelector
        selectedTenantIds={selectedTenantIds}
        onChange={setSelectedTenantIds}
        userSkillStatusMap={userSkillStatusMap}
      />
    </div>
  </Modal>
);
```

- [ ] **Step 6: 添加 fetchTenantsBySource 导入**

在文件顶部添加导入：

```typescript
import { fetchTenantsBySource } from "../../api/modules/userInfo";
```

- [ ] **Step 7: 验证 TypeScript 类型检查**

运行前端类型检查：

```bash
cd console && npm run type-check 2>&1 | grep -E "error|warning" || echo "OK"
```

Expected: 无错误输出

---

## Task 8: 前端国际化支持

**Files:**
- Modify: `console/src/locales/zh-CN/translation.json`
- Modify: `console/src/locales/en-US/translation.json`（如有）

- [ ] **Step 1: 添加中文翻译**

在 `zh-CN/translation.json` 中添加：

```json
{
  "distributionPreview": {
    "title": "分发预览",
    "selectDistributed": "默认选中已分发用户",
    "firstTime": "首次分发",
    "update": "覆盖更新",
    "conflict": "跳过(冲突)",
    "currentVersion": "当前技能版本",
    "distributedCount": "已分发用户数"
  },
  "tenantSelector": {
    "orgStats": "覆盖: {{update}} | 首次: {{firstTime}}"
  }
}
```

- [ ] **Step 2: 验证前端构建**

运行前端构建：

```bash
cd console && npm run build 2>&1 | tail -20
```

Expected: 构建成功，无错误

---

## Task 9: 集成测试验证

- [ ] **Step 1: 启动后端服务**

```bash
cd market && python -m src.market.app
```

Expected: 服务启动成功

- [ ] **Step 2: 启动前端开发服务器**

```bash
cd console && npm run dev
```

Expected: 前端启动成功

- [ ] **Step 3: 手动测试预览功能**

1. 打开技能市场页面
2. 点击某个技能的"分发"按钮
3. 验证预览卡片显示
4. 勾选"默认选中已分发用户"验证自动选中
5. 切换"按机构"模式验证机构内用户状态显示
6. 选择不同用户验证统计数字实时更新

- [ ] **Step 4: 验证两种模式一致性**

1. 切换"按用户"模式，选择若干用户
2. 验证预览卡片统计准确
3. 切换"按机构"模式，选择相同机构
4. 验证用户状态标记与"按用户"模式一致

---

## Task 10: 代码检查与验证总结

- [ ] **Step 1: 检查所有变更文件**

```bash
git status
git diff --stat
```

Expected: 显示所有修改和新增的文件

- [ ] **Step 2: 运行前端类型检查和构建**

```bash
cd console && npm run type-check && npm run build
```

Expected: 无错误，构建成功

- [ ] **Step 3: 验证功能完整性**

手动测试清单：
- [ ] 预览卡片正确显示（首次/覆盖/冲突统计）
- [ ] "默认选中已分发用户"选项可用
- [ ] 按用户模式：用户状态标记显示正确
- [ ] 按机构模式：机构内用户状态显示正确
- [ ] 统计数字随选择实时更新

- [ ] **Step 4: 用户确认后手动提交**

完成验证后，请用户确认是否提交代码。

---

**注意：代码提交需用户验证确认后执行。**

---

## Self-Review Checklist

**Spec Coverage:**
- [x] Task 1-3: 后端预览 API 实现
- [x] Task 4: 前端 API 调用
- [x] Task 5: 概览卡片组件
- [x] Task 6: TenantSelector 用户状态标记
- [x] Task 7: DistributeTargetModal 集成
- [x] Task 8: 国际化支持
- [x] Task 9-10: 测试验证与用户确认提交

**Placeholder Scan:**
- 无 TBD、TODO、implement later
- 所有步骤包含完整代码
- 无"类似 Task N"引用

**Type Consistency:**
- UserSkillStatus: 前后端类型一致（tenant_id, tenant_name, bbk_id, status, current_version）
- DistributionPreviewResponse: 前后端类型一致（skill_version, users, distributed_user_ids）
- API 方法名一致：getDistributionPreview

**提交策略:**
- 需用户验证确认后手动提交，不自动提交代码