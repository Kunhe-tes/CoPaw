# -*- coding: utf-8 -*-
"""运行时静态文件 gzip 压缩中间件。"""

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

_RUNTIME_STATIC_PREFIX = "/static/"
_HTML_SUFFIXES = (".html", ".htm")


def is_runtime_static_html_path(path: str) -> bool:
    """判断路径是否匹配运行时静态 HTML 文件。"""
    if not path.startswith(_RUNTIME_STATIC_PREFIX):
        return False

    parts = path[len(_RUNTIME_STATIC_PREFIX) :].split("/", 2)
    if len(parts) != 3 or not all(parts):
        return False

    file_name = parts[2].lower()
    return file_name.endswith(_HTML_SUFFIXES)


def _disable_pathsend(scope: Scope) -> Scope:
    """移除零拷贝文件发送扩展，保证 gzip 能处理文件响应体。"""
    extensions = scope.get("extensions")
    if not isinstance(extensions, dict):
        return scope
    if "http.response.pathsend" not in extensions:
        return scope

    gzip_scope = dict(scope)
    gzip_extensions = dict(extensions)
    gzip_extensions.pop("http.response.pathsend", None)
    gzip_scope["extensions"] = gzip_extensions
    return gzip_scope


class RuntimeStaticGZipMiddleware:
    """仅对运行时静态 HTML 文件启用 gzip 压缩。"""

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 500,
        compresslevel: int = 6,
    ) -> None:
        self.app = app
        self.gzip_app = GZipMiddleware(
            app,
            minimum_size=minimum_size,
            compresslevel=compresslevel,
        )

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http" or not is_runtime_static_html_path(
            scope.get("path", ""),
        ):
            await self.app(scope, receive, send)
            return

        await self.gzip_app(_disable_pathsend(scope), receive, send)
