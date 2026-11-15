# Issue tracker: Local Markdown

事项与规格以 Markdown 文件存放于 `.scratch/`。

## Conventions

- 每项功能独立目录：`.scratch/<feature-slug>/`。
- 规格文件：`.scratch/<feature-slug>/spec.md`。
- 实施事项：`.scratch/<feature-slug>/issues/<NN>-<slug>.md`，
  从 `01` 开始编号，每项一个文件。
- 文件顶部使用 `Status:` 记录状态：`open`、`claimed`、`resolved`。
- 评论与讨论追加至文件底部的 `## Comments` 下。

## When a skill says "publish to the issue tracker"

在 `.scratch/<feature-slug>/` 下创建相应文件，必要时创建目录。

## When a skill says "fetch the relevant ticket"

读取指定路径；仅给出编号时，在对应功能的 issues 目录定位文件。

## Wayfinding operations

- Map：`.scratch/<effort>/map.md`，记录 Notes、Decisions-so-far 和 Fog。
- Child ticket：`.scratch/<effort>/issues/NN-<slug>.md`。
- Type：`research`、`prototype`、`grilling` 或 `task`。
- Blocking：文件顶部用 `Blocked by: NN, NN` 记录依赖；
  所有依赖均为 `resolved` 后才可开始。
- Frontier：按编号选择首个开放、无阻塞且未领取的事项。
- Claim：开始工作前保存 `Status: claimed`。
- Resolve：将答案追加至 `## Answer`，设置 `Status: resolved`，
  并将结论摘要与文件链接追加至 map 的 Decisions-so-far。
