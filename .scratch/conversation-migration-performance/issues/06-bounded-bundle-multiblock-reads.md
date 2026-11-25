# 06: 安全复用 bundle 打开与索引解析

**What to build:** 迁移正文预取及关联证据读取对同一 bundle 一次安全打开、一次解析索引并读取多个请求块，减少 NAS 小操作且保持完整性保护。

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] 提供有界多块读取并接入运行时正文预取、同 publication 消息读取和适用的 import plan/恢复证据路径，保留单块兼容接口。
- [x] 当前读取操作复用同一受限文件描述符及解析结果，不建立跨 source、跨命令的长期正文或证据缓存。
- [x] 每个 extent 校验边界、长度和 publication 身份，维持索引/正文一致性及既有文件状态复查契约。
- [x] 拒绝软链接、越界、特殊文件、截断及异常替换；覆盖同大小替换、读取中修改与取消，资源正确关闭和排空。
- [x] 多块总字节、解析膨胀及 IO 并发计入共享预算，保留 fsync、最终源复查和全量语义验证。
- [x] 经现有迁移入口验证历史、归档、分享及恢复结果一致，计数证明单次多块读取索引只解析一次；本地延迟测试不宣称真实 NAS 放行。


## Answer

- 新增操作级 BundleStore.open_reader/BundleReader 与有界 read_extents；一次安全打开和索引解析后读取多个块，无跨命令缓存，原 read_extent/iter_extent 接口保留。
- 接入 runtime_prefetch、同 publication 消息验证、offline commit/verify 的 import plan/恢复块、Turn recovery 及验证多 extent 入口。逐 extent 校验类型、边界及块 kind，publication 证据保留 operation_key/长度身份校验。
- 索引解析前预留 JSON 膨胀预算；预取全部正文按总字节及解析膨胀计入既有 worker allowance，读取继续通过共享 MigrationIO，取消后排空并关闭 FD。文件退出复查 dev/inode/size/mtime_ns/ctime_ns，覆盖同大小改写和名称替换。
- TDD：新增读取器测试在实现前出现 4 个预期 AttributeError；同 publication 读取性能测试先证实 4 次打开再通过单次打开断言。安全测试覆盖软链接、FIFO、截断、越界、同大小改写/替换及取消排空。
- 验证：storage 全目录 + conversation CLI 两个模块 **1658 passed in 59.54s**；合并最新集成 6153dd1e0 后相关 focused **161 passed in 0.93s**。实现提交 c16027308、兼容修复65b35ec2f 均正常通过仓库 commit hooks（AST、mypy、black、flake8、pylint 等），无绕过。
- 范围限制：本地目录验证，不宣称真实 NAS 放行或总耗时倍数；隔离 MySQL 与完整 prepare→migrate 现场验收由集成票据08执行。bundle 计数 observation 接线按集成负责人约定在合入后补齐；本票据已有一次打开/一次索引解析断言。
