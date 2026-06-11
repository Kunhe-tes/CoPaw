# CoPaw Wiki 索引

本目录记录当前代码中已经落地、适合复用和排查的功能说明。优先从这里进入，再回到源码确认当前实现细节。

## 功能文档

| 文档 | 适合回答的问题 |
| --- | --- |
| [Cron 定时任务](cron/README.md) | 定时任务创建、调度回调、执行上下文、广播、Monitor 同步、完成通知和通知延迟 |
| [应用市场技能拥有用户反查](market-skill-owner-lookup/README.md) | 应用市场按技能目录名反查哪些用户当前拥有同名技能，以及版本/启用状态 |
| [系统提示词注入](system-prompt-injections/README.md) | source 级和请求级 system prompt injection 如何配置、合并、进入 Agent system prompt |
| [静态文件访问网络](network-aware-file-urls/README.md) | `copy_file_to_static` 如何按办公网/业务网生成可访问 URL |
| [Hook](hook/README.md) | hook 运行机制和示例 |
| [Session 压缩](session-compaction/README.md) | 会话压缩相关行为 |
| [Session 技能刷新](session-skill-refresh/README.md) | 会话内技能刷新相关行为 |
| [用户环境变量配置](user-env-config/README.md) | tenant/source scope 下的运行时环境变量配置和使用 |

## 本地分支补充

当前 `v1.0.0_0616` 本地分支相对 `origin/v1.0.0` 的特性补充主要包括：

- `feat(system-config): add system prompt injections`
- `feat(static): support network-aware file URLs`
- 当前未提交的 cron 通知延迟：`meta.notification_delay_minutes`
- 当前未提交的分发拥有者管理：cron 分发子任务反查/批量操作、应用市场技能按名称反查拥有用户

这些内容已经分别补入上表对应 wiki。
