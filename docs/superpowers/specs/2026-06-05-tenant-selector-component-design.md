# TenantSelector 组件提取重构

## Context

Console 前端中存在多处租户选择功能的重复实现，分布在多个页面组件中：

- `DistributeTargetModal.tsx` - 技能/MCP 分发
- `DistributeModal.tsx` - Agent 配置分发
- `Workspace/index.tsx` - 文件广播
- `ChannelDrawer.tsx` - 通道配置分发
- `CronJobs/index.tsx` - 定时任务广播
- `ModelsSection.tsx` - 模型配置分发
- `Models/index.tsx` - 供应商全量分发

这些组件各自维护租户列表加载、机构筛选、用户选择等状态逻辑，导致：

1. **代码重复**：租户选择 UI 和逻辑在多处重复实现
2. **维护成本高**：修改租户选择功能需要同步修改多个文件
3. **行为不一致风险**：各页面可能逐步产生细微差异

此前已有 `TenantTargetPicker` 组件，但设计上需要外部传入 `tenantIds` 列表，仍需各页面自行加载租户数据。

## Goal

提取统一的 `TenantSelector` 组件：

1. **自动数据加载**：组件内部通过 `useIframeStore` 获取 `sourceId`，自动调用 `fetchTenantsBySource` 加载租户信息
2. **统一交互模式**：支持「按机构」和「按用户」双模式切换，交互体验一致
3. **简化调用方式**：父组件只需提供 `selectedTenantIds` 和 `onChange`，无需关心数据加载逻辑
4. **支持过滤当前租户**：通过 `excludeTenantId` prop 过滤自身

## Non-Goals

- 不改变租户选择的核心交互逻辑（机构/用户模式切换、手动输入等）
- 不修改 `TenantTargetPicker` 组件的定义和实现（保留给特定场景使用）
- 不迁移 `Agent/MCP/index.tsx` 和 `SkillPool/components/BroadcastModal.tsx`（这两个页面保持使用 `TenantTargetPicker`）
- 不修改后端 API

## Options Considered

### Option 1: 提取 `TenantSelector` 组件（自动加载模式）

推荐方案。

组件内部自动完成数据加载，父组件调用最简化：

```tsx
<TenantSelector
  selectedTenantIds={selectedTenantIds}
  onChange={setSelectedTenantIds}
  excludeTenantId={currentTenantId}
/>
```

优点：

- 父组件代码大幅简化，移除 `loading`、`tenantIds` 等状态
- 租户数据加载逻辑统一，易于维护
- 符合「容器组件」模式，组件自管理数据

缺点：

- 组件内部依赖 `useIframeStore`，耦合 store
- 不适用于需要自定义数据源的页面

### Option 2: 扩展 `TenantTargetPicker` 支持 `sourceId`

在现有组件上增加 `sourceId` prop，组件内部按需加载。

优点：

- 复用现有组件，改动较小

缺点：

- 混合两种模式（传入 `tenantIds` 或 `sourceId`），接口语义不清晰
- 影响现有使用 `TenantTargetPicker` 的页面

### Option 3: 保留现状，仅文档化

不做代码修改，仅记录现有各页面的实现差异。

优点：

- 零风险

缺点：

- 重复代码持续存在
- 后续维护成本高

## Design

### 组件接口设计

```ts
interface TenantSelectorProps {
  /** 已选中的租户 ID 列表 */
  selectedTenantIds: string[];
  /** 选择变更回调 */
  onChange: (tenantIds: string[]) => void;
  /** 提示文本 */
  hint?: ReactNode;
  /** 当前租户 ID（用于过滤自身） */
  excludeTenantId?: string;
}
```

### 组件内部状态

```tsx
// 加载状态
const [loading, setLoading] = useState(false);

// 租户选项数据
const [tenantOptions, setTenantOptions] = useState<TenantSourceInfo[]>([]);

// 分发模式：按机构 / 按用户
const [targetMode, setTargetMode] = useState<"bbk_id" | "user_id">("bbk_id");

// 机构选择
const [selectedBbkIds, setSelectedBbkIds] = useState<string[]>([]);

// 用户选择（按用户模式）
const [selectedDiscoveredTenantIds, setSelectedDiscoveredTenantIds] =
  useState<string[]>([]);

// 手动输入
const [manualTenantIdsText, setManualTenantIdsText] = useState("");
```

### 数据加载时机

组件在 `sourceId` 可用时自动加载租户信息：

```tsx
useEffect(() => {
  if (!sourceId) return;
  setLoading(true);
  fetchTenantsBySource(sourceId)
    .then((items) => {
      const filtered = excludeTenantId
        ? items.filter((item) => item.tenant_id !== excludeTenantId)
        : items;
      setTenantOptions(filtered);
    })
    .catch(console.error)
    .finally(() => setLoading(false));
}, [sourceId, excludeTenantId]);
```

### 状态同步机制

组件通过双向同步保持内外状态一致：

1. **外部 → 内部**：当外部 `selectedTenantIds` 变化时，拆分为「已发现用户」和「手动输入用户」
2. **内部 → 外部**：当内部合并结果变化时，调用 `onChange` 通知外部

使用 `haveSameTenantIds` 比较函数避免循环更新：

```tsx
// 内部状态变更通知外部
useEffect(() => {
  if (haveSameTenantIds(selectedTenantIds, mergedTenantIds)) {
    return;
  }
  onChange(mergedTenantIds);
}, [mergedTenantIds, onChange, selectedTenantIds]);
```

### 迁移范围

| 页面 | 原组件 | 新组件 | 状态变更 |
|------|--------|--------|----------|
| `DistributeTargetModal.tsx` | 内置实现 | `TenantSelector` | 移除 `loading`、`tenantOptions` 等 |
| `DistributeModal.tsx` | `TenantTargetPicker` | `TenantSelector` | 移除 `tenantIds`、加载逻辑 |
| `Workspace/index.tsx` | `TenantTargetPicker` | `TenantSelector` | 移除加载逻辑 |
| `ChannelDrawer.tsx` | `TenantTargetPicker` | `TenantSelector` | 移除加载逻辑 |
| `CronJobs/index.tsx` | `TenantTargetPicker` | `TenantSelector` | 移除 `sourceId` prop |
| `ModelsSection.tsx` | `TenantTargetPicker` | `TenantSelector` | 移除加载逻辑 |
| `Models/index.tsx` | `TenantTargetPicker` | `TenantSelector` | 移除加载逻辑 |

### 保留 `TenantTargetPicker` 的场景

以下两个页面继续使用 `TenantTargetPicker`：

- `Agent/MCP/index.tsx`
- `SkillPool/components/BroadcastModal.tsx`

原因：这两个页面有特定的使用场景，可能需要外部控制数据源或保持现有交互模式。

### 文件结构

```
console/src/components/TenantSelector/
├── index.tsx         # 主组件实现
├── index.module.less # 样式文件（预留）
├── types.ts          # Props 类型定义
```

## Implementation Notes

1. `Spin` 组件需从 `antd` 导入，而非 `@agentscope-ai/design`
2. 组件使用 `useTranslation` 支持国际化
3. 机构数据使用本地常量 `BBK_ID_MAP` 和 `BBK_ID_TO_NAME_MAP`
4. 手动输入解析支持空格和逗号分隔，自动去重

## Testing

迁移后需验证：

1. 各页面的租户选择功能正常工作
2. 「按机构」和「按用户」模式切换正确
3. 手动输入租户 ID 功能正常
4. `excludeTenantId` 过滤生效
5. 状态同步无循环更新问题