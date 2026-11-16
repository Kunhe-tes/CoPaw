# 会话迁移性能验收

本说明复用 `prepare → migrate --apply`，不增加现场迁移阶段。性能规格以 `.scratch/conversation-migration-performance/spec.md` 为准。禁止通过放宽源冻结、完整校验、fsync、单 SQL owner 或 source 准入来降低耗时。

## 隔离范围

使用项目虚拟环境、固定代码版本、本地临时输入目录及专用空 MySQL 测试库。`SWE_TEST_DB_NAME` 必须以 `test_` 开头或 `_test` 结尾，且不得等于应用库；测试 fixture 再新建随机子库，只删除自己创建的子库。数据库凭据由环境或 Secret 注入，不写进报告或提交。该测试会执行 CREATE/DROP DATABASE，须使用获准的测试实例及账号。

```bash
cd /path/to/isolated/worktree
export PYTHONPATH=src
export SWE_TEST_DB_HOST=获准测试实例
export SWE_TEST_DB_PORT=3306
export SWE_TEST_DB_USER=获准测试账号
export SWE_TEST_DB_NAME=test_conversation_performance
# SWE_TEST_DB_PASSWORD 由 Secret 注入，值是实际密码，不经过 SWE_DB_ACCESS 前缀处理。
/path/to/project/venv/bin/python -m pytest \
  tests/integrated/conversation_storage/test_performance_workflow_mysql.py \
  -q -s --disable-warnings \
  -o cache_dir=/private/tmp/conversation-performance-cache \
  --basetemp=/private/tmp/conversation-performance-run
```

缺少测试库配置时 pytest 会 skipped；skipped 不作为 MySQL 验收通过证据。基线与最终版本须使用不同 `basetemp`，相同 Python/依赖、数据库实例、worker/IO/预算和测试数据。记录两个 commit SHA、操作系统、数据库版本、延迟条件与日志；比较输出的 `representative_prepare_migrate` JSON，不比较不同输入的总时长。

用例固定三个小 source/workspace，其中一个包含 128 条消息；另一路覆盖运行中 Turn 导致的 source 失败、其他 source 发布、修复后重跑。资源固定 workers=3、io-workers=2、memory=128 MiB。第二次运行使用原 manifest；不重新 prepare，不删除票据。已有更广的 source 保护、分享/归档/事件/checkpoint 和中断恢复用例由最终组合验收一并运行。本用例不代替这些语义回归。

## 指标口径

- `db_calls/db_seconds`：迁移 DML 门面调用及累计等待，含失败；一次 prepared 门面调用可能执行多块。
- `db_statement_attempts/db_statement_seconds`：普通 execute 或每个 prepared 分块的执行尝试及累计执行耗时，包含失败/取消，不含协议 prepare/reset、建连、读取结果和清理。
- `db_executemany_calls/db_executemany_seconds`：驱动 executemany 调用单列；内部 SQL 数未知，不能当作一条真实 SQL。
- `db_transaction_begins/commits/rollbacks`：底层边界调用尝试，嵌套事务不重复计数；提交次数不是提交成功证明，UnknownCommit 仍全局停止。
- `bundle_opens/bundle_index_parses`：实际打开与索引解析尝试；生命周期限于一次安全读取，不跨命令缓存。
- `stage_wall_seconds`：同名阶段累计墙钟，含当前阶段。并发预读可能重叠；`io_seconds` 是累计 IO 时间，不能相加为墙钟。
- `rss_peak_bytes/temp_peak_bytes`：现有进度的采样进程 RSS/已登记临时数据峰值；解析门禁不是进程 RSS 硬上限。

数据库层各口径有重叠，禁止求和。性能日志不包含正文、凭据、SQL 参数或源路径。prepare 测量由测试外层观察上下文捕获；migrate 使用现有 CLI 进度。失败时报告实际退出码和阶段，不能将 partial_success 解释为全部 source 成功。

## 结果边界

结果须区分本地单测、真实隔离 MySQL、本地目录与受控延迟 IO。未执行真实 NAS、万级基线、生产部署或现场旧镜像回滚时明确标注。SQL 形态/计数改善不等于承诺现场总耗时倍数；数据库身份或命名锁丢失仍须排查连接/代理原因。
