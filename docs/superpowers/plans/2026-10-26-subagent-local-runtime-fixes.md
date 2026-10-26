# SubAgent local runtime fixes

**Goal:** 修复并发限额、source 句柄隔离、取消后遗留 Shell、跨进程状态倒退四个问题。

**Architecture:** 保留粘性分发和本地 Python 子进程。以规范化 run store 目录补齐内存 scope 身份；启动前预占名额；取消时清理 worker 的独立子进程；每 Run 使用文件锁保护完整读改写。

**Tech Stack:** Python asyncio、fcntl、psutil、pytest。直接在当前工作区执行，保留用户已有修改；不修改跨 Pod 路由，不引入数据库或 Redis 协议。

## Task 1: Reproduce

- [x] 新建 `tests/unit/subagents/test_local_runtime_regressions.py`，使用测试专用 SubAgentDefinition，不依赖已移除的内置专家。
- [x] barrier 同步三个 start，请求限额 2，断言只有两个 running，启动失败后能重新启动。
- [x] 相同 tenant/agent 配合两个目录，验证限额、回收、cancel 互不影响。
- [x] 两个真实 Python 进程控制旧 mark_running 与 finish 的顺序，断言终态及结果保留。
- [x] 真实 worker 创建独立 Shell session，取消后断言 worker 与 Shell 均退出；覆盖忽略 SIGTERM 的进程。
- [x] 使用项目 venv 运行新增测试，原实现上 10 项失败、1 项边界检查通过，确认失败原因对应四项缺陷；之后补充三项边界回归。

## Task 2: Implement

- [x] 修改 `src/swe/app/subagents/supervisor.py`：统一 scope key；同步检查并登记 starting reservation；finally 释放 reservation；active/starting 按 run_id 去重计数。
- [x] 修改同文件取消流程：通过 psutil 捕获、清理独立子进程，进程清理完成后才移除 handle 和持久化取消。
- [x] 修改 `src/swe/app/subagents/run_store.py`：使用每 Run 稳定 lock 文件保护所有已有记录更新入口，等待 flock 时避免阻塞事件循环；锁内重新读取状态。
- [x] 新增 14 项回归测试通过。

## Task 3: Verify and document

- [x] 执行现有 Supervisor、run store 和相关 worker/工具测试：35 项直接相关测试通过；完整专项 218/67，对照已知 186/85 基线。
- [x] 对受影响旧测试使用本地测试定义替换无效 fixture，恢复原有 18 项失败，保留生产内置专家为空的契约。
- [x] 对本次修改文件执行格式、静态检查，pre-commit 全部通过；GitNexus detect_changes 已执行，但图谱仍将 run store 关联到大量无关流程，实际范围以源码 diff 和测试确认。
- [x] 更新报告、优化方案和 `analysis/playbook/subagent-runtime.md`，记录实际测试结果；保留其他工作区修改。后续按用户要求提交四项修复代码、相关测试和本计划；遵循现有忽略规则，不强制加入 analysis 文档。

实现没有增加 worker 信号处理、应用 shutdown、MySQL/Redis 协调或跨 Pod 取消。取消通过捕获已有后代进程并逐一清理来覆盖独立 Shell session，不将此能力描述为容器级强隔离。
