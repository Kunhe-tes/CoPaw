# Domain Docs

工程技能探索代码前，应先读取相关领域文档。

## Before exploring, read these

- 根目录 `GLOSSARY.md`：项目领域词汇。
- `docs/adr/`：与当前工作相关的架构决策。

文件不存在时直接继续，不主动要求创建。
由 domain-modeling 在术语或决策明确后按需补充。

## File structure

采用 single-context：根目录维护一份 `GLOSSARY.md`，
架构决策统一存放于 `docs/adr/`。

## Use the glossary's vocabulary

事项标题、重构建议、假设和测试名称应使用词汇表定义的术语，
避免使用词汇表明确排除的近义词。
遇到缺失术语时，先检查是否偏离项目语言；确有缺口则记录给
domain-modeling 处理。

## Flag ADR conflicts

与现有 ADR 冲突时，明确指出对应 ADR 和重新讨论的理由，
不得静默覆盖既有决策。
