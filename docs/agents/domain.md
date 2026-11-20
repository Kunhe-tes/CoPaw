# Domain Docs

工程技能探索代码前，应先读取相关领域文档。

## Before exploring, read these

- 根目录 `GLOSSARY.md`：项目领域词汇。
- `docs/adr/`：与当前工作相关的架构决策。

文件不存在时直接继续，不主动要求创建。
由 domain-modeling 在术语或决策明确后按需补充。

## Layout

本仓库使用单上下文布局：

- 领域术语：根目录 `GLOSSARY.md`。
- 架构决策：`docs/adr/`。

现有 `CONTEXT.md` 可保留用于历史兼容，但新领域定义统一写入
`GLOSSARY.md`；两者同时存在时不得静默选择冲突定义。

## Consumer rules

- 分析代码前，阅读与任务相关的领域术语和 ADR。
- 文档不存在时继续执行，不预先创建空术语表。
- 在 spec、issue 和实现中使用领域文档定义的术语，避免使用词汇表
  明确排除的近义词。
- 与既有 ADR 冲突时明确指出对应 ADR 和重新讨论的理由，不静默覆盖。
- 术语存在实际缺口时，先检查是否偏离项目语言，再通过领域建模补充。

## Flag ADR conflicts

与现有 ADR 冲突时，明确指出对应 ADR 和重新讨论的理由，
不得静默覆盖既有决策。
