# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from .auth_state import resolve_auth_token_for_execution
from .models import CronJobSpec
from ..tenant_context import bind_tenant_context
from ..console_push_store import append as push_store_append
from ...config.llm_workload import LLM_WORKLOAD_CRON, bind_llm_workload
from ...config.context import canonicalize_scope_id, resolve_scope_id
from ...tracing import has_trace_manager, get_trace_manager
from ...tracing.models import TraceStatus

logger = logging.getLogger(__name__)

CONSOLE_CHANNEL = "console"


@dataclass
class ExecutionResult:
    """执行结果，包含 trace_id 和输出预览。

    用于将执行过程中的关键信息传递给调用方。
    """

    trace_id: str = ""
    output_preview: str = ""
    input_snapshot: Optional[Dict[str, Any]] = None  # 执行时的输入快照
    executor_leader: str = ""  # 执行者 leader ID


async def _index_model_output_to_monitor(
    trace_id: str,
    model_output: str,
) -> None:
    """通过 Monitor API 写入 model_output 到 ES.

    Args:
        trace_id: 追踪 ID
        model_output: 模型输出文本
    """
    monitor_url = os.environ.get(
        "SWE_MONITOR_API_URL",
        "http://127.0.0.1:9090",
    )
    url = f"{monitor_url}/monitor/tracing/model-output"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                url,
                json={
                    "trace_id": trace_id,
                    "model_output": model_output,
                },
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "success":
                    logger.info(
                        "Model output indexed via Monitor API: trace_id=%s",
                        trace_id,
                    )
                else:
                    logger.info(
                        "Model output write skipped: trace_id=%s, reason=%s",
                        trace_id,
                        result.get("reason", "unknown"),
                    )
            else:
                logger.warning(
                    "Monitor API returned %s: trace_id=%s",
                    response.status_code,
                    trace_id,
                )
    except httpx.TimeoutException:
        logger.warning("Monitor API timeout: trace_id=%s", trace_id)
    except Exception as e:
        logger.warning(
            "Failed to call Monitor API for model_output: %s",
            e,
        )


class CronExecutor:
    def __init__(self, *, runner: Any, channel_manager: Any):
        self._runner = runner
        self._channel_manager = channel_manager

    async def execute(self, job: CronJobSpec) -> ExecutionResult:
        """Execute one job once with tenant context.

        - task_type text: send fixed text to channel
        - task_type agent: ask agent with prompt, send reply to channel (
            stream_query + send_event)

        Job execution is wrapped in tenant context to ensure proper isolation.

        Returns:
            ExecutionResult containing trace_id and output_preview
        """
        target_user_id = job.dispatch.target.user_id
        target_session_id = job.dispatch.target.session_id
        dispatch_meta: Dict[str, Any] = dict(job.dispatch.meta or {})
        workspace_dir_value = dispatch_meta.get("workspace_dir")
        workspace_dir = None
        if workspace_dir_value:
            workspace_dir = Path(workspace_dir_value)

        # Extract tenant_id from job spec (added for tenant isolation)
        tenant_id = getattr(job, "tenant_id", None)
        source_id = getattr(job, "source_id", None)
        job_scope_id = getattr(job, "scope_id", None)
        scope_id = (
            canonicalize_scope_id(job_scope_id)
            if job_scope_id is not None
            else resolve_scope_id(tenant_id, source_id)
        )
        if tenant_id:
            dispatch_meta["tenant_id"] = tenant_id
        if source_id:
            dispatch_meta["source_id"] = source_id
        if scope_id:
            dispatch_meta["scope_id"] = scope_id

        logger.info(
            "cron execute: job_id=%s channel=%s task_type=%s "
            "target_user_id=%s target_session_id=%s tenant_id=%s",
            job.id,
            job.dispatch.channel,
            job.task_type,
            target_user_id[:40] if target_user_id else "",
            target_session_id[:40] if target_session_id else "",
            tenant_id or "default",
        )

        # Wrap execution in tenant context
        with (
            bind_tenant_context(
                tenant_id=tenant_id,
                user_id=target_user_id,
                workspace_dir=workspace_dir,
                source_id=source_id,
                scope_id=scope_id,
            ),
            bind_llm_workload(LLM_WORKLOAD_CRON),
        ):
            result = await self._execute_job(
                job,
                target_user_id,
                target_session_id,
                dispatch_meta,
            )
        result = result or {}
        output_preview = str(result.get("output_preview") or "")

        return ExecutionResult(
            trace_id=str(result.get("trace_id") or ""),
            output_preview=output_preview[:100],
            input_snapshot=result.get("input_snapshot"),
            executor_leader=str(result.get("executor_leader") or ""),
        )

    async def _execute_job(
        self,
        job: CronJobSpec,
        target_user_id: str,
        target_session_id: str,
        dispatch_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Internal: execute job logic (called within tenant context).

        Returns:
            Dict with trace_id, output_preview, input_snapshot, executor_leader
        """
        if job.task_type == "text" and job.text:
            return await self._execute_text_job(
                job,
                target_user_id,
                target_session_id,
                dispatch_meta,
            )
        else:
            return await self._execute_agent_job(
                job,
                target_user_id,
                target_session_id,
                dispatch_meta,
            )

    async def _execute_text_job(
        self,
        job: CronJobSpec,
        target_user_id: str,
        target_session_id: str,
        dispatch_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute text-type job: send fixed text to channel.

        Returns:
            Dict with trace_id, output_preview, input_snapshot, executor_leader
        """
        runtime_tenant_id = (
            dispatch_meta.get("scope_id")
            or dispatch_meta.get("tenant_id")
            or "default"
        )
        logger.info(
            "cron send_text: job_id=%s channel=%s len=%s",
            job.id,
            job.dispatch.channel,
            len(job.text or ""),
        )

        # 保留抽出的 helper，同时继续传递 scope 级租户标识。
        trace_id = await self._create_trace_for_text_job(
            job,
            target_user_id,
            target_session_id,
        )

        try:
            await self._send_text_to_channel(
                job,
                target_user_id,
                target_session_id,
                dispatch_meta,
                runtime_tenant_id,
            )
        finally:
            await self._end_trace_for_text_job(trace_id)

        # 返回执行结果
        output_preview = (job.text or "").strip()[:100]
        input_snapshot = (
            {"text": (job.text or "").strip()} if job.text else None
        )
        return {
            "trace_id": trace_id or "",
            "output_preview": output_preview,
            "input_snapshot": input_snapshot,
            "executor_leader": "",
        }

    async def _create_trace_for_text_job(
        self,
        job: CronJobSpec,
        target_user_id: str,
        target_session_id: str,
    ) -> Optional[str]:
        """为 text 类型任务创建 trace 记录。

        Args:
            job: 任务定义
            target_user_id: 目标用户 ID
            target_session_id: 目标会话 ID

        Returns:
            trace_id 或 None
        """
        if not has_trace_manager():
            return None

        try:
            trace_mgr = get_trace_manager()
            if not trace_mgr.enabled:
                return None

            source_id = job.source_id or "default"
            trace_id = await trace_mgr.start_trace(
                user_id=target_user_id or "cron",
                session_id=target_session_id or f"cron:{job.id}",
                channel=job.dispatch.channel,
                source_id=source_id,
                user_message=None,
                user_name=job.tenant_name,
                bbk_id=job.bbk_id,
                session_name=job.name,
            )
            # 写入 model_output 到 ES
            if trace_id and job.text:
                await _index_model_output_to_monitor(
                    trace_id,
                    job.text.strip(),
                )
            return trace_id
        except Exception as e:
            logger.warning("Failed to start trace for text job: %s", e)
            return None

    async def _send_text_to_channel(
        self,
        job: CronJobSpec,
        target_user_id: str,
        target_session_id: str,
        dispatch_meta: Dict[str, Any],
        runtime_tenant_id: str,
    ) -> None:
        """发送 text 到 channel 并推送到 console。

        Args:
            job: 任务定义
            target_user_id: 目标用户 ID
            target_session_id: 目标会话 ID
            dispatch_meta: dispatch 元数据
            runtime_tenant_id: 运行时 scope/tenant 标识
        """
        await self._channel_manager.send_text(
            channel=job.dispatch.channel,
            user_id=target_user_id,
            session_id=target_session_id,
            text=job.text.strip(),
            meta=dispatch_meta,
        )
        task_chat_id: Optional[str] = (job.meta or {}).get("task_chat_id")
        if job.dispatch.channel != CONSOLE_CHANNEL and task_chat_id:
            await self._push_to_console(
                task_chat_id,
                job.text.strip(),
                runtime_tenant_id,
            )

    async def _end_trace_for_text_job(self, trace_id: Optional[str]) -> None:
        """结束 text 任务的 trace。

        Args:
            trace_id: trace ID
        """
        if not trace_id or not has_trace_manager():
            return

        try:
            trace_mgr = get_trace_manager()
            await trace_mgr.end_trace(trace_id, TraceStatus.COMPLETED)
        except Exception as e:
            logger.warning("Failed to end trace for text job: %s", e)

    async def _create_trace_for_agent_job(
        self,
        job: CronJobSpec,
        target_user_id: str,
        target_session_id: str,
    ) -> Optional[str]:
        """为 agent 任务创建 trace 记录。

        Args:
            job: 任务定义
            target_user_id: 目标用户 ID
            target_session_id: 目标会话 ID

        Returns:
            trace_id 或 None
        """
        if not has_trace_manager():
            return None

        try:
            trace_mgr = get_trace_manager()
            if not trace_mgr.enabled:
                return None

            source_id = job.source_id or "default"
            trace_id = await trace_mgr.start_trace(
                user_id=target_user_id or "cron",
                session_id=target_session_id or f"cron:{job.id}",
                channel=job.dispatch.channel,
                source_id=source_id,
                user_message=None,  # agent 任务的用户消息由 runner 处理
                user_name=job.tenant_name,
                bbk_id=job.bbk_id,
                session_name=job.name,
            )
            logger.info(
                "cron agent: created trace_id=%s for job_id=%s",
                trace_id[:20] if trace_id else "(empty)",
                job.id,
            )
            return trace_id
        except Exception as e:
            logger.warning("Failed to start trace for agent job: %s", e)
            return None

    async def _end_trace_on_exception(
        self,
        trace_id: Optional[str],
        status: TraceStatus,
        error_msg: Optional[str] = None,
    ) -> None:
        """异常情况下结束 trace。

        Args:
            trace_id: trace ID
            status: trace 状态
            error_msg: 错误信息（可选）
        """
        if not trace_id or not has_trace_manager():
            return

        try:
            trace_mgr = get_trace_manager()
            await trace_mgr.end_trace(trace_id, status, error_msg)
        except Exception as e:
            logger.warning("Failed to end trace for %s: %s", status, e)

    async def _end_trace_on_success(
        self,
        trace_id: Optional[str],
        job_id: str,
    ) -> None:
        """成功情况下结束 trace（使用 shield 保护）。

        Args:
            trace_id: trace ID
            job_id: 任务 ID
        """
        if not trace_id or not has_trace_manager():
            return

        trace_mgr = get_trace_manager()
        task = asyncio.create_task(
            trace_mgr.end_trace(trace_id, TraceStatus.COMPLETED),
        )

        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # 外部取消信号到达，但 shield 已阻止其传播到 end_trace
            # 显式等待 task 完成，确保 trace 状态正确写入
            logger.info(
                "Trace ending was cancelled after successful cron execution; "
                "waiting for end_trace to finish: job_id=%s",
                job_id,
            )
            try:
                await task
            except Exception as e:
                logger.warning("Failed to end trace for success: %s", e)
        except Exception as e:
            logger.warning("Failed to end trace for success: %s", e)

    def _build_agent_execution_result(
        self,
        trace_id: Optional[str],
        console_text_parts: list[str],
        req: Dict[str, Any],
    ) -> Dict[str, Any]:
        """构建 agent 任务执行结果。

        Args:
            trace_id: trace ID
            console_text_parts: 输出的文本部分列表
            req: agent 请求字典

        Returns:
            包含执行结果的字典
        """
        output_preview = (
            "\n".join(console_text_parts)[:100] if console_text_parts else ""
        )
        input_snapshot = req if req else None
        return {
            "trace_id": trace_id,
            "output_preview": output_preview,
            "input_snapshot": input_snapshot,
            "executor_leader": "",
        }

    async def _execute_agent_job(
        self,
        job: CronJobSpec,
        target_user_id: str,
        target_session_id: str,
        dispatch_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute agent-type job: run agent query and send events.

        Returns:
            Dict with trace_id, output_preview, input_snapshot, executor_leader
        """
        runtime_tenant_id = (
            dispatch_meta.get("scope_id")
            or dispatch_meta.get("tenant_id")
            or "default"
        )
        logger.info(
            "cron agent: job_id=%s channel=%s timeout=%ss",
            job.id,
            job.dispatch.channel,
            job.runtime.timeout_seconds,
        )
        assert job.request is not None
        req = self._build_agent_request(job, target_user_id, target_session_id)
        self._apply_auth_token(job, dispatch_meta, req)

        # 在 executor 中创建 trace，确保 trace_id 可用
        trace_id = await self._create_trace_for_agent_job(
            job,
            target_user_id,
            target_session_id,
        )
        if trace_id:
            req["trace_id"] = trace_id

        # 用于标记 trace 是否已被结束（防止重复结束）
        trace_ended = False
        console_text_parts: list[str] = []
        result: Optional[Dict[str, Any]] = None
        try:
            # Wrap the entire agent execution in a timeout
            # asyncio.timeout 是 Python 3.11+ 的特性，低版本使用 wait_for
            if hasattr(asyncio, "timeout"):
                async with asyncio.timeout(job.runtime.timeout_seconds):
                    await self._run_agent_stream(
                        job,
                        target_user_id,
                        target_session_id,
                        dispatch_meta,
                        req,
                        console_text_parts,
                    )
            else:
                await asyncio.wait_for(
                    self._run_agent_stream(
                        job,
                        target_user_id,
                        target_session_id,
                        dispatch_meta,
                        req,
                        console_text_parts,
                    ),
                    timeout=job.runtime.timeout_seconds,
                )
            # 推送结果到 console
            task_chat_id: Optional[str] = (job.meta or {}).get("task_chat_id")
            if (
                job.dispatch.channel != CONSOLE_CHANNEL
                and console_text_parts
                and task_chat_id
            ):
                await self._push_to_console(
                    task_chat_id,
                    "\n".join(console_text_parts),
                    runtime_tenant_id,
                )
            # 正常完成，构建执行结果
            result = self._build_agent_execution_result(
                trace_id,
                console_text_parts,
                req,
            )
        except asyncio.TimeoutError:
            trace_ended = True
            logger.warning(
                "cron execute: job_id=%s timed out after %ss",
                job.id,
                job.runtime.timeout_seconds,
            )
            await self._notify_timeout(job, runtime_tenant_id)
            await self._end_trace_on_exception(
                trace_id,
                TraceStatus.ERROR,
                "Timeout",
            )
            raise
        except asyncio.CancelledError:
            trace_ended = True
            logger.info("cron execute: job_id=%s cancelled", job.id)
            await self._end_trace_on_exception(trace_id, TraceStatus.CANCELLED)
            raise
        except Exception as e:  # pylint: disable=broad-except
            trace_ended = True
            logger.warning(
                "cron execute: job_id=%s error: %s",
                job.id,
                repr(e),
            )
            await self._end_trace_on_exception(
                trace_id,
                TraceStatus.ERROR,
                str(e),
            )
            raise
        finally:
            # 结束 trace（仅在未被结束时）
            # 使用 shield 保护 end_trace 操作，确保 trace 状态正确写入
            if trace_id and not trace_ended:
                await self._end_trace_on_success(trace_id, job.id)

        # 正常完成时返回结果（异常分支已 raise）
        return result

    def _build_agent_request(
        self,
        job: CronJobSpec,
        target_user_id: str,
        target_session_id: str,
    ) -> Dict[str, Any]:
        """Build agent request dict from job spec."""
        req: Dict[str, Any] = job.request.model_dump(mode="json")
        req["user_id"] = req.get("user_id") or target_user_id or "cron"
        req["session_id"] = (
            req.get("session_id") or target_session_id or f"cron:{job.id}"
        )
        req["skip_history"] = True  # 标记定时任务不加载历史会话
        # 传递 source_id 用于 tracing 数据隔离
        if job.source_id:
            req["source_id"] = job.source_id
        scope_id = (
            canonicalize_scope_id(job.scope_id)
            if job.scope_id is not None
            else resolve_scope_id(
                getattr(job, "tenant_id", None),
                job.source_id,
            )
        )
        if scope_id:
            req["scope_id"] = scope_id
        # 传递 bbk_id 用于 tracing 用户标识
        if job.bbk_id:
            req["bbk_id"] = job.bbk_id
        # 传递 user_name（从 tenant_name 字段获取）
        if job.tenant_name:
            req["user_name"] = job.tenant_name
        return req

    def _apply_auth_token(
        self,
        job: CronJobSpec,
        dispatch_meta: Dict[str, Any],
        req: Dict[str, Any],
    ) -> None:
        """Resolve and apply auth token to request."""
        runtime_tenant_id = (
            canonicalize_scope_id(job.scope_id)
            if job.scope_id is not None
            else resolve_scope_id(
                getattr(job, "tenant_id", None),
                getattr(job, "source_id", None),
            )
        )
        try:
            resolved = resolve_auth_token_for_execution(
                tenant_id=runtime_tenant_id,
                workspace_dir=dispatch_meta.get("workspace_dir"),
            )
        except ValueError as exc:
            logger.warning(
                "cron agent aborted: job_id=%s auth_state_error=%s",
                job.id,
                repr(exc),
            )
            raise RuntimeError(
                "cron auth user_info is expired; "
                "please refresh cron auth configuration",
            ) from exc
        if resolved.token:
            req["auth_token"] = resolved.token
        if resolved.cookie_header:
            req["cookie"] = resolved.cookie_header

    async def _run_agent_stream(
        self,
        job: CronJobSpec,
        target_user_id: str,
        target_session_id: str,
        dispatch_meta: Dict[str, Any],
        req: Dict[str, Any],
        console_text_parts: list[str],
    ) -> None:
        """Run agent stream query and send events to channel."""
        async for event in self._runner.stream_query(req):
            await self._channel_manager.send_event(
                channel=job.dispatch.channel,
                user_id=target_user_id,
                session_id=target_session_id,
                event=event,
                meta=dispatch_meta,
            )
            text = self._extract_text_from_event(event)
            if text:
                console_text_parts.append(text)

    async def _notify_timeout(self, job: CronJobSpec, tenant_id: str) -> None:
        """Push a timeout notification to the console so the user is aware.

        Falls back to logging if the push fails; never raises.
        """
        task_chat_id: Optional[str] = (job.meta or {}).get("task_chat_id")
        target_session_id = task_chat_id or job.dispatch.target.session_id
        if not target_session_id:
            logger.warning(
                "cron timeout: no session_id for job_id=%s",
                job.id,
            )
            return
        timeout_text = (
            f"⏰ 定时任务 [{job.name}] 执行超时"
            f"（{job.runtime.timeout_seconds}s），已自动终止。"
        )
        try:
            await self._push_to_console(
                target_session_id,
                timeout_text,
                tenant_id,
            )
        except Exception:  # pylint: disable=broad-except
            logger.warning(
                "Failed to push timeout notification for job_id=%s",
                job.id,
                exc_info=True,
            )

    async def _push_to_console(
        self,
        session_id: str,
        text: str,
        tenant_id: str,
    ) -> None:
        """Push message to console channel for frontend notification."""
        if not session_id or not text:
            return
        logger.info(
            "cron push_to_console: session_id=%s text_len=%s tenant_id=%s",
            session_id[:40] if session_id else "",
            len(text),
            tenant_id,
        )
        await push_store_append(session_id, text.strip(), tenant_id=tenant_id)

    def _extract_text_from_event(self, event: Any) -> str:
        """Extract text content from a runner event.

        Args:
            event: Runner event (from stream_query)

        Returns:
            Extracted text string, empty if no text found
        """
        from agentscope_runtime.engine.schemas.agent_schemas import RunStatus

        obj = getattr(event, "object", None)
        status = getattr(event, "status", None)

        # Only extract from completed message events
        if obj != "message" or status != RunStatus.Completed:
            return ""

        # Extract text from message content
        content = getattr(event, "content", None) or []
        text_parts: list[str] = []
        for part in content:
            part_type = getattr(part, "type", None)
            if part_type == "text":
                text = getattr(part, "text", None)
                if text:
                    text_parts.append(text)
            elif part_type == "refusal":
                refusal = getattr(part, "refusal", None)
                if refusal:
                    text_parts.append(refusal)

        return "\n".join(text_parts) if text_parts else ""
