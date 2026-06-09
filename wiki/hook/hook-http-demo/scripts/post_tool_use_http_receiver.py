# -*- coding: utf-8 -*-
"""本地 PostToolUse HTTP hook 接收器样例。"""

from __future__ import annotations

import argparse
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

LOGGER = logging.getLogger(__name__)
HOOK_PATH = "/hooks/mcp-posttool"
MAX_SUMMARY_LENGTH = 300


def _summarize_tool_response(tool_response: Any) -> str:
    """提取工具返回结果的短摘要，避免把完整输出塞回记忆。"""
    if tool_response is None:
        return "无返回值"
    if isinstance(tool_response, dict):
        content = tool_response.get("content")
        if content:
            return str(content)[:MAX_SUMMARY_LENGTH]
    return str(tool_response)[:MAX_SUMMARY_LENGTH]


def _build_additional_context(payload: dict[str, Any]) -> list[str]:
    """根据 hook payload 生成额外上下文。"""
    tool_name = str(payload.get("tool_name") or "")
    tool_use_id = str(payload.get("tool_use_id") or "")
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response")

    return [
        f"已收到 PostToolUse hook，工具名: {tool_name or 'unknown'}。",
        f"tool_use_id: {tool_use_id or 'unknown'}。",
        f"tool_input 摘要: {json.dumps(tool_input, ensure_ascii=False)[:MAX_SUMMARY_LENGTH]}",
        f"tool_response 摘要: {_summarize_tool_response(tool_response)}",
    ]


def _build_hook_output(payload: dict[str, Any]) -> dict[str, Any]:
    """构造符合 hook runtime 约定的 JSON 返回值。"""
    return {
        "hookSpecificOutput": {
            "additionalContext": _build_additional_context(payload),
        },
    }


class PostToolUseHookHandler(BaseHTTPRequestHandler):
    """处理本地 hook 请求。"""

    server_version = "HookHttpDemo/1.0"

    def do_POST(self) -> None:  # noqa: N802
        """处理 hook runtime 发来的 POST 请求。"""
        if self.path != HOOK_PATH:
            self.send_error(HTTPStatus.NOT_FOUND, "unknown hook path")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "invalid json body")
            return

        response = _build_hook_output(payload)
        response_body = json.dumps(response, ensure_ascii=False).encode(
            "utf-8",
        )

        LOGGER.info(
            "收到 hook 请求: event=%s tool=%s",
            payload.get("hook_event_name"),
            payload.get("tool_name"),
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, format: str, *args: Any) -> None:
        """把 BaseHTTPRequestHandler 的访问日志转到标准 logging。"""
        LOGGER.info("%s - %s", self.address_string(), format % args)


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="启动本地 PostToolUse HTTP hook 接收器样例",
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=9000, help="监听端口")
    return parser.parse_args()


def main() -> int:
    """启动 HTTP 服务。"""
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    server = ThreadingHTTPServer(
        (args.host, args.port),
        PostToolUseHookHandler,
    )
    LOGGER.info(
        "启动 hook 接收器: http://%s:%s%s",
        args.host,
        args.port,
        HOOK_PATH,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("收到中断信号，准备退出")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
