# 新会话 @ 引用菜单展开方向设计

## 目标

新会话欢迎页中的 `@` 上下文引用菜单向下展开；已有会话底部输入框中的菜单继续向上展开。

## 背景

`SkillTokenEditor` 同时被 `WelcomeCenterLayout`（新会话欢迎页）和 `Sender`（已有会话底部输入框）使用。菜单容器当前固定使用 `bottom: calc(100% + 3px)`，导致两个场景都向上展开。

## 方案

为 `SkillTokenEditor` 增加可选的 `mentionMenuPlacement` 属性：

- 默认值为 `"top"`，保持已有会话现有的向上展开行为。
- 值为 `"bottom"` 时，菜单使用 `top: calc(100% + 3px)` 向下展开。
- `WelcomeCenterLayout` 显式传递 `mentionMenuPlacement="bottom"`。
- `Sender` 不传该属性，以默认值保持向上展开。

菜单宽度、左右对齐、层级、筛选、键盘导航、点击选择和无障碍属性均不改变。

## 测试

在 `SkillTokenEditor` 组件测试中覆盖：

1. 未传 placement 时，菜单容器使用向上定位。
2. 传入 `"bottom"` 时，菜单容器使用向下定位，且不保留向上定位属性。

## 非目标

- 不实现基于可用空间的自动翻转。
- 不调整菜单视觉样式或数据加载逻辑。
