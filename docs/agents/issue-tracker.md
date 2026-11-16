# Issue tracker: Local Markdown

本仓库的 issues 和 specs 存放于 `.scratch/`，不向外部平台发布。

## Conventions

- 每个功能一个目录：`.scratch/<feature-slug>/`。
- Spec：`.scratch/<feature-slug>/spec.md`。
- 实施任务：`.scratch/<feature-slug>/issues/<NN>-<slug>.md`，从 01 编号，每个任务单独一个文件。
- 文件顶部用 `Status:` 记录状态；技能要求的标签以原字符串记录，例如 `Status: ready-for-agent`。
- 评论和讨论追加在 `## Comments` 下。
- “发布到 issue tracker”表示创建上述本地文件。
- “读取相关 ticket”表示读取用户指定的本地文件。
- 不自动提交、推送或创建外部 issue。

## Wayfinding operations

- Map：`.scratch/<feature>/map.md`。
- 子任务使用独立任务文件，以 `Type:` 记录任务类型。
- 依赖用 `Blocked by: NN, NN` 表示。
- 按编号选择未解决、未领取且依赖已解决的任务。
- 领取时设置 `Status: claimed`。
- 完成后追加 `## Answer`，设置 `Status: resolved`，并在 map 中补充结果摘要和相对链接。
