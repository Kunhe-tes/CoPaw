# 多租户隔离设计规范

**日期：** 2026-04-01
**状态：** 草稿
**范围：** CoPaw 多租户部署的用户隔离与权限控制

---

## 1. 概述

本文档详细规定了在 CoPaw 中实现多租户隔离的完整设计方案，使多个独立用户/组织能够共享单个 CoPaw 实例，同时保持完整的数据和运行时隔离。

### 1.1 关键需求

- **租户识别：** 通过 `X-Tenant-Id` HTTP 请求头
- **完整数据隔离：** 每个租户拥有独立的工作目录
- **运行时隔离：** 每个租户运行在独立的 Workspace 实例中
- **资源管理：** 可按租户配置限制（并发数、存储空间等）
- **安全性：** 租户访问控制和跨租户泄露防护

---

## 2. 架构设计

### 2.1 高层架构

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI 应用层                          │
├─────────────────────────────────────────────────────────────┤
│  中间件层                                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. 租户安全中间件 (TenantSecurityMiddleware)         │   │
│  │    - 验证 X-Tenant-Id 格式                          │   │
│  │    - 检查租户白名单/黑名单                          │   │
│  │    - 设置 contextvars.current_tenant_id             │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 2. 租户上下文中间件 (TenantContextMiddleware)        │   │
│  │    - 设置 contextvars.current_user_id               │   │
│  │    - 初始化/请求租户工作空间                        │   │
│  │    - 按租户限流                                     │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  路由层                                                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │   Console   │ │    Cron     │ │      Settings       │   │
│  │   路由      │ │    路由     │ │      路由           │   │
│  └──────┬──────┘ └──────┬──────┘ └──────────┬──────────┘   │
│         │               │                   │              │
│         └───────────────┼───────────────────┘              │
│                         │                                   │
├─────────────────────────┼───────────────────────────────────┤
│                         ▼                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              TenantWorkspacePool                     │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │  tenant-1: Workspace (agent_id, runtime)    │   │   │
│  │  │  tenant-2: Workspace (agent_id, runtime)    │   │   │
│  │  │  tenant-3: Workspace (agent_id, runtime)    │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  │  - 懒加载 / 自动驱逐                                │   │
│  │  - 资源限制强制执行                                 │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
请求 → 安全检查 → 上下文设置 → 获取 Workspace → 处理 → 响应
              ↓              ↓              ↓
         验证ID         设置上下文      不存在则懒加载
         检查ACL        tenant/user
```

---

## 3. 核心组件

### 3.1 上下文变量

**文件：** `src/copaw/config/context.py`

```python
from contextvars import ContextVar
from typing import Optional

# 已有变量（保留）
current_workspace_dir: ContextVar[Path | None] = ContextVar(...)
current_recent_max_bytes: ContextVar[int | None] = ContextVar(...)

# 新增：租户识别
current_tenant_id: ContextVar[str | None] = ContextVar(
    "current_tenant_id",
    default=None,
)

# 新增：租户内用户识别
current_user_id: ContextVar[str | None] = ContextVar(
    "current_user_id",
    default=None,
)

# 新增：租户工作空间引用（快速访问）
current_tenant_workspace: ContextVar["Workspace" | None] = ContextVar(
    "current_tenant_workspace",
    default=None,
)


# 访问函数
def get_current_tenant_id() -> str:
    """获取当前租户 ID，默认为 'default'。"""
    return current_tenant_id.get() or "default"


def get_current_user_id() -> str:
    """获取当前用户 ID，默认为 'anonymous'。"""
    return current_user_id.get() or "anonymous"


def get_current_tenant_workspace() -> Optional["Workspace"]:
    """获取当前租户的工作空间实例。"""
    return current_tenant_workspace.get()
```

### 3.2 租户工作空间池

**文件：** `src/copaw/app/workspace/tenant_pool.py`

```python
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Set

from .workspace import Workspace
from ...config.context import (
    current_tenant_workspace,
    current_tenant_id,
)

logger = logging.getLogger(__name__)


class TenantWorkspacePool:
    """管理租户工作空间生命周期与资源限制。

    特性：
    - 懒加载（首次访问时创建）
    - LRU 驱逐（容量满时移除最近最少使用）
    - 空闲超时（自动清理不活跃工作空间）
    - 资源追踪（每租户内存、连接数）
    """

    def __init__(
        self,
        base_working_dir: Path,
        max_tenants: int = 100,
        max_concurrent_per_tenant: int = 10,
        idle_timeout: timedelta = timedelta(hours=1),
    ):
        self._base = base_working_dir
        self._max_tenants = max_tenants
        self._max_concurrent = max_concurrent_per_tenant
        self._idle_timeout = idle_timeout

        # 活跃工作空间
        self._workspaces: Dict[str, Workspace] = {}
        self._last_access: Dict[str, datetime] = {}
        self._semaphores: Dict[str, asyncio.Semaphore] = {}

        # 同步
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown = False

    async def start(self) -> None:
        """启动后台清理任务。"""
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop()
        )
        logger.info(
            f"TenantWorkspacePool 已启动: "
            f"max_tenants={self._max_tenants}, "
            f"idle_timeout={self._idle_timeout}"
        )

    async def stop(self) -> None:
        """停止所有工作空间并清理。"""
        self._shutdown = True

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            # 停止所有工作空间
            stop_tasks = [
                ws.stop() for ws in self._workspaces.values()
            ]
            if stop_tasks:
                await asyncio.gather(*stop_tasks, return_exceptions=True)

            self._workspaces.clear()
            self._last_access.clear()
            self._semaphores.clear()

        logger.info("TenantWorkspacePool 已停止")

    async def get_or_create(
        self,
        tenant_id: str,
        agent_id: Optional[str] = None,
    ) -> Workspace:
        """获取或创建租户的工作空间。

        Args:
            tenant_id: 唯一租户标识符
            agent_id: 可选代理 ID（默认为 tenant_id）

        Returns:
            租户的工作空间实例

        Raises:
            TenantLimitExceeded: 达到最大租户数且无法驱逐
            TenantBlocked: 租户在黑名单中
        """
        if self._shutdown:
            raise RuntimeError("池正在关闭中")

        async with self._lock:
            # 检查是否已存在
            if tenant_id in self._workspaces:
                self._last_access[tenant_id] = datetime.now()
                return self._workspaces[tenant_id]

            # 检查容量
            if len(self._workspaces) >= self._max_tenants:
                await self._evict_lru_tenant()

            # 创建工作空间
            workspace_dir = self._get_tenant_dir(tenant_id)
            workspace_dir.mkdir(parents=True, exist_ok=True)

            # 初始化租户结构（如果是新的）
            await self._init_tenant_structure(workspace_dir)

            # 创建并启动工作空间
            actual_agent_id = agent_id or tenant_id
            workspace = Workspace(
                agent_id=actual_agent_id,
                workspace_dir=str(workspace_dir),
            )
            await workspace.start()

            self._workspaces[tenant_id] = workspace
            self._last_access[tenant_id] = datetime.now()
            self._semaphores[tenant_id] = asyncio.Semaphore(
                self._max_concurrent
            )

            logger.info(
                f"为租户创建工作空间: {tenant_id} "
                f"路径: {workspace_dir}"
            )
            return workspace

    async def get_semaphore(self, tenant_id: str) -> asyncio.Semaphore:
        """获取租户的并发信号量。"""
        async with self._lock:
            if tenant_id not in self._semaphores:
                self._semaphores[tenant_id] = asyncio.Semaphore(
                    self._max_concurrent
                )
            return self._semaphores[tenant_id]

    async def get_workspace(self, tenant_id: str) -> Optional[Workspace]:
        """获取工作空间（如果存在，不创建）。"""
        async with self._lock:
            return self._workspaces.get(tenant_id)

    async def remove_tenant(self, tenant_id: str) -> bool:
        """移除并停止租户的工作空间。"""
        async with self._lock:
            if tenant_id not in self._workspaces:
                return False

            workspace = self._workspaces.pop(tenant_id)
            self._last_access.pop(tenant_id, None)
            self._semaphores.pop(tenant_id, None)

        # 在锁外停止
        await workspace.stop()
        logger.info(f"已移除租户工作空间: {tenant_id}")
        return True

    def _get_tenant_dir(self, tenant_id: str) -> Path:
        """获取租户工作目录。"""
        if tenant_id == "default":
            return self._base / "default"
        # 清理 tenant_id 以适配文件系统
        safe_id = "".join(
            c for c in tenant_id
            if c.isalnum() or c in "_-"
        )
        return self._base / f"tenant-{safe_id}"

    async def _init_tenant_structure(self, tenant_dir: Path) -> None:
        """初始化新租户目录结构。"""
        # 核心目录
        (tenant_dir / "skills").mkdir(exist_ok=True)
        (tenant_dir / "customized_skills").mkdir(exist_ok=True)
        (tenant_dir / "memory").mkdir(exist_ok=True)
        (tenant_dir / "media").mkdir(exist_ok=True)
        (tenant_dir / "files").mkdir(exist_ok=True)

        # 配置文件和数据文件将在首次使用时创建

    async def _evict_lru_tenant(self) -> None:
        """容量满时驱逐最近最少使用的租户。"""
        if not self._last_access:
            raise TenantLimitExceeded(
                f"已达最大租户数 ({self._max_tenants})，"
                "没有可驱逐的租户"
            )

        # 找到 LRU 租户
        lru_tenant = min(
            self._last_access.keys(),
            key=lambda k: self._last_access[k]
        )

        # 检查是否空闲足够久
        idle_time = datetime.now() - self._last_access[lru_tenant]
        if idle_time < timedelta(minutes=5):
            raise TenantLimitExceeded(
                f"已达最大租户数 ({self._max_tenants}) "
                f"且所有租户都在活跃状态"
            )

        await self.remove_tenant(lru_tenant)
        logger.info(f"已驱逐空闲租户: {lru_tenant} (空闲={idle_time})")

    async def _cleanup_loop(self) -> None:
        """后台任务：清理空闲工作空间。"""
        while not self._shutdown:
            try:
                await asyncio.sleep(60)  # 每分钟检查

                async with self._lock:
                    now = datetime.now()
                    to_evict = []

                    for tenant_id, last_access in self._last_access.items():
                        if now - last_access > self._idle_timeout:
                            to_evict.append(tenant_id)

                # 在锁外驱逐
                for tenant_id in to_evict:
                    await self.remove_tenant(tenant_id)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("清理循环错误")

    async def get_stats(self) -> dict:
        """获取池统计信息。"""
        async with self._lock:
            return {
                "total_tenants": len(self._workspaces),
                "max_tenants": self._max_tenants,
                "active_semaphores": len(self._semaphores),
                "tenant_ids": list(self._workspaces.keys()),
            }


class TenantLimitExceeded(Exception):
    """达到租户限制时抛出。"""
    pass


class TenantBlocked(Exception):
    """租户被阻止时抛出。"""
    pass
```

---

## 4. 中间件实现

### 4.1 租户安全中间件

**文件：** `src/copaw/app/middleware/tenant_security.py`

```python
import re
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ...config.context import current_tenant_id, current_user_id


class TenantSecurityMiddleware(BaseHTTPMiddleware):
    """验证租户请求头并设置安全上下文。

    顺序：必须在中间件栈早期（路由之前）。
    """

    # 有效租户 ID 模式：字母数字、下划线、连字符
    TENANT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')

    def __init__(
        self,
        app,
        allow_list: Optional[Set[str]] = None,
        block_list: Optional[Set[str]] = None,
    ):
        super().__init__(app)
        self._allow_list = allow_list
        self._block_list = block_list or set()

    async def dispatch(self, request: Request, call_next) -> Response:
        tenant_id = request.headers.get("X-Tenant-Id", "default")
        user_id = request.headers.get("X-User-Id", "anonymous")

        # 验证租户 ID 格式
        if not self._validate_tenant_id(tenant_id):
            return Response(
                status_code=400,
                content=json.dumps({
                    "error": "无效的租户 ID 格式",
                    "detail": "必须是 1-64 位字母数字、下划线或连字符"
                }),
                media_type="application/json"
            )

        # 检查黑名单/白名单
        if tenant_id in self._block_list:
            return Response(
                status_code=403,
                content=json.dumps({
                    "error": "租户访问被拒绝",
                    "detail": f"租户 '{tenant_id}' 已被阻止"
                }),
                media_type="application/json"
            )

        if self._allow_list and tenant_id not in self._allow_list:
            return Response(
                status_code=403,
                content=json.dumps({
                    "error": "租户未授权",
                    "detail": f"租户 '{tenant_id}' 不在白名单中"
                }),
                media_type="application/json"
            )

        # 为本次请求设置上下文
        tenant_token = current_tenant_id.set(tenant_id)
        user_token = current_user_id.set(user_id)

        try:
            response = await call_next(request)
            # 添加租户信息到响应头（调试用）
            response.headers["X-Tenant-Id-Processed"] = tenant_id
            return response
        finally:
            current_tenant_id.reset(tenant_token)
            current_user_id.reset(user_token)

    def _validate_tenant_id(self, tenant_id: str) -> bool:
        """验证租户 ID 格式。"""
        if not tenant_id:
            return False
        return bool(self.TENANT_ID_PATTERN.match(tenant_id))
```

### 4.2 租户上下文中间件

**文件：** `src/copaw/app/middleware/tenant_context.py`

```python
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ...config.context import (
    current_tenant_workspace,
    get_current_tenant_id,
)
from ..workspace.tenant_pool import TenantWorkspacePool


class TenantContextMiddleware(BaseHTTPMiddleware):
    """设置租户工作空间并管理请求级上下文。

    必须在 TenantSecurityMiddleware 之后运行。
    """

    def __init__(self, app, tenant_pool: TenantWorkspacePool):
        super().__init__(app)
        self._pool = tenant_pool

    async def dispatch(self, request: Request, call_next) -> Response:
        tenant_id = get_current_tenant_id()

        # 获取或创建工作空间（可能抛出 TenantLimitExceeded）
        try:
            workspace = await self._pool.get_or_create(tenant_id)
        except TenantLimitExceeded as e:
            return Response(
                status_code=503,
                content=json.dumps({
                    "error": "服务过载",
                    "detail": str(e)
                }),
                media_type="application/json"
            )

        # 将工作空间设置到上下文以便快速访问
        workspace_token = current_tenant_workspace.set(workspace)
        request.state.workspace = workspace

        # 获取信号量用于并发控制
        semaphore = await self._pool.get_semaphore(tenant_id)

        try:
            # 限制每租户并发请求
            async with semaphore:
                response = await call_next(request)
                return response
        finally:
            current_tenant_workspace.reset(workspace_token)
```

---

## 5. 路由适配

### 5.1 Console 路由

**文件：** `src/copaw/app/routers/console.py`

```python
@router.post("/chat")
async def post_console_chat(
    request_data: Union[AgentRequest, dict],
    request: Request,
) -> StreamingResponse:
    """支持租户隔离的流式响应。"""

    # 从上下文获取工作空间（由中间件设置）
    workspace = request.state.workspace

    # 从上下文获取租户/用户信息
    tenant_id = get_current_tenant_id()
    user_id = get_current_user_id()

    console_channel = await workspace.channel_manager.get_channel("console")
    if console_channel is None:
        raise HTTPException(
            status_code=503,
            detail="未找到 Console 渠道",
        )

    # 构建带租户上下文的 payload
    native_payload = _extract_session_and_payload(request_data)

    # 会话 ID 包含租户信息以实现隔离
    session_id = f"console:{tenant_id}:{user_id}:{uuid.uuid4().hex[:8]}"

    # 创建租户范围内的聊天
    chat = await workspace.chat_manager.get_or_create_chat(
        session_id=session_id,
        user_id=user_id,
        channel_id="console",
        name=f"Chat-{tenant_id}-{user_id[:8]}",
    )

    # ... 其余实现
```

### 5.2 Cron 路由

**文件：** `src/copaw/app/routers/cron.py`

```python
@router.get("/crons")
async def list_cron_jobs(request: Request) -> list[CronJobView]:
    """仅列出当前租户的任务。"""
    workspace = request.state.workspace

    # CronManager 通过 Workspace 实现租户范围
    jobs = await workspace.cron_manager.list_jobs()

    # 添加状态信息
    views = []
    for job in jobs:
        state = workspace.cron_manager.get_state(job.id)
        views.append(CronJobView(spec=job, state=state))

    return views


@router.post("/crons")
async def create_cron_job(
    request: Request,
    spec: CronJobSpec,
) -> dict:
    """为当前租户创建定时任务。"""
    workspace = request.state.workspace
    tenant_id = get_current_tenant_id()

    # 确保任务标记租户信息
    spec.meta["tenant_id"] = tenant_id

    await workspace.cron_manager.create_or_replace_job(spec)
    return {"id": spec.id, "status": "created"}
```

---

## 6. 租户感知组件

### 6.1 Token 使用管理器

**文件：** `src/copaw/token_usage/tenant_manager.py`

```python
from pathlib import Path
from typing import Dict, Optional
import asyncio

from .manager import TokenManager


class TenantTokenManager:
    """按租户隔离的 Token 使用追踪管理器。"""

    def __init__(self, base_dir: Path):
        self._base = base_dir
        self._managers: Dict[str, TokenManager] = {}
        self._lock = asyncio.Lock()

    async def get_manager(self, tenant_id: str) -> TokenManager:
        """获取或创建租户的 Token 管理器。"""
        async with self._lock:
            if tenant_id not in self._managers:
                tenant_dir = self._base / f"tenant-{tenant_id}"
                tenant_dir.mkdir(parents=True, exist_ok=True)

                self._managers[tenant_id] = TokenManager(
                    storage_dir=tenant_dir
                )
            return self._managers[tenant_id]

    async def record_usage(
        self,
        tenant_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """记录租户的 Token 使用。"""
        manager = await self.get_manager(tenant_id)
        await manager.record_usage(model, input_tokens, output_tokens)

    async def get_usage_stats(
        self,
        tenant_id: str,
        period: str = "day",
    ) -> dict:
        """获取租户的 Token 使用统计。"""
        manager = await self.get_manager(tenant_id)
        return await manager.get_stats(period)

    async def check_quota(self, tenant_id: str) -> bool:
        """检查租户是否超出配额。"""
        # TODO: 实现配额检查
        stats = await self.get_usage_stats(tenant_id)
        # 与租户特定限制比较
        return True
```

### 6.2 工具 Guard 配置

**文件：** `src/copaw/security/tenant_tool_guard.py`

```python
from pathlib import Path
from typing import Dict, Optional, Any
import yaml

from .tool_guard import ToolGuard


class TenantToolGuard:
    """支持自定义策略的租户专用工具 Guard。"""

    def __init__(self, base_config_dir: Path):
        self._base = base_config_dir
        self._guards: Dict[str, ToolGuard] = {}

    def get_guard(self, tenant_id: str) -> ToolGuard:
        """获取或加载租户的工具 Guard。"""
        if tenant_id not in self._guards:
            config_path = self._get_tenant_config_path(tenant_id)

            if config_path.exists():
                config = yaml.safe_load(config_path.read_text())
            else:
                # 使用默认配置
                config = self._load_default_config()

            self._guards[tenant_id] = ToolGuard(config)

        return self._guards[tenant_id]

    def _get_tenant_config_path(self, tenant_id: str) -> Path:
        tenant_dir = self._base / f"tenant-{tenant_id}"
        return tenant_dir / "tool_guard.yaml"

    def _load_default_config(self) -> dict:
        """加载默认工具 Guard 配置。"""
        default_path = self._base / "default" / "tool_guard.yaml"
        if default_path.exists():
            return yaml.safe_load(default_path.read_text())
        return {}

    async def check_tool_execution(
        self,
        tenant_id: str,
        tool_name: str,
        params: dict,
    ) -> ToolGuardResult:
        """检查租户是否允许执行工具。"""
        guard = self.get_guard(tenant_id)
        return await guard.check(tool_name, params)
```

### 6.3 截图存储隔离

**文件：** `src/copaw/agents/tools/desktop_screenshot.py`

```python
from ...config.context import get_current_tenant_id
from ...constant import get_tenant_working_dir


def get_screenshot_storage_path() -> Path:
    """获取租户隔离的截图存储路径。"""
    tenant_id = get_current_tenant_id()
    tenant_dir = get_tenant_working_dir(tenant_id)
    screenshot_dir = tenant_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    return screenshot_dir


async def desktop_screenshot() -> ToolResponse:
    """支持租户隔离的截图捕获。"""
    # ... 截图逻辑 ...

    # 存储到租户专用目录
    storage_dir = get_screenshot_storage_path()
    filename = f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
    filepath = storage_dir / filename

    # ... 保存截图 ...
```

---

## 7. 目录结构

### 7.1 租户目录布局

```
~/.copaw/  # 或 COPAW_WORKING_DIR
├── default/                          # 默认租户（向后兼容）
│   ├── config.yaml
│   ├── config.json
│   ├── skills/
│   ├── customized_skills/
│   ├── memory/
│   ├── media/
│   ├── files/
│   ├── screenshots/
│   ├── jobs.json
│   ├── chats.json
│   ├── token_usage.json
│   └── tool_guard.yaml
├── tenant-acme-corp/                 # 租户: acme-corp
│   ├── config.yaml
│   ├── config.json
│   ├── skills/
│   ├── customized_skills/
│   ├── memory/
│   ├── media/
│   ├── files/
│   ├── screenshots/
│   ├── jobs.json
│   ├── chats.json
│   ├── token_usage.json
│   └── tool_guard.yaml
└── tenant-startup-inc/               # 租户: startup-inc
    └── ... (相同结构)
```

### 7.2 租户感知路径工具

**文件：** `src/copaw/config/tenant_paths.py`

```python
from pathlib import Path
from .constant import WORKING_DIR
from .context import get_current_tenant_id


def get_tenant_working_dir(tenant_id: Optional[str] = None) -> Path:
    """获取租户工作目录。

    Args:
        tenant_id: 租户 ID（默认为当前上下文）

    Returns:
        租户工作目录路径
    """
    if tenant_id is None:
        tenant_id = get_current_tenant_id()

    if tenant_id == "default":
        return WORKING_DIR / "default"

    # 文件系统安全清理
    safe_id = "".join(
        c for c in tenant_id
        if c.isalnum() or c in "_-"
    )
    return WORKING_DIR / f"tenant-{safe_id}"


def get_tenant_config_path(tenant_id: Optional[str] = None) -> Path:
    """获取租户配置文件路径。"""
    return get_tenant_working_dir(tenant_id) / "config.yaml"


def get_tenant_memory_dir(tenant_id: Optional[str] = None) -> Path:
    """获取租户记忆目录。"""
    return get_tenant_working_dir(tenant_id) / "memory"


def get_tenant_media_dir(tenant_id: Optional[str] = None) -> Path:
    """获取租户媒体目录。"""
    return get_tenant_working_dir(tenant_id) / "media"


def get_tenant_jobs_path(tenant_id: Optional[str] = None) -> Path:
    """获取租户定时任务文件路径。"""
    return get_tenant_working_dir(tenant_id) / "jobs.json"
```

---

## 8. 迁移策略

### 8.1 向后兼容性

现有单租户部署应继续工作：

```python
# src/copaw/config/context.py

def get_current_tenant_id() -> str:
    """获取当前租户 ID，支持向后兼容。

    如果不在多租户上下文中，返回 'default'。
    """
    tenant_id = current_tenant_id.get()
    if tenant_id is None:
        # 不在多租户上下文，使用传统行为
        return "default"
    return tenant_id
```

### 8.2 数据迁移

```python
# 迁移脚本
async def migrate_existing_to_tenant():
    """将现有默认数据迁移到 tenant-default 结构。"""
    source = WORKING_DIR  # 传统扁平结构
    target = WORKING_DIR / "default"  # 新租户结构

    if target.exists():
        return  # 已迁移

    target.mkdir(parents=True, exist_ok=True)

    # 移动现有文件
    for item in source.iterdir():
        if item.name.startswith("tenant-"):
            continue  # 跳过已有租户目录
        if item.name == "default":
            continue  # 跳过目标本身

        shutil.move(str(item), str(target / item.name))
```

---

## 9. 安全考虑

### 9.1 租户隔离强制执行

| 层级 | 执行机制 |
|------|----------|
| 文件系统 | 通过 `get_tenant_working_dir()` 解析路径 |
| 内存 | 每租户独立的 Workspace 实例 |
| 网络 | N/A（共享 HTTP 服务器） |
| 数据库 | 每租户独立的 JSON 文件 |
| 进程 | 同一进程，基于上下文隔离 |

### 9.2 跨租户攻击防护

1. **路径遍历：** 清理 tenant_id，验证解析后的路径
2. **资源耗尽：** 每租户信号量和限制
3. **信息泄露：** 请求间清理上下文
4. **权限提升：** 无租户可未经授权访问 "default"

---

## 10. 性能考虑

### 10.1 资源开销

| 指标 | 单租户 | 多租户 |
|------|--------|--------|
| 内存 | 1x | ~1.5-2x（工作空间池） |
| 启动 | 快 | 较慢（懒加载） |
| 每请求 | 最小 | +上下文切换 |
| 存储 | 1x | Nx（每租户） |

### 10.2 优化策略

1. **工作空间池：** 使用 LRU 驱逐复用工作空间实例
2. **懒加载：** 仅在首次访问租户时创建工作空间
3. **连接池：** 在安全的场景下共享数据库连接
4. **缓存：** 带 TTL 的租户范围缓存

---

## 11. 测试策略

### 11.1 单元测试

```python
# tests/unit/test_tenant_isolation.py

async def test_tenant_workspace_isolation():
    """验证工作空间正确隔离。"""
    pool = TenantWorkspacePool(base_dir=tmp_path)
    await pool.start()

    ws1 = await pool.get_or_create("tenant-1")
    ws2 = await pool.get_or_create("tenant-2")

    # 应为不同实例
    assert ws1 is not ws2

    # 工作目录应不同
    assert ws1.workspace_dir != ws2.workspace_dir

    await pool.stop()


async def test_tenant_context_propagation():
    """验证上下文变量正确传递。"""
    token = current_tenant_id.set("test-tenant")

    try:
        # 模拟异步调用
        async def inner():
            return get_current_tenant_id()

        result = await inner()
        assert result == "test-tenant"
    finally:
        current_tenant_id.reset(token)
```

### 11.2 集成测试

```python
# tests/integrated/test_tenant_api.py

async def test_tenant_api_isolation(client):
    """测试 API 调用遵守租户边界。"""

    # 以 tenant-1 创建文件
    response = await client.post(
        "/api/files",
        headers={"X-Tenant-Id": "tenant-1"},
        data={"content": "secret"}
    )
    file_id = response.json()["id"]

    # 尝试以 tenant-2 访问
    response = await client.get(
        f"/api/files/{file_id}",
        headers={"X-Tenant-Id": "tenant-2"}
    )
    assert response.status_code == 404
```

---

## 12. 部署配置

### 12.1 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `COPAW_MULTI_TENANT` | 启用多租户模式 | `false` |
| `COPAW_MAX_TENANTS` | 最大并发租户数 | `100` |
| `COPAW_TENANT_IDLE_TIMEOUT` | 驱逐前空闲分钟数 | `60` |
| `COPAW_MAX_CONCURRENT_PER_TENANT` | 每租户最大并发请求 | `10` |

### 12.2 特性开关

```python
# src/copaw/config/constant.py

MULTI_TENANT_ENABLED = EnvVarLoader.get_bool(
    "COPAW_MULTI_TENANT",
    False
)
```

---

## 13. 总结

本设计通过以下方式提供全面的多租户隔离：

1. **工作空间池模式：** 每租户获得独立的工作空间实例
2. **基于上下文的路由：** `contextvars` 传递租户身份
3. **路径隔离：** 所有文件操作使用租户范围的目录
4. **资源管理：** 每租户限制配合 LRU 驱逐
5. **向后兼容：** 现有部署无需更改即可工作

设计在隔离强度与资源效率之间取得平衡，使 CoPaw 能够从单一实例服务多个用户，同时保持安全边界。
