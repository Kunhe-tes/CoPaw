# 技能分发预览功能设计文档

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在分发弹窗中展示用户技能持有情况，支持首次分发和覆盖更新两种场景

**Architecture:** 概览卡片 + 用户状态标记双层展示，两种模式（按用户/按机构）统一设计

**Tech Stack:** React + Ant Design + FastAPI (Market)

---

## 概述

为技能分发弹窗增加预览功能，让管理员在分发前了解每个用户的技能持有情况。

**核心需求：**
1. 展示每个用户的技能状态：首次分发 / 覆盖更新（显示当前版本）
2. 支持"默认选中已分发用户"快速覆盖
3. 两种模式（按用户/按机构）统一展示

---

## UI 设计

### 概览卡片

在 TenantSelector 区域上方添加概览卡片：

```
┌─────────────────────────────────────────────────────────────┐
│  分发预览                              [✓ 默认选中已分发用户] │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                     │
│  │   45    │  │   38    │  │    0    │                     │
│  │ 首次分发 │  │ 覆盖更新 │  │跳过(冲突)│                     │
│  └─────────┘  └─────────┘  └─────────┘                     │
│  当前技能版本: v1.2 | 已分发用户数: 38                       │
└─────────────────────────────────────────────────────────────┘
```

- 统计数字实时更新，反映当前选中用户的分发情况
- 勾选"默认选中已分发用户"后，自动选中所有已持有该技能的用户

### 用户状态标记

用户卡片使用两行布局，显示用户名 + 状态：

```
┌──────────┐  ┌──────────┐  ┌──────────┐
│  ✓ 张三  │  │  ○ 王五  │  │  ⚠ 钱七  │
│ v1.0→v1.2│  │   首次   │  │ 自建冲突 │
└──────────┘  └──────────┘  └──────────┘
```

**状态样式：**
- 覆盖更新：蓝色边框 + 蓝色背景，显示版本变化 (v旧→v新)
- 首次分发：灰色边框，绿色"首次"标签
- 自建冲突：黄色边框 + 黄色背景，红色"自建冲突"标签

### 按机构模式

Collapse 展开的机构用户列表使用相同的小卡片布局：

```
┌─────────────────────────────────────────────────────────────┐
│  ▼ 总行 (100) - 25 人               覆盖: 18 | 首次: 7    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  ✓ 张三  │  │  ✓ 李四  │  │  ○ 王五  │  │  ○ 赵六  │   │
│  │v1.0→v1.2 │  │v1.0→v1.2 │  │   首次   │  │   首次   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  ▶ 北京分行 (200) - 38 人           覆盖: 20 | 首次: 18    │
└─────────────────────────────────────────────────────────────┘
```

- 机构标题行显示：机构名 + 用户数 + 覆盖/首次统计
- 展开后使用 grid 布局显示用户小卡片

---

## 数据模型

### 前端类型定义

```typescript
// 用户技能状态
interface UserSkillStatus {
  tenant_id: string;
  tenant_name: string | null;
  bbk_id: string | null;
  status: 'first_time' | 'update' | 'conflict';
  current_version?: string;  // 当前持有版本（update 时显示）
}

// 分发预览统计
interface DistributionPreview {
  first_time_count: number;
  update_count: number;
  conflict_count: number;
  skill_version: string;
  distributed_user_count: number;
}
```

### 后端 API

新增 API 获取技能分发预览：

```
GET /market/skills/{item_id}/distribution-preview?source_id={source_id}
```

**响应：**
```json
{
  "skill_version": "v1.2",
  "users": [
    {
      "tenant_id": "80001",
      "tenant_name": "张三",
      "bbk_id": "100",
      "status": "update",
      "current_version": "v1.0"
    },
    {
      "tenant_id": "80002",
      "tenant_name": "王五",
      "bbk_id": "100",
      "status": "first_time"
    }
  ],
  "distributed_user_ids": ["80001", "80003", ...]
}
```

---

## 文件清单

### 后端新增

```
market/src/market/app/routers/skills_market.py  # 新增预览 API
market/src/market/marketplace/service.py         # 新增预览查询方法
```

### 前端新增

```
console/src/api/modules/skillDistribution.ts     # 新增预览 API 调用
console/src/components/DistributionPreview/      # 概览卡片组件
    index.tsx
    index.module.less
```

### 前端修改

```
console/src/components/TenantSelector/index.tsx  # 添加状态标记显示
console/src/components/TenantSelector/index.module.less  # 添加状态样式
console/src/pages/Market/DistributeTargetModal.tsx  # 集成预览组件
```

---

## 实现范围

本次迭代包含：

1. 后端预览 API 实现
2. 前端概览卡片组件
3. TenantSelector 用户状态标记
4. "默认选中已分发用户"功能

本次迭代不包含：

1. MCP 分发预览（后续迭代）
2. 批量分发历史记录
3. 分发回滚功能

---

## 交互设计

### 默认选中已分发用户

1. 勾选"默认选中已分发用户"选项
2. 自动调用 `onChange`，传入所有已分发用户的 tenant_id
3. 概览卡片更新统计

### 实时统计更新

1. 监听 `selectedTenantIds` 变化
2. 根据用户状态计算统计
3. 更新概览卡片显示

### 按机构模式同步

1. 用户选择机构时，获取机构内用户状态
2. Collapse 展开后显示用户小卡片
3. 机构标题行显示统计摘要