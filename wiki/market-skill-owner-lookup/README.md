# 应用市场技能拥有用户反查

本文说明应用市场里每个技能管理按钮新增的“查看拥有用户”能力。

返回 [CoPaw Wiki 索引](../README.md)。

## 一句话理解

技能拥有用户反查不依赖历史分发日志。Console 会读取当前 source 下的用户列表，再分别查询每个用户当前拥有的技能，并用市场技能的稳定目录名 `skill_name` 做精确匹配。

## 查询入口

入口位于应用市场的技能管理操作：

- 技能卡片的“管理”下拉菜单：`查看拥有用户`
- 技能详情页的管理按钮区：`查看拥有用户`

反查结果展示：

| 字段 | 含义 |
| --- | --- |
| 用户 | `tenant_name` 和 `tenant_id` |
| 机构 | `bbk_id` |
| 技能目录 | 用户工作区里的 `skill_name` |
| 市场版本 | 当前市场技能版本 |
| 用户版本 | 用户当前安装或接收的版本 |
| 接收版本 | `received_version` |
| 状态 | 用户侧技能是否启用 |
| 版本 | 是否可更新或已经同步 |

## 匹配规则

匹配优先使用市场条目的 `skill_name`。如果市场数据没有 `skill_name`，才回退到市场展示名 `name`。

用户侧只看当前技能列表：

```text
/market/skills/mine
/market/skills/received
```

请求时会带上目标用户的 `X-User-Id` 和 `X-Tenant-Id`，从而读取对应用户工作区。两个列表按 `skill_name` 去重后再匹配。

## 行为边界

- 这是当前状态反查，不是历史分发审计。
- 同名技能即视为命中，即使它不是通过当前市场条目分发得到。
- 被删除、改名或工作区读取失败的用户不会出现在命中列表；弹窗会显示读取失败数量。
- 版本状态来自用户技能数据的 `has_update`，或市场版本和用户版本不一致的比较结果。

## 前端入口

| 文件 | 职责 |
| --- | --- |
| `console/src/api/modules/market.ts` | 增加按目标用户读取技能列表的 API helper |
| `console/src/pages/Market/skillOwnerLookup.ts` | 稳定名称解析、用户技能匹配和版本状态计算 |
| `console/src/pages/Market/SkillOwnerLookupModal.tsx` | 反查弹窗 |
| `console/src/pages/Market/SkillCard.tsx` | 卡片管理菜单入口 |
| `console/src/pages/Market/SkillDetailDrawer.tsx` | 详情页管理入口 |

覆盖测试位于 `console/src/pages/Market/skillOwnerLookup.test.ts`。
