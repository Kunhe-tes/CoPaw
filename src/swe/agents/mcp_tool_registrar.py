# -*- coding: utf-8 -*-
"""MCP discovery and registration isolated from the ReAct loop."""

import asyncio
import logging
from collections.abc import Callable, MutableSequence
from typing import Any

from agentscope.mcp._mcp_function import MCPToolFunction
from anyio import ClosedResourceError

from ..app.mcp import HttpStatefulClient, StdIOStatefulClient
from ..app.mcp.http_headers import build_mcp_http_headers
from ..app.mcp.lazy_client import LazyMCPClient, mcp_tool_json_schema
from ..app.mcp.stdio_launcher import build_tenant_aware_stdio_launch_config

logger = logging.getLogger(__name__)


class McpToolRegistrar:
    """Register stateful and lazy MCP clients without reordering them."""

    def __init__(
        self,
        *,
        toolkit: Any,
        mcp_clients: MutableSequence[Any] | None = None,
        agent_config: Any | None = None,
        source_tool_versions: tuple[Any, ...] = (),
        reset_watchdog: Callable[..., None] | None = None,
        normalize_tool_functions: (
            Callable[[Any, list[str]], None] | None
        ) = None,
        recover_client: Callable[[Any], Any] | None = None,
        should_propagate_cancelled_error: (
            Callable[[BaseException], bool] | None
        ) = None,
    ) -> None:
        self._toolkit = toolkit
        self._mcp_clients = mcp_clients if mcp_clients is not None else []
        self._agent_config = agent_config
        self._source_tool_versions = source_tool_versions
        self._reset_watchdog = reset_watchdog or (
            lambda *_args, **_kwargs: None
        )
        self._normalize_tool_functions = normalize_tool_functions or (
            lambda *_args: None
        )
        self._recover_client = recover_client or self._recover_mcp_client
        self._should_propagate = (
            should_propagate_cancelled_error
            or self._should_propagate_cancelled_error
        )

    @classmethod
    def from_agent(cls, agent: Any) -> "McpToolRegistrar":
        """Adapt the legacy agent state without changing its public API."""
        return cls(
            toolkit=getattr(agent, "toolkit", None),
            mcp_clients=agent._mcp_clients,
            agent_config=agent._agent_config,
            source_tool_versions=agent._source_tool_versions,
            reset_watchdog=agent._reset_watchdog,
            normalize_tool_functions=agent._normalize_registered_tool_functions,
            recover_client=agent._recover_mcp_client,
            should_propagate_cancelled_error=(
                agent._should_propagate_cancelled_error
            ),
        )

    async def register_clients(
        self,
        *,
        namesake_strategy: str = "skip",
    ) -> None:
        index = 0
        while index < len(self._mcp_clients):
            client = self._mcp_clients[index]
            if isinstance(client, LazyMCPClient):
                lazy_clients, index = self._collect_lazy_mcp_clients(index)
                await self._register_lazy_mcp_clients(
                    lazy_clients,
                    namesake_strategy=namesake_strategy,
                )
                continue
            index = await self._register_stateful_mcp_client(
                index,
                namesake_strategy=namesake_strategy,
            )

    async def register_stateful_clients(
        self,
        clients: MutableSequence[Any],
        *,
        namesake_strategy: str = "skip",
    ) -> None:
        """Register clients in sequence; a recoverable failure is skipped."""
        original_clients = self._mcp_clients
        self._mcp_clients = clients
        try:
            index = 0
            while index < len(self._mcp_clients):
                index = await self._register_stateful_mcp_client(
                    index,
                    namesake_strategy=namesake_strategy,
                )
        finally:
            self._mcp_clients = original_clients

    def _source_tool_names(self) -> set[str]:
        configured_tools = getattr(
            getattr(self._agent_config, "tools", None),
            "builtin_tools",
            {},
        )
        return {
            version.name
            for version in self._source_tool_versions
            if configured_tools.get(version.name, None) is None
            or configured_tools[version.name].enabled
        }

    def _collect_lazy_mcp_clients(
        self,
        start_index: int,
    ) -> tuple[list[LazyMCPClient], int]:
        clients: list[LazyMCPClient] = []
        index = start_index
        while index < len(self._mcp_clients) and isinstance(
            self._mcp_clients[index],
            LazyMCPClient,
        ):
            clients.append(self._mcp_clients[index])
            index += 1
        return clients, index

    async def _register_stateful_mcp_client(
        self,
        client_index: int,
        *,
        namesake_strategy: str,
    ) -> int:
        client = self._mcp_clients[client_index]
        client_name = getattr(client, "name", repr(client))
        collisions: list[str] = []
        try:
            client_tools = await client.list_tools()
            if hasattr(client_tools, "tools"):
                client_tools = client_tools.tools
            collisions = sorted(
                self._source_tool_names()
                & {str(getattr(tool, "name", "")) for tool in client_tools},
            )
            if not collisions:
                self._register_progress_callback(client)
                await self._register_stateful_client(
                    client,
                    namesake_strategy=namesake_strategy,
                )
        except (ClosedResourceError, asyncio.CancelledError) as error:
            if self._should_propagate(error):
                raise
            logger.warning(
                "MCP client '%s' session interrupted while listing tools; trying recovery",
                client_name,
            )
            recovered_client = await self._recover_client(client)
            if recovered_client is not None:
                self._mcp_clients[client_index] = recovered_client
                self._register_progress_callback(recovered_client)
                try:
                    await self._register_stateful_client(
                        recovered_client,
                        namesake_strategy=namesake_strategy,
                    )
                    return client_index + 1
                except asyncio.CancelledError as recover_error:
                    if self._should_propagate(recover_error):
                        raise
                    logger.warning(
                        "MCP client '%s' registration cancelled after recovery, skipping",
                        client_name,
                    )
                except (
                    Exception
                ) as recover_error:  # pylint: disable=broad-except
                    logger.warning(
                        "MCP client '%s' still unavailable after recovery, skipping: %s",
                        client_name,
                        recover_error,
                    )
            else:
                logger.warning(
                    "MCP client '%s' recovery failed, skipping",
                    client_name,
                )
        except Exception as error:  # pylint: disable=broad-except
            logger.warning(
                "Failed to register MCP client '%s', skipping: %s",
                client_name,
                error,
                exc_info=True,
            )
        if collisions:
            raise RuntimeError(
                "MCP tool collides with an active source tool: "
                + ", ".join(collisions),
            )
        return client_index + 1

    def _register_progress_callback(self, client: Any) -> None:
        if hasattr(client, "on_progress_callback"):
            client.on_progress_callback = self._reset_watchdog

    async def _register_stateful_client(
        self,
        client: Any,
        *,
        namesake_strategy: str,
    ) -> None:
        existing_tool_names = set(getattr(self._toolkit, "tools", {}))
        await self._toolkit.register_mcp_client(
            client,
            namesake_strategy=namesake_strategy,
        )
        self._wire_mcp_progress_callbacks(client)
        self._normalize_tool_functions(
            self._toolkit,
            sorted(
                set(getattr(self._toolkit, "tools", {})) - existing_tool_names,
            ),
        )

    async def _register_lazy_mcp_clients(
        self,
        clients: list[LazyMCPClient],
        *,
        namesake_strategy: str,
    ) -> None:
        discovered_tools = await asyncio.gather(
            *(
                self._discover_lazy_mcp_client_tools(client)
                for client in clients
            ),
        )
        for client, client_tools in zip(clients, discovered_tools):
            if client_tools is not None:
                await self._register_lazy_mcp_client(
                    client,
                    namesake_strategy=namesake_strategy,
                    client_tools=client_tools,
                )

    async def _discover_lazy_mcp_client_tools(
        self,
        client: LazyMCPClient,
    ) -> list[Any] | None:
        try:
            return await client.list_tools()
        except asyncio.CancelledError as error:
            if self._should_propagate(error):
                raise
            logger.warning(
                "Lazy MCP client '%s' discovery cancelled, skipping",
                client.name,
            )
        except Exception as error:  # pylint: disable=broad-except
            logger.warning(
                "Failed to discover lazy MCP client '%s', skipping: %s",
                client.name,
                error,
                exc_info=True,
            )
        return None

    async def _register_lazy_mcp_client(
        self,
        client: LazyMCPClient,
        *,
        namesake_strategy: str,
        client_tools: list[Any] | None = None,
    ) -> None:
        if client_tools is None:
            client_tools = await self._discover_lazy_mcp_client_tools(client)
            if client_tools is None:
                return
        collisions = sorted(
            self._source_tool_names()
            & {str(getattr(tool, "name", "")) for tool in client_tools},
        )
        if collisions:
            raise RuntimeError(
                "MCP tool collides with an active source tool: "
                + ", ".join(collisions),
            )
        try:
            self._register_progress_callback(client)
            existing_tool_names = set(self._toolkit.tools)
            for tool in client_tools:
                self._toolkit.register_tool_function(
                    client.get_tool_function(tool),
                    func_name=tool.name,
                    func_description=getattr(tool, "description", "") or "",
                    json_schema=mcp_tool_json_schema(tool),
                    namesake_strategy=namesake_strategy,
                )
            registered_names = sorted(
                set(self._toolkit.tools) - existing_tool_names,
            )
            for tool_name in registered_names:
                self._toolkit.tools[tool_name].mcp_name = client.name
            self._normalize_tool_functions(self._toolkit, registered_names)
        except Exception as error:  # pylint: disable=broad-except
            logger.warning(
                "Failed to register lazy MCP client '%s', skipping: %s",
                client.name,
                error,
                exc_info=True,
            )

    def _wire_mcp_progress_callbacks(self, client: Any) -> None:
        mcp_name = getattr(client, "name", None)
        for tool_entry in getattr(self._toolkit, "tools", {}).values():
            func = getattr(tool_entry, "original_func", None)
            mcp_func = getattr(func, "__self__", None) or func
            if (
                isinstance(mcp_func, MCPToolFunction)
                and mcp_func.mcp_name == mcp_name
            ):
                mcp_func.on_progress_callback = self._reset_watchdog  # type: ignore[attr-defined]

    async def _recover_mcp_client(self, client: Any) -> Any | None:
        if await self._reconnect_mcp_client(client):
            return client
        rebuilt_client = self._rebuild_mcp_client(client)
        if rebuilt_client is not None and await self._reconnect_mcp_client(
            rebuilt_client,
        ):
            return self._reuse_shared_client_reference(client, rebuilt_client)
        return None

    @staticmethod
    def _reuse_shared_client_reference(
        original_client: Any,
        rebuilt_client: Any,
    ) -> Any:
        original_dict = getattr(original_client, "__dict__", None)
        rebuilt_dict = getattr(rebuilt_client, "__dict__", None)
        if isinstance(original_dict, dict) and isinstance(rebuilt_dict, dict):
            original_dict.update(rebuilt_dict)
            return original_client
        return rebuilt_client

    @staticmethod
    def _should_propagate_cancelled_error(error: BaseException) -> bool:
        if not isinstance(error, asyncio.CancelledError):
            return False
        task = asyncio.current_task()
        if task is None:
            return False
        cancelling = getattr(task, "cancelling", None)
        return cancelling() > 0 if callable(cancelling) else True

    @staticmethod
    async def _reconnect_mcp_client(
        client: Any,
        timeout: float = 60.0,
    ) -> bool:
        close_fn = getattr(client, "close", None)
        if callable(close_fn):
            try:
                await close_fn()
            except asyncio.CancelledError:
                raise
            except Exception:  # pylint: disable=broad-except
                pass
        connect_fn = getattr(client, "connect", None)
        if not callable(connect_fn):
            return False
        try:
            await asyncio.wait_for(connect_fn(), timeout=timeout)
            return True
        except asyncio.CancelledError:
            raise
        except (asyncio.TimeoutError, Exception):
            return False

    @staticmethod
    def _rebuild_mcp_client(client: Any) -> Any | None:
        rebuild_info = getattr(client, "_swe_rebuild_info", None)
        if not isinstance(rebuild_info, dict):
            return None
        transport = rebuild_info.get("transport")
        name = rebuild_info.get("name")
        try:
            if transport == "stdio":
                command = rebuild_info.get("command")
                if not isinstance(command, str) or not command:
                    return None
                launch_config = build_tenant_aware_stdio_launch_config(
                    command,
                    rebuild_info.get("args", []),
                    rebuild_info.get("env", {}),
                    rebuild_info.get("cwd"),
                    chat_id=rebuild_info.get("chat_id"),
                )
                rebuilt_client = StdIOStatefulClient(
                    name=name,
                    command=launch_config.launch_command,
                    args=launch_config.launch_args,
                    env=launch_config.env,
                    cwd=launch_config.cwd,
                )
                setattr(
                    rebuilt_client,
                    "_swe_rebuild_info",
                    {
                        **rebuild_info,
                        "launch_command": launch_config.launch_command,
                        "launch_args": launch_config.launch_args,
                        "launch_diagnostic": launch_config.diagnostic,
                    },
                )
                return rebuilt_client
            headers = build_mcp_http_headers(
                rebuild_info.get("headers"),
                passthrough_headers=rebuild_info.get("passthrough_headers"),
                url=rebuild_info.get("url"),
                session_id=rebuild_info.get("session_id"),
                chat_id=rebuild_info.get("chat_id"),
                trace_id=rebuild_info.get("trace_id"),
            )
            timeout = rebuild_info.get(
                "timeout",
                getattr(client, "timeout", None),
            )
            sse_read_timeout = rebuild_info.get(
                "sse_read_timeout",
                getattr(client, "sse_read_timeout", None),
            )
            kwargs = {
                key: value
                for key, value in {
                    "timeout": timeout,
                    "sse_read_timeout": sse_read_timeout,
                }.items()
                if value is not None
            }
            rebuilt_client = HttpStatefulClient(
                name=name,
                transport=transport,
                url=rebuild_info.get("url"),
                headers=headers,
                **kwargs,
            )
            setattr(
                rebuilt_client,
                "_swe_rebuild_info",
                {
                    **rebuild_info,
                    "timeout": timeout,
                    "sse_read_timeout": sse_read_timeout,
                },
            )
            return rebuilt_client
        except Exception:  # pylint: disable=broad-except
            return None
