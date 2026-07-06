# `/api/models` 10s Gap 根因定位记录

## 背景

生产环境 `GET /api/models` 出现约 9.5s 耗时。提交
`b0a47d1d fix(models): instrument pre-route timing` 已对 provider models
请求链路增加分段日志。

## 已观察到的关键日志

同一次请求：

```text
provider_models_request_done path=/api/models status_code=200 duration_ms=9524 tenant_id=80280195 source_id=RMASSIST scope_id=ODAyODAxOTU.Uk1BU1NJU1Q dependency_ms=1 dependency_ensure_ms=1 dependency_get_instance_ms=0 dependency_cache_hit_before=True handler_ms=7 after_handler_ms=3 content_length=1686

provider_models_middleware_done name=HeaderPassthroughMiddleware path=/api/models status_code=200 total_ms=9523 pre_ms=0 downstream_ms=9523 tenant_id=80280195 source_id=RMASSIST scope_id=ODAyODAxOTU.Uk1BU1NJU1Q fields={'passthrough_header_count': 1}

provider_models_middleware_done name=TenantIdentityMiddleware path=/api/models status_code=200 total_ms=9521 pre_ms=0 downstream_ms=9521 tenant_id=80280195 source_id=RMASSIST scope_id=ODAyODAxOTU.Uk1BU1NJU1Q fields={'resolve_ms': 0, 'store_ms': 0, 'bind_ms': 0, 'is_exempt': False}

provider_models_middleware_done name=SourceSystemConfigMiddleware path=/api/models status_code=200 total_ms=9521 pre_ms=8 downstream_ms=9512 tenant_id=80280195 source_id=RMASSIST scope_id=ODAyODAxOTU.Uk1BU1NJU1Q fields={'source_id': 'RMASSIST', 'has_service': True, 'resolve_config_ms': 8}

provider_models_middleware_done name=TenantWorkspaceMiddleware path=/api/models status_code=200 total_ms=9512 pre_ms=3 downstream_ms=9509 tenant_id=80280195 source_id=RMASSIST scope_id=ODAyODAxOTU.Uk1BU1NJU1Q fields={'effective_tenant_id': 'ODAyODAxOTU.Uk1BU1NJU1Q', 'workspace_loaded': True, 'workspace_ms': 3, 'require_workspace': True}

provider_models_middleware_done name=AgentContextMiddleware path=/api/models status_code=200 total_ms=9508 pre_ms=0 downstream_ms=9508 tenant_id=80280195 source_id=RMASSIST scope_id=ODAyODAxOTU.Uk1BU1NJU1Q fields={'agent_id': None, 'tenant_id': '80280195'}

provider_models_middleware_done name=AuthMiddleware path=/api/models status_code=200 total_ms=9502 pre_ms=0 downstream_ms=9502 tenant_id=80280195 source_id=RMASSIST scope_id=ODAyODAxOTU.Uk1BU1NJU1Q fields={'skip_auth': True, 'skip_auth_ms': 0}

provider_models_handler_done path=/api/models tenant_id=80280195 manager_tenant_id=ODAyODAxOTU.Uk1BU1NJU1Q duration_ms=7 provider_count=3 builtin_count=0 custom_count=3 model_count=0 extra_model_count=3 root_path=/opt/deployments/app/working.secret/ODAyODAxOTU.Uk1BU1NJU1Q/providers
```

另有关键时间关系：

```text
provider_models_middleware_before_next name=AuthMiddleware ...
provider_manager_dependency_start ...
```

这两条日志的生产时间戳间隔约 10 秒。

## 已排除项

当前证据显示慢点不在以下路径：

- `HeaderPassthroughMiddleware` 自身：`pre_ms=0`
- `TenantIdentityMiddleware` 自身：`resolve_ms=0 store_ms=0 bind_ms=0`
- `SourceSystemConfigMiddleware` 自身：`resolve_config_ms=8`
- `TenantWorkspaceMiddleware` 自身：`workspace_ms=3`
- `AgentContextMiddleware` 自身：`pre_ms=0`
- `AuthMiddleware` 自身：`skip_auth=True skip_auth_ms=0`
- Provider manager 依赖执行体：`dependency_ms=1`
- provider storage ensure：`dependency_ensure_ms=1`
- provider manager get instance：`dependency_get_instance_ms=0`
- provider models handler：`handler_ms=7`
- handler 之后响应构建/出栈：`after_handler_ms=3`

## 当前定位

9.5s gap 位于：

```text
AuthMiddleware call_next(request)
  -> Starlette/FastAPI 路由/依赖调度
  -> get_provider_manager() 函数内第一条 provider_manager_dependency_start 日志
```

`/api/models` 路由没有额外 router/global dependency，`get_provider_manager`
是该 endpoint 的第一个业务依赖。

## 主要假设

### 假设 A：AnyIO threadpool token 等待

`get_provider_manager` 当前是同步 `def` 依赖。FastAPI 会将同步 dependency
放入 AnyIO threadpool 执行。`provider_manager_dependency_start` 是函数内部日志，
因此如果 threadpool token 饱和，请求会在进入该函数前排队，形成：

```text
AuthMiddleware before_next 已打印
等待 AnyIO threadpool token
拿到 token 后进入 get_provider_manager()
provider_manager_dependency_start 才打印
```

这能解释 `get_provider_manager` 自身只执行 1ms，但进入它之前等待约 10s。

### 假设 B：event loop 被其它同步代码阻塞

如果 event loop 在该窗口被阻塞，请求也可能停在下游调度阶段。但当前窗口没有
`RUNTIME_DIAGNOSTIC` 日志，缺少 `event_loop_lag_max_ms` 等证据。

## 生产止血建议

先阶梯调大 threadpool 配置验证，不建议直接拉到很大：

```text
ANYIO_THREAD_TOKENS=64  -> 96 -> 128 -> 192
ASYNCIO_EXECUTOR_WORKERS=64 -> 96 -> 128 -> 192
```

优先观察 `ANYIO_THREAD_TOKENS` 调整效果。当前怀疑点主要是 FastAPI 同步
dependency 使用的 AnyIO threadpool。

不要一上来设为 512。原因是它会允许更多阻塞同步任务同时运行，可能引发 CPU、
磁盘 I/O、DB/HTTP 连接池、文件句柄、内存和 Python 线程调度争抢，导致整体
P95/P99 更差。

## 代码优化方向

把 `/api/models` 热路径从同步 dependency/threadpool 中移出：

1. 将 `get_provider_manager` 改为 `async def`。
2. cache hit 热路径直接同步快速返回，不进入 threadpool。
3. cache miss、首次初始化、可能涉及文件 I/O 的路径再显式使用
   `anyio.to_thread.run_sync(...)`。

这样可以避免 `dependency_ms=1` 的热路径因为 threadpool 饱和而排队 10s。

## 需要补充的根因数据

### 线程池饱和证据

增加埋点记录同步 dependency 进入前的等待时间，或在 `get_provider_manager`
外层用 async wrapper 记录：

```text
provider_manager_dependency_wait_before
provider_manager_dependency_enter
provider_manager_dependency_wait_ms
```

若 `wait_ms` 接近 9500ms，即坐实 threadpool 等待。

### 同窗口资源指标

围绕生产时间 `2026-07-02 19:40:15` 到 `19:40:30` 查看：

- CPU 使用率和 load average
- CPU iowait
- 磁盘 `%util`、`await`、队列深度
- pod/container filesystem read/write rate
- DB/HTTP 连接池等待
- 进程线程数、FD 数
- 同 worker 内其它慢请求、备份、压缩、解压、skill 安装/扫描、workspace 文件操作、cron 任务

### 可用命令

主机上：

```bash
top
vmstat 1
iostat -xz 1
pidstat -d 1
pidstat -d -p <PID> 1
sudo iotop -oPa
```

Kubernetes / Prometheus：

```text
rate(container_fs_reads_bytes_total[1m])
rate(container_fs_writes_bytes_total[1m])
rate(container_fs_io_time_seconds_total[1m])
rate(node_cpu_seconds_total{mode="iowait"}[1m])
container_memory_working_set_bytes
```

## 下一步建议

1. 生产先将 `ANYIO_THREAD_TOKENS` 从 64 提到 128 验证 gap 是否下降。
2. 同步观察 CPU、iowait、磁盘 await、整体接口 P95/P99。

## 已实施

- 给 `get_provider_manager` 增加 `provider_manager_dependency_threadpool_enter`
  和 `provider_manager_dependency_threadpool_wait_ms`。
- 将 `get_provider_manager` 改为 async 依赖；cache hit 热路径直接返回缓存
  `ProviderManager`，cache miss 冷路径再进入 `anyio.to_thread.run_sync(...)`。
- `provider_models_request_done` / `provider_models_request_error` 已输出
  `dependency_threadpool_wait_ms`，方便从总入口日志直接判断是否为 threadpool
  排队。
