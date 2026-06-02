# 菜单结构重构设计文档

## 概述

**目标**：重构前端菜单结构，按照新的业务模块重新组织一级和二级菜单。

**影响范围**：
- `console/src/layouts/Sidebar.tsx` - 菜单配置
- `console/src/layouts/constants.ts` - KEY_TO_PATH 和 KEY_TO_LABEL 映射
- `console/src/locales/zh.json` - 国际化文本
- `console/src/locales/en.json` - 英文翻译

---

## 新菜单结构

### 一级菜单顺序

1. 聊天（单独一级）
2. 创作中心
3. 运行中心
4. 应用市场（单独一级）
5. 系统设置
6. 洞察中心
7. 质量工程

### 完整结构

```
聊天

创作中心
  ├── 文件 (workspace)
  ├── 我的技能 (my-skills)
  ├── 工具
  └── 我的 MCP (my-mcp)

运行中心
  ├── 定时任务 (cron-jobs)
  ├── 频道
  ├── 运行配置 (agent-config)
  └── 心跳

应用市场

系统设置
  ├── 模型
  ├── 精选案例管理 (featured-cases-management)
  ├── 环境变量
  ├── 安全
  └── 系统特性配置 (system-config-page)

洞察中心
  ├── 运营看板 (analytics-business-overview)
  ├── 用户消息 (analytics-messages)
  ├── 用户分析 (analytics-users)
  ├── 会话分析 (analytics-sessions)
  └── 对话分析

质量工程
  └── 持续治理 (continuous-iteration)
```

---

## 菜单项映射表

| 新一级菜单 | 新二级菜单 | 原 key | 原 key 说明 |
|------------|------------|--------|-------------|
| 聊天 | - | `chat` | 单独一级 |
| 创作中心 | 文件 | `workspace` | 原Agent组 |
| 创作中心 | 我的技能 | `my-skills` | 原市场组 |
| 创作中心 | 工具 | `tools` | 原Agent组 |
| 创作中心 | 我的 MCP | `my-mcp` | 原市场组 |
| 运行中心 | 定时任务 | `cron-jobs` | 原控制组 |
| 运行中心 | 频道 | `channels` | 原控制组 |
| 运行中心 | 运行配置 | `agent-config` | 原Agent组 |
| 运行中心 | 心跳 | `heartbeat` | 原控制组 |
| 应用市场 | - | `market` | 单独一级 |
| 系统设置 | 模型 | `models` | 原设置组 |
| 系统设置 | 精选案例管理 | `featured-cases-management` | 原控制组 |
| 系统设置 | 环境变量 | `environments` | 原设置组 |
| 系统设置 | 安全 | `security` | 原设置组 |
| 系统设置 | 系统特性配置 | `system-config-page` | 原Agent组（条件渲染） |
| 洞察中心 | 运营看板 | `analytics-business-overview` | 原Analytics组 |
| 洞察中心 | 用户消息 | `analytics-messages` | 原Analytics组 |
| 洞察中心 | 用户分析 | `analytics-users` | 原Analytics组 |
| 洞察中心 | 会话分析 | `analytics-sessions` | 原Analytics组 |
| 洞察中心 | 对话分析 | `analytics-traces` | 原Analytics组 |
| 质量工程 | 持续治理 | `continuous-iteration` | 原Harness组 |

---

## 需要移除的菜单项

以下原菜单项不在新结构中：

| 原 key | 原菜单名 | 处理 |
|--------|----------|------|
| `sessions` | 会话 | 移除 |
| `skills` | 技能 | 移除（已有 my-skills） |
| `skill-pool` | 技能池 | 移除 |
| `agents` | 智能体管理 | 移除 |
| `mcp` | MCP | 移除（已有 my-mcp） |

---

## 国际化文本

### 新增一级菜单文本

**zh.json**:
```json
"creationCenter": "创作中心",
"runCenter": "运行中心",
"insightCenter": "洞察中心",
"qualityEngineering": "质量工程"
```

**en.json**:
```json
"creationCenter": "Creation Center",
"runCenter": "Run Center",
"insightCenter": "Insight Center",
"qualityEngineering": "Quality Engineering"
```

---

## DEFAULT_OPEN_KEYS 更新

```typescript
export const DEFAULT_OPEN_KEYS = [
  "creation-center",
  "run-center",
  "system-settings",
  "insight-center",
  "quality-engineering",
];
```

---

## 实现要点

1. **Sidebar.tsx 修改**：
   - 重新组织 `menuItems` 数组
   - 更新一级菜单 key（使用新命名如 `creation-center`、`run-center`）
   - 保持二级菜单 key 不变（便于路由映射）
   - 移除不需要的菜单项

2. **constants.ts 修改**：
   - 更新 `DEFAULT_OPEN_KEYS`
   - 保持 `KEY_TO_PATH` 和 `KEY_TO_LABEL` 不变（二级菜单 key 未变）

3. **locales 修改**：
   - 新增一级菜单的国际化文本