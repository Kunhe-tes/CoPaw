# -*- coding: utf-8 -*-
"""Tenant context binding utilities for HTTP, cron, and channel callbacks.

This module provides shared helpers and context managers for binding
tenant/workspace context in various entry points (HTTP requests,
cron jobs, channel callbacks).
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

try:
    import swe.config.context as _config_context
except (ImportError, ModuleNotFoundError):
    _config_context = None

if _config_context is not None:
    TenantContextError = _config_context.TenantContextError
else:

    def _build_fallback_tenant_context_error() -> type[RuntimeError]:
        class _FallbackTenantContextError(RuntimeError):
            """Fallback error used when config.context is stubbed in tests."""

        return _FallbackTenantContextError

    TenantContextError = _build_fallback_tenant_context_error()


@contextmanager
def bind_tenant_context(
    tenant_id: str | None = None,
    user_id: str | None = None,
    workspace_dir: Path | None = None,
    source_id: str | None = None,
    scope_id: str | None = None,
) -> Generator[None, None, None]:
    """Bind tenant context for the duration of the context manager.

    This is the primary entry point for non-HTTP code paths (cron jobs,
    background tasks, channel callbacks) to establish tenant context.

    Args:
        tenant_id: The tenant ID to bind. Required for tenant-scoped operations.
        user_id: The user ID to bind. Optional.
        workspace_dir: The workspace directory to bind. Required for
            file operations.
        source_id: The source ID to bind for source-scoped runtime state.
        scope_id: The runtime scope ID to bind. If omitted, it is derived
            from tenant_id/source_id when both are available.

    Yields:
        None

    Example:
        # In a cron job executor
        with bind_tenant_context(
            tenant_id=job.tenant_id,
            user_id=job.user_id,
            workspace_dir=workspace.path,
        ):
            result = execute_job(job)
    """
    from swe.config.context import (
        canonicalize_scope_id,
        resolve_scope_id,
        set_current_tenant_id,
        set_current_user_id,
        set_current_source_id,
        set_current_scope_id,
        set_current_workspace_dir,
        reset_current_tenant_id,
        reset_current_user_id,
        reset_current_source_id,
        reset_current_scope_id,
        reset_current_workspace_dir,
    )

    tokens = []
    resolved_scope_id = (
        canonicalize_scope_id(scope_id)
        if scope_id is not None
        else (
            None
            if tenant_id == "default" and source_id is not None
            else resolve_scope_id(tenant_id, source_id)
        )
    )
    try:
        if tenant_id is not None:
            tokens.append(("tenant", set_current_tenant_id(tenant_id)))
        if user_id is not None:
            tokens.append(("user", set_current_user_id(user_id)))
        if source_id is not None:
            tokens.append(("source", set_current_source_id(source_id)))
        if resolved_scope_id is not None:
            tokens.append(("scope", set_current_scope_id(resolved_scope_id)))
        if workspace_dir is not None:
            tokens.append(
                ("workspace", set_current_workspace_dir(workspace_dir)),
            )
        yield
    finally:
        # Reset in reverse order to restore state correctly
        for name, token in reversed(tokens):
            if name == "tenant":
                reset_current_tenant_id(token)
            elif name == "user":
                reset_current_user_id(token)
            elif name == "source":
                reset_current_source_id(token)
            elif name == "scope":
                reset_current_scope_id(token)
            elif name == "workspace":
                reset_current_workspace_dir(token)


def get_tenant_context() -> dict:
    """Get the current tenant context as a dictionary.

    Returns:
        Dictionary containing tenant/source/user/workspace context values.
    """
    from swe.config.context import (
        get_current_scope_id,
        get_current_source_id,
        get_current_tenant_id,
        get_current_user_id,
        get_current_workspace_dir,
    )

    return {
        "tenant_id": get_current_tenant_id(),
        "user_id": get_current_user_id(),
        "source_id": get_current_source_id(),
        "scope_id": get_current_scope_id(),
        "workspace_dir": get_current_workspace_dir(),
    }


def require_tenant_context() -> tuple[str, Path]:
    """Require that tenant context is set, returning tenant_id and workspace_dir.

    Returns:
        Tuple of (tenant_id, workspace_dir).

    Raises:
        TenantContextError: If tenant_id or workspace_dir is not set.
    """
    from swe.config.context import (
        get_current_tenant_id_strict,
        get_current_workspace_dir_strict,
    )

    tenant_id = get_current_tenant_id_strict()
    workspace_dir = get_current_workspace_dir_strict()
    return tenant_id, workspace_dir


def require_full_context() -> tuple[str, str, Path]:
    """Require that full tenant context is set, returning all three values.

    Returns:
        Tuple of (tenant_id, user_id, workspace_dir).

    Raises:
        TenantContextError: If any of tenant_id, user_id, or workspace_dir
            is not set.
    """
    from swe.config.context import (
        get_current_tenant_id_strict,
        get_current_user_id_strict,
        get_current_workspace_dir_strict,
    )

    tenant_id = get_current_tenant_id_strict()
    user_id = get_current_user_id_strict()
    workspace_dir = get_current_workspace_dir_strict()
    return tenant_id, user_id, workspace_dir


@contextmanager
def bind_request_context(
    request,
) -> Generator[None, None, None]:
    """Bind tenant context from a FastAPI request object.

    Extracts tenant_id and user_id from request headers, and workspace
    from request.state.workspace.

    Args:
        request: The FastAPI request object.

    Yields:
        None

    Example:
        @app.middleware("http")
        async def tenant_middleware(request: Request, call_next):
            with bind_request_context(request):
                return await call_next(request)
    """
    tenant_id = request.headers.get("X-Tenant-Id")
    user_id = request.headers.get("X-User-Id")
    source_id = request.headers.get("X-Source-Id")
    workspace = getattr(request.state, "workspace", None)
    # Support both workspace_dir (standard) and path (legacy) attributes
    if workspace is not None:
        workspace_dir = getattr(workspace, "workspace_dir", None)
        if workspace_dir is None:
            workspace_dir = getattr(workspace, "path", None)
    else:
        workspace_dir = None

    with bind_tenant_context(
        tenant_id=tenant_id,
        user_id=user_id,
        workspace_dir=workspace_dir,
        source_id=source_id,
        scope_id=getattr(request.state, "scope_id", None),
    ):
        yield


__all__ = [
    "bind_tenant_context",
    "get_tenant_context",
    "require_tenant_context",
    "require_full_context",
    "bind_request_context",
    "TenantContextError",
]
