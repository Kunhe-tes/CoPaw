# 菜单结构重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构前端菜单结构，按照新的业务模块重新组织一级和二级菜单。

**Architecture:** 修改 Sidebar.tsx 的 menuItems 配置，更新 constants.ts 的 DEFAULT_OPEN_KEYS，新增 locales 国际化文本。

**Tech Stack:** React, TypeScript, Ant Design Menu, i18next

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `console/src/layouts/Sidebar.tsx` | 菜单配置和渲染 |
| `console/src/layouts/constants.ts` | DEFAULT_OPEN_KEYS 配置 |
| `console/src/locales/zh.json` | 中文国际化文本 |
| `console/src/locales/en.json` | 英文国际化文本 |

---

## Task 1: 更新国际化文本

**Files:**
- Modify: `console/src/locales/zh.json`
- Modify: `console/src/locales/en.json`

- [ ] **Step 1: 更新 zh.json 的 nav 部分**

找到 `console/src/locales/zh.json` 中 `nav` 部分，新增以下文本：

```json
"nav": {
  "chat": "聊天",
  "creationCenter": "创作中心",
  "runCenter": "运行中心",
  "insightCenter": "洞察中心",
  "qualityEngineering": "质量工程",
  "systemSettings": "系统设置",
  "market": "应用市场",
  // ... 其他已有字段保持不变
}
```

需要新增的字段：
- `"creationCenter": "创作中心"`
- `"runCenter": "运行中心"`
- `"insightCenter": "洞察中心"`
- `"qualityEngineering": "质量工程"`
- `"systemSettings": "系统设置"`

- [ ] **Step 2: 更新 en.json 的 nav 部分**

找到 `console/src/locales/en.json` 中 `nav` 部分，新增以下文本：

```json
"nav": {
  "chat": "Chat",
  "creationCenter": "Creation Center",
  "runCenter": "Run Center",
  "insightCenter": "Insight Center",
  "qualityEngineering": "Quality Engineering",
  "systemSettings": "System Settings",
  "market": "Market",
  // ... 其他已有字段保持不变
}
```

- [ ] **Step 3: 提交国际化修改**

```bash
git add console/src/locales/zh.json console/src/locales/en.json
git commit -m "feat(nav): add new menu group i18n texts

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: 更新 constants.ts 的 DEFAULT_OPEN_KEYS

**Files:**
- Modify: `console/src/layouts/constants.ts`

- [ ] **Step 1: 更新 DEFAULT_OPEN_KEYS**

找到 `console/src/layouts/constants.ts` 第 27-36 行的 `DEFAULT_OPEN_KEYS`，替换为：

```typescript
export const DEFAULT_OPEN_KEYS = [
  "creation-center",
  "run-center",
  "system-settings",
  "insight-center",
  "quality-engineering",
];
```

- [ ] **Step 2: 提交修改**

```bash
git add console/src/layouts/constants.ts
git commit -m "refactor(nav): update DEFAULT_OPEN_KEYS for new menu structure

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: 重构 Sidebar.tsx 的 menuItems（聊天和创作中心）

**Files:**
- Modify: `console/src/layouts/Sidebar.tsx`

- [ ] **Step 1: 修改 menuItems 开头部分（聊天和创作中心）**

找到 `console/src/layouts/Sidebar.tsx` 第 358-443 行的 `menuItems` 数组，替换开头部分：

```typescript
const menuItems: MenuProps["items"] = [
  {
    key: "chat",
    label: collapsed ? null : t("nav.chat"),
    icon: <SparkChatTabFill size={16} />,
  },
  {
    key: "creation-center",
    label: collapsed ? null : t("nav.creationCenter"),
    children: [
      {
        key: "workspace",
        label: collapsed ? null : t("nav.workspace"),
        icon: <SparkLocalFileLine size={16} />,
      },
      {
        key: "my-skills",
        label: collapsed ? null : t("nav.mySkills"),
        icon: <Wrench size={16} />,
      },
      {
        key: "tools",
        label: collapsed ? null : t("nav.tools"),
        icon: <SparkToolLine size={16} />,
      },
      {
        key: "my-mcp",
        label: collapsed ? null : t("nav.myMcp"),
        icon: <Puzzle size={16} />,
      },
    ],
  },
```

---

## Task 4: 重构 Sidebar.tsx 的 menuItems（运行中心和系统设置）

**Files:**
- Modify: `console/src/layouts/Sidebar.tsx`

- [ ] **Step 1: 添加运行中心菜单组**

在创作中心后面添加：

```typescript
  {
    key: "run-center",
    label: collapsed ? null : t("nav.runCenter"),
    children: [
      {
        key: "cron-jobs",
        label: collapsed ? null : t("nav.cronJobs"),
        icon: <SparkDateLine size={16} />,
      },
      {
        key: "channels",
        label: collapsed ? null : t("nav.channels"),
        icon: <SparkWifiLine size={16} />,
      },
      {
        key: "agent-config",
        label: collapsed ? null : t("nav.agentConfig"),
        icon: <SparkModifyLine size={16} />,
      },
      {
        key: "heartbeat",
        label: collapsed ? null : t("nav.heartbeat"),
        icon: <SparkVoiceChat01Line size={16} />,
      },
    ],
  },
```

- [ ] **Step 2: 添加系统设置菜单组**

```typescript
  {
    key: "system-settings",
    label: collapsed ? null : t("nav.systemSettings"),
    children: [
      {
        key: "models",
        label: collapsed ? null : t("nav.models"),
        icon: <SparkModePlazaLine size={16} />,
      },
      {
        key: "featured-cases-management",
        label: collapsed ? null : t("nav.featuredCasesManagement", "精选案例管理"),
        icon: <SparkFileTxtLine size={16} />,
      },
      {
        key: "environments",
        label: collapsed ? null : t("nav.environments"),
        icon: <SparkInternetLine size={16} />,
      },
      {
        key: "security",
        label: collapsed ? null : t("nav.security"),
        icon: <SparkBrowseLine size={16} />,
      },
      ...(canManageCurrentSourceConfig
        ? [
            {
              key: "system-config-page",
              label: collapsed
                ? null
                : t("nav.currentSourceConfig", {
                    defaultValue: "系统特性配置",
                  }),
              icon: <SparkModifyLine size={16} />,
            },
          ]
        : []),
    ],
  },
```

---

## Task 5: 重构 Sidebar.tsx 的 menuItems（洞察中心和质量工程）

**Files:**
- Modify: `console/src/layouts/Sidebar.tsx`

- [ ] **Step 1: 添加洞察中心菜单组**

```typescript
  {
    key: "insight-center",
    label: collapsed ? null : t("nav.insightCenter"),
    children: [
      {
        key: "analytics-business-overview",
        label: collapsed
          ? null
          : t("nav.analyticsBusinessOverview", "运营看板"),
        icon: <SparkBarChartLine size={16} />,
      },
      {
        key: "analytics-messages",
        label: collapsed ? null : t("nav.analyticsMessages", "Messages"),
        icon: <SparkSearchLine size={16} />,
      },
      {
        key: "analytics-users",
        label: collapsed ? null : t("nav.analyticsUsers", "Users"),
        icon: <SparkUserGroupLine size={16} />,
      },
      {
        key: "analytics-sessions",
        label: collapsed ? null : t("nav.analyticsSessions", "Sessions"),
        icon: <SparkMessageLine size={16} />,
      },
      {
        key: "analytics-traces",
        label: collapsed ? null : t("nav.analyticsTraces", "Traces"),
        icon: <SparkFileTxtLine size={16} />,
      },
    ],
  },
```

- [ ] **Step 2: 添加质量工程菜单组**

```typescript
  {
    key: "quality-engineering",
    label: collapsed ? null : t("nav.qualityEngineering"),
    children: [
      {
        key: "continuous-iteration",
        label: collapsed ? null : t("nav.continuousIteration", "持续治理"),
        icon: <SparkRefreshLine size={16} />,
      },
    ],
  },
```

---

## Task 6: 重构 Sidebar.tsx 的 menuItems（应用市场）

**Files:**
- Modify: `console/src/layouts/Sidebar.tsx`

- [ ] **Step 1: 添加应用市场为单独一级菜单**

在质量工程后面添加：

```typescript
  {
    key: "market",
    label: collapsed ? null : t("nav.market"),
    icon: <Store size={16} />,
  },
```

---

## Task 7: 提交 Sidebar.tsx 修改

**Files:**
- Modify: `console/src/layouts/Sidebar.tsx`

- [ ] **Step 1: 确认完整修改后的 menuItems 结构**

确保 `menuItems` 数组顺序正确：
1. 聊天
2. 创作中心
3. 运行中心
4. 系统设置
5. 洞察中心
6. 质量工程
7. 应用市场

- [ ] **Step 2: 提交完整修改**

```bash
git add console/src/layouts/Sidebar.tsx
git commit -m "refactor(nav): restructure menu items per new business modules

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: 更新 collapsedNavItems

**Files:**
- Modify: `console/src/layouts/Sidebar.tsx`

- [ ] **Step 1: 移除不再需要的 collapsedNavItems**

找到第 149-354 行的 `collapsedNavItems` 数组，移除以下项：
- `sessions`
- `skills`
- `skill-pool`
- `agents`
- `mcp`
- `system-config-page`（如果不是条件渲染）
- 所有 instance 相关项（如果被注释掉了）

保留以下项：
- `chat`
- `workspace`
- `my-skills`
- `tools`
- `my-mcp`
- `cron-jobs`
- `channels`
- `agent-config`
- `heartbeat`
- `market`
- `models`
- `featured-cases-management`
- `environments`
- `security`
- `system-config-page`（条件渲染）
- `analytics-business-overview`
- `analytics-messages`
- `analytics-users`
- `analytics-sessions`
- `analytics-traces`
- `continuous-iteration`

- [ ] **Step 2: 提交修改**

```bash
git add console/src/layouts/Sidebar.tsx
git commit -m "refactor(nav): clean up collapsedNavItems

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: 前端构建验证

**Files:**
- 无文件修改，仅验证

- [ ] **Step 1: 运行前端构建**

```bash
cd console && npm run build
```

Expected: 构建成功（除了已有的 diff/tiny-pinyin 模块问题）

- [ ] **Step 2: 确认所有修改已提交**

```bash
git status
```

Expected: 无未提交的修改

- [ ] **Step 3: 查看提交历史**

```bash
git log --oneline -10
```

---

## Self-Review

**1. Spec Coverage:**
- 新增一级菜单国际化文本 ✓ (Task 1)
- 更新 DEFAULT_OPEN_KEYS ✓ (Task 2)
- 重构 menuItems：聊天、创作中心、运行中心、系统设置、洞察中心、质量工程、应用市场 ✓ (Tasks 3-6)
- 清理 collapsedNavItems ✓ (Task 8)
- 移除不需要的菜单项 ✓ (Tasks 3-6, 8)

**2. Placeholder Scan:**
- 无 TBD、TODO 或占位符 ✓

**3. Type Consistency:**
- 所有菜单 key 使用一致的命名 ✓
- 国际化 key 与使用一致 ✓